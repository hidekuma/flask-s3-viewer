import os
import unicodedata
import urllib
import urllib.parse
from collections.abc import Iterable
from datetime import timezone
from functools import wraps
from typing import Any
from urllib.parse import quote as url_quote

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import HTTPException

from .. import APP_TEMPLATE_FOLDER, FlaskS3Viewer
from ..audit import emit as audit_emit
from ..auth import (
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_LIST,
    ACTION_PRESIGN,
    ACTION_UPLOAD,
)
from ..config import NAMESPACE
from ..errors import InvalidPrefix, InvalidRangeError

blueprint = Blueprint(
    NAMESPACE,
    __name__,
    template_folder=APP_TEMPLATE_FOLDER,
    static_folder='static',
    static_url_path='flasks3viewerassets',
    url_prefix='/<path:BUCKET_NAMESPACE>',
)

# Auth routes intentionally live OUTSIDE the namespace prefix: OAuth is
# an app-level concern (one client per Flask app, shared across every
# FlaskS3Viewer namespace), and tying the callback URL to a specific
# namespace would force the deployer to register N redirect URIs in
# Google Console — and re-register every time a namespace name changes.
auth_blueprint = Blueprint(
    f'{NAMESPACE}_auth',
    __name__,
    url_prefix='/auth',
)


@blueprint.app_errorhandler(HTTPException)
def handle_http_exception(e: HTTPException) -> Any:
    if request.blueprint != NAMESPACE or not hasattr(g, 'BUCKET_NAMESPACE'):
        return e
    template = '_error_panel.html' if request.headers.get('HX-Request') else 'error.html'
    return render_template(
        template,
        FS3V_MESSAGE=e.description,
        FS3V_CODE=e.code,
    ), e.code


def _any_oauth_configured() -> bool:
    """Return True when at least one viewer instance has Google OAuth wired up."""
    registry = current_app.extensions.get(NAMESPACE, {})
    return any(getattr(v, 'google_client_id', None) for v in registry.values())


def _any_auth_enabled() -> bool:
    """Return True when at least one viewer has any auth opt-in."""
    registry = current_app.extensions.get(NAMESPACE, {})
    return any(getattr(v, 'auth_enabled', False) for v in registry.values())


def _get_viewer(namespace: str) -> FlaskS3Viewer:
    """Lookup a FlaskS3Viewer instance via the Flask extensions registry.

    Replaces the v0.x ``FlaskS3Viewer.get_instance(namespace)`` Singleton
    lookup. Called from request handlers so ``current_app`` is always
    available.
    """
    try:
        viewer: FlaskS3Viewer = current_app.extensions['flask_s3_viewer'][namespace]
        return viewer
    except KeyError:
        abort(404, 'Unknown FlaskS3Viewer namespace')


def _enforce_auth(fs3viewer: FlaskS3Viewer, action: str, key: str | None = None) -> Any:
    """Run the viewer's auth + permission callbacks for the current request.

    Returns the authenticated email (may be ``None`` when the viewer is
    in the legacy "no auth" mode and the deployer hasn't wired anything
    up — in that case the route is treated as fully public).

    Raises ``abort(401)`` if the deployer enabled auth but the request
    cannot be tied to an identity, and ``abort(403)`` when the identity
    lacks the requested action permission.
    """
    if not fs3viewer.auth_enabled:
        return None
    email = fs3viewer.auth_callback(request)
    if not email:
        # When Google OAuth is configured, send the user through the
        # login flow instead of a bare 401 — that's what a browser
        # client (the dominant case) needs. Redirect is intentionally
        # not audited; the follow-up request after login carries the
        # identity and produces the canonical record.
        if request.method == 'GET' and fs3viewer.google_client_id:
            return redirect(url_for(
                'flask_s3_viewer_auth.login',
                next=request.url,
            ))
        # emit BEFORE abort — flask's abort() raises and short-circuits.
        audit_emit(
            action=action,
            namespace=getattr(g, 'BUCKET_NAMESPACE', None),
            key=key,
            user='anonymous',
            result='denied',
            status_code=401,
        )
        g.FSV_AUDIT_EMITTED = True
        abort(401, 'Authentication required.')
    if not fs3viewer.permission_callback(email, action, g.BUCKET_NAMESPACE, key):
        audit_emit(
            action=action,
            namespace=getattr(g, 'BUCKET_NAMESPACE', None),
            key=key,
            user=email,
            result='denied',
            status_code=403,
        )
        g.FSV_AUDIT_EMITTED = True
        abort(403, 'Forbidden.')
    g.FSV_AUTH_EMAIL = email
    return email


def _normalize_object_key(
    fs3viewer: FlaskS3Viewer,
    key: str,
) -> tuple[str, str]:
    decoded = urllib.parse.unquote_plus(key)
    return decoded, fs3viewer.get_object_name(decoded)


def _normalize_prefix_key(
    fs3viewer: FlaskS3Viewer,
    prefix: str | None,
) -> tuple[str, str]:
    decoded = urllib.parse.unquote_plus(prefix or '')
    return decoded, fs3viewer.prefixer(decoded)


def _normalize_upload_filename(filename: str) -> str:
    if not filename or '\x00' in filename:
        raise InvalidPrefix(filename)
    if '/' in filename or '\\' in filename:
        raise InvalidPrefix(filename)
    if filename in ('.', '..'):
        raise InvalidPrefix(filename)
    return filename


def _audit_emit_file(
    action: str,
    key: str | None,
    status_code: int,
    result: str,
    exc: BaseException | None = None,
) -> None:
    """Emit a single audit record for one file inside a multi-file request.

    Captures the request-scoped invariants (namespace, authenticated user)
    from ``g`` so callers only pass the per-file varying bits. Setting
    ``g.FSV_AUDIT_EMITTED`` here is part of the contract — once any file
    line has fired, the request-level finally fallback must NOT emit a
    duplicate aggregate row.
    """
    audit_emit(
        action=action,
        namespace=getattr(g, 'BUCKET_NAMESPACE', None),
        key=key,
        user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
        result=result,
        status_code=status_code,
        exc=exc,
    )
    g.FSV_AUDIT_EMITTED = True


def _status_from_response(rv: Any) -> int:
    """Best-effort extraction of an HTTP status from a Flask view return.

    Flask view functions return either a ``Response``, a string, a dict,
    or a tuple ``(body, status[, headers])``. We only need the integer
    code for the audit record — non-integer or absent codes default to
    ``200`` (Flask's own default).
    """
    if isinstance(rv, tuple) and len(rv) >= 2 and isinstance(rv[1], int):
        return rv[1]
    status = getattr(rv, 'status_code', None)
    if isinstance(status, int):
        return status
    return 200


def require(action: str) -> Any:
    """Decorator: enforce ``_enforce_auth`` before running the route.

    The decorated handler receives the regular Flask URL kwargs unchanged.
    ``action`` is one of the ACTION_* constants from ``flask_s3_viewer.auth``.
    Wraps the handler in a try/except so every terminal outcome (success,
    HTTPException raised by ``abort``, unexpected exception) produces
    exactly one audit record.
    """
    def deco(fn: Any) -> Any:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            viewer = _get_viewer(g.BUCKET_NAMESPACE)
            key = kwargs.get('key')
            canonical_key: str | None = None
            if key is not None:
                try:
                    _decoded_key, canonical_key = _normalize_object_key(viewer, key)
                except InvalidPrefix:
                    audit_emit(
                        action=action,
                        namespace=getattr(g, 'BUCKET_NAMESPACE', None),
                        key=key,
                        user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
                        result='error',
                        status_code=400,
                    )
                    g.FSV_AUDIT_EMITTED = True
                    abort(400, 'Invalid prefix')
            maybe_redirect = _enforce_auth(viewer, action, canonical_key)
            # `_enforce_auth` may have returned a redirect response (Google login).
            if maybe_redirect is not None and not isinstance(maybe_redirect, str):
                return maybe_redirect
            try:
                rv = fn(*args, **kwargs)
            except HTTPException as e:
                if not getattr(g, 'FSV_AUDIT_EMITTED', False):
                    audit_emit(
                        action=action,
                        namespace=getattr(g, 'BUCKET_NAMESPACE', None),
                        key=canonical_key,
                        user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
                        result='error' if (e.code or 500) >= 400 else 'ok',
                        status_code=e.code or 500,
                        exc=e,
                    )
                    g.FSV_AUDIT_EMITTED = True
                raise
            except Exception as e:
                if not getattr(g, 'FSV_AUDIT_EMITTED', False):
                    audit_emit(
                        action=action,
                        namespace=getattr(g, 'BUCKET_NAMESPACE', None),
                        key=canonical_key,
                        user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
                        result='error',
                        status_code=500,
                        exc=e,
                    )
                    g.FSV_AUDIT_EMITTED = True
                raise
            else:
                if not getattr(g, 'FSV_AUDIT_EMITTED', False):
                    code = _status_from_response(rv)
                    audit_emit(
                        action=action,
                        namespace=getattr(g, 'BUCKET_NAMESPACE', None),
                        key=canonical_key,
                        user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
                        result='ok' if code < 400 else 'error',
                        status_code=code,
                    )
                    g.FSV_AUDIT_EMITTED = True
            return rv
        return wrapped
    return deco


def is_allowed(fs3viewer: FlaskS3Viewer, filename: str) -> bool:
    if fs3viewer.allowed_extensions:
        return (
            '.' in filename
            and filename.rsplit('.', 1)[1].lower() in fs3viewer.allowed_extensions
        )
    return True


@blueprint.url_defaults
def add_division(endpoint: str, values: dict) -> None:
    values.setdefault(
        'BUCKET_NAMESPACE',
        g.BUCKET_NAMESPACE,
    )


@blueprint.url_value_preprocessor
def pull_division(endpoint: Any, values: Any) -> None:
    g.BUCKET_NAMESPACE = values.pop('BUCKET_NAMESPACE')


@blueprint.route("/files/<path:key>", methods=['GET'])
@require(ACTION_DOWNLOAD)
def files_download(key: str) -> Any:
    if request.method == "GET":
        """
        key: encoded
        """
        fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
        try:
            key, _canonical_key = _normalize_object_key(fs3viewer, key)
        except InvalidPrefix:
            abort(400, 'Invalid prefix')
        range_header = request.headers.get('Range')
        try:
            obj = fs3viewer.find_one(key, range=range_header)
        except InvalidRangeError:
            # RFC 7233 §4.4 — malformed / unsatisfiable Range.
            abort(416, 'Range Not Satisfiable')
        if obj:
            try:
                key_bytes: bytes = os.path.basename(key).encode('latin-1')
            except UnicodeEncodeError:
                encoded_key = unicodedata.normalize(
                    'NFKD',
                    key,
                ).encode('latin-1', 'ignore')
                filenames: dict = {
                    'filename': encoded_key,
                    'filename*': f"UTF-8''{url_quote(key)}",
                }
            else:
                filenames = {'filename': key_bytes.decode('utf-8')}
            # boto3 응답의 'Body' (StreamingBody)는 file-like / iterable 이므로
            # Werkzeug WSGI 헬퍼 없이도 Response가 직접 chunk 스트리밍을 처리한다.
            # Range가 있으면 boto3가 ``ContentRange`` 응답 헤더를 채워준다 —
            # RFC 7233 ``206 Partial Content`` 응답으로 변환한다.
            status = 206 if range_header and obj.get('ContentRange') else 200
            rv = Response(
                obj.get('Body', b''),
                status=status,
                direct_passthrough=True,
                mimetype=obj['ContentType'],
            )
            rv.headers['Accept-Ranges'] = 'bytes'
            if status == 206:
                rv.headers['Content-Range'] = obj['ContentRange']
                rv.headers['Content-Length'] = str(obj.get('ContentLength', ''))
            rv.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            rv.headers['Pragma'] = 'no-cache'
            rv.headers['Expires'] = '0'
            rv.headers.set('Content-Disposition', 'attachment', **filenames)
            return rv
        else:
            return render_template(
                'error.html',
                FS3V_MESSAGE="Can't not found resource.",
                FS3V_CODE=404,
            ), 404


@blueprint.route("/files/<path:key>", methods=['DELETE'])
@require(ACTION_DELETE)
def files_delete(key: str) -> tuple[str, int]:
    if request.method == 'DELETE':
        """
        key: decoded
        """
        fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
        try:
            key, _canonical_key = _normalize_object_key(fs3viewer, key)
            fs3viewer.remove(key)
            # HTMX flow: hx-swap removes the row, so an empty 200 body is the
            # idiomatic response. Non-HTMX callers still get the v0.x 204.
            if request.headers.get('HX-Request'):
                return '', 200
            return '', 204
        except InvalidPrefix:
            abort(400, 'Invalid prefix')
        except Exception:
            abort(500)
    abort(405)


@blueprint.route("/files/presign", methods=['POST'])
def files_presign() -> Any:
    # No @require decorator — auth is enforced manually after we have
    # the canonical prefix in hand, so the audit/permission record sees
    # the same key the S3 layer will use.
    fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
    prefix: str | None = None
    response_code = 500
    audit_exc: BaseException | None = None
    try:
        try:
            _decoded_prefix, prefix = _normalize_prefix_key(
                fs3viewer,
                request.form.get('prefix', ''),
            )
        except InvalidPrefix:
            response_code = 400
            abort(400, 'Invalid prefix')
        _redirect = _enforce_auth(fs3viewer, ACTION_PRESIGN, prefix)
        if _redirect is not None and not isinstance(_redirect, str):
            # Redirect: skip audit (deliberate — see _enforce_auth doc).
            g.FSV_AUDIT_EMITTED = True
            return _redirect
        file_list = request.form.get("file_list")
        allow_overwrite = request.form.get('overwrite') == '1'
        rtns: list[dict] = []
        if file_list:
            for f in file_list.split(','):
                filename: str | None = None
                try:
                    safe_name = _normalize_upload_filename(f)
                    filename = f'{prefix}{safe_name}'
                    if fs3viewer.is_exists(filename) and not allow_overwrite:
                        rtns.append({'status_code': 409})
                        _audit_emit_file(ACTION_PRESIGN, filename, 409, 'error')
                    elif not is_allowed(fs3viewer, filename):
                        rtns.append({'status_code': 403})
                        _audit_emit_file(ACTION_PRESIGN, filename, 403, 'error')
                    else:
                        r = fs3viewer.post_presign(filename)
                        rtns.append(r)
                        _audit_emit_file(ACTION_PRESIGN, filename, 200, 'ok')
                except InvalidPrefix:
                    response_code = 400
                    abort(400, 'Invalid prefix')
                except Exception as e:
                    rtns.append({'status_code': 500})
                    _audit_emit_file(ACTION_PRESIGN, filename, 500, 'error', exc=e)

        fs3viewer.purge(prefix)
        response_code = 200
        return jsonify(rtns), 200
    except HTTPException as e:
        response_code = e.code or 500
        audit_exc = e
        raise
    except Exception as e:
        response_code = 500
        audit_exc = e
        raise
    finally:
        # Per-file paths inside the rtns loop set the sentinel through
        # ``_audit_emit_file``; this block only fires when no file was
        # iterated (empty file_list, invalid prefix abort, denied auth).
        if not getattr(g, 'FSV_AUDIT_EMITTED', False):
            audit_emit(
                action=ACTION_PRESIGN,
                namespace=getattr(g, 'BUCKET_NAMESPACE', None),
                key=prefix,
                user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
                result='ok' if response_code < 400 else 'error',
                status_code=response_code,
                exc=audit_exc,
            )
            g.FSV_AUDIT_EMITTED = True


@blueprint.route("/files/conflicts", methods=['POST'])
def files_conflicts() -> Any:
    fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
    try:
        _decoded_prefix, prefix = _normalize_prefix_key(
            fs3viewer,
            request.form.get('prefix', ''),
        )
    except InvalidPrefix:
        abort(400, 'Invalid prefix')
    _redirect = _enforce_auth(fs3viewer, ACTION_UPLOAD, prefix)
    if _redirect is not None and not isinstance(_redirect, str):
        return _redirect

    filenames = request.form.getlist('file_names[]')
    if not filenames:
        file_list = request.form.get('file_list', '')
        filenames = [f for f in file_list.split(',') if f]

    targets: list[tuple[str, str]] = []
    for filename in filenames:
        try:
            safe_name = _normalize_upload_filename(filename)
        except InvalidPrefix:
            abort(400, 'Invalid prefix')
        target = f'{prefix}{safe_name}'
        targets.append((safe_name, target))

    target_keys = [target for _safe_name, target in targets]
    duplicate_targets = sorted({target for target in target_keys if target_keys.count(target) > 1})
    conflicts = [
        safe_name
        for safe_name, target in targets
        if target in duplicate_targets or fs3viewer.is_exists(target)
    ]
    disallowed_targets = [target for _safe_name, target in targets if not is_allowed(fs3viewer, target)]
    if disallowed_targets:
        abort(403, 'Not allowd file extension')

    return jsonify({'conflicts': conflicts}), 200


@blueprint.route("/files", methods=['GET', 'POST'])
def files() -> Any:
    # files() carries two distinct actions (LIST vs UPLOAD) so it can't
    # use the @require decorator wholesale — enforce per branch and
    # emit one audit record per request in the finally block.
    fs3viewer_for_auth = _get_viewer(g.BUCKET_NAMESPACE)
    action = ACTION_UPLOAD if request.method == "POST" else ACTION_LIST
    audit_key: str | None = None
    response_code = 500
    audit_exc: BaseException | None = None
    try:
        if request.method == "POST":
            """
            prefix: encoded
            files[].f.filename: decoded
            prefixer(): 탐색 및 폴더생성시
            """
            # form
            files_list: Iterable[FileStorage] = request.files.getlist("files[]")
            fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
            try:
                raw_prefix, full_prefix = _normalize_prefix_key(
                    fs3viewer,
                    request.form.get('prefix', ''),
                )
            except InvalidPrefix:
                response_code = 400
                abort(400, 'Invalid prefix')
            audit_key = full_prefix
            _redirect = _enforce_auth(fs3viewer_for_auth, ACTION_UPLOAD, full_prefix)
            if _redirect is not None and not isinstance(_redirect, str):
                g.FSV_AUDIT_EMITTED = True
                return _redirect
            if not files_list and full_prefix:
                if fs3viewer.is_exists(full_prefix):
                    response_code = 409
                    abort(409, 'Already exists.')
                if not fs3viewer.mkdir(full_prefix):
                    response_code = 500
                    abort(500)
                # mkdir: stay in the parent prefix (don't navigate into the new folder).
                parent = os.path.dirname(raw_prefix.rstrip('/'))
                listing_prefix = parent + '/' if parent else ''
            else:
                # Detect duplicates and ask the client to confirm overwrite once.
                allow_overwrite = (
                    request.form.get('overwrite') == '1'
                    or request.headers.get('HX-Fsv-Overwrite') == '1'
                )
                targets: list[str] = []
                for f in files_list:
                    try:
                        safe_name = _normalize_upload_filename(f.filename or '')
                    except InvalidPrefix:
                        response_code = 400
                        abort(400, 'Invalid prefix')
                    targets.append(f'{full_prefix}{safe_name}')
                # Decide the per-file success status_code BEFORE the upload
                # loop runs — HTMX partials return 200, plain POST returns
                # 201. Emitting per-file means we need this value while still
                # inside the loop (before the response is rendered).
                success_status = 200 if request.headers.get('HX-Request') else 201
                # A single multi-file request must not silently upload two
                # different payloads to the same target key. Browsers often strip
                # directory names, so duplicate basenames can collide here.
                duplicate_targets = sorted({t for t in targets if targets.count(t) > 1})
                if duplicate_targets:
                    response_code = 409
                    for dup in duplicate_targets:
                        _audit_emit_file(ACTION_UPLOAD, dup, 409, 'error')
                    return jsonify({'conflicts': duplicate_targets}), 409
                disallowed_targets = [t for t in targets if not is_allowed(fs3viewer, t)]
                if disallowed_targets:
                    response_code = 403
                    for bad in disallowed_targets:
                        _audit_emit_file(ACTION_UPLOAD, bad, 403, 'error')
                    abort(403, 'Not allowd file extension')
                if not allow_overwrite:
                    conflicts = [t for t in targets if fs3viewer.is_exists(t)]
                    if conflicts:
                        response_code = 409
                        for conflict in conflicts:
                            _audit_emit_file(ACTION_UPLOAD, conflict, 409, 'error')
                        return jsonify({'conflicts': conflicts}), 409
                for f, target in zip(files_list, targets, strict=True):
                    f.filename = target
                    try:
                        fs3viewer.add_one(f, f.filename)
                    except Exception as e:
                        # Already-uploaded files have their ok rows; this
                        # file gets an error row; remaining files are left
                        # un-emitted (atomic "where did the request stop?"
                        # trace). The helper sets the sentinel so the outer
                        # finally fallback stays silent.
                        _audit_emit_file(ACTION_UPLOAD, target, 500, 'error', exc=e)
                        raise
                    _audit_emit_file(ACTION_UPLOAD, target, success_status, 'ok')
                # upload: stay on the same prefix the user was viewing.
                listing_prefix = raw_prefix
            if request.headers.get('HX-Request'):
                current_search = request.form.get('search', '')
                prefixes, contents, next_token = fs3viewer.find(
                    prefix=listing_prefix,
                    search=current_search or None,
                    cache_identity=getattr(g, 'FSV_AUTH_EMAIL', None),
                )
                # FS3V_TITLE/LOGO/UPLOAD_TYPE/OBJECT_HOSTNAME come from the
                # blueprint context processor — keep request-specific data
                # (listing + current_prefix) here.
                response_code = 200
                return render_template(
                    '_file_list.html',
                    FS3V_CONTENTS=contents,
                    FS3V_PREFIXES=prefixes,
                    FS3V_NEXT_TOKEN=next_token,
                    current_prefix=listing_prefix,
                    current_search=current_search,
                ), 200
            response_code = 201
            return {}, 201

        elif request.method == "GET":
            """
            prefix: encoded
            search: decoded
            """
            # args
            starting_token: str | None = request.args.get('starting_token')
            search = request.args.get('search')
            requested_page = int(request.args.get('page', 1))
            if not starting_token or starting_token == 'None':
                starting_token = None

            fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
            max_items = fs3viewer.max_items
            max_pages = fs3viewer.max_pages
            try:
                prefix, full_prefix = _normalize_prefix_key(
                    fs3viewer,
                    request.args.get('prefix', ''),
                )
                audit_key = full_prefix
                _redirect = _enforce_auth(fs3viewer_for_auth, ACTION_LIST, full_prefix)
                if _redirect is not None and not isinstance(_redirect, str):
                    g.FSV_AUDIT_EMITTED = True
                    return _redirect
                if prefix:
                    prefixes, contents, next_token = fs3viewer.find(
                        prefix=prefix,
                        starting_token=starting_token,
                        max_items=max_items * max_pages,
                        search=search,
                        cache_identity=getattr(g, 'FSV_AUTH_EMAIL', None),
                    )
                else:
                    prefixes, contents, next_token = fs3viewer.find(
                        starting_token=starting_token,
                        max_items=max_items * max_pages,
                        search=search,
                        cache_identity=getattr(g, 'FSV_AUTH_EMAIL', None),
                    )
            except InvalidPrefix:
                response_code = 400
                abort(400, 'Invalid prefix')
            content_pages = [
                contents[i:i + max_items] for i in range(
                    0,
                    len(contents),
                    max_items,
                )
            ]
            total_pages = len(content_pages)
            current_page = 1 if total_pages == 0 else min(max(requested_page, 1), total_pages)

            # HTMX partial swap returns only the inner #file-list fragment;
            # full-page navigation returns the layout-wrapped page.
            template = (
                '_file_list.html'
                if request.headers.get('HX-Request')
                else 'files.html'
            )
            # Branding / upload_type / object_hostname / auth widget data are
            # injected by the blueprint context processor.
            response_code = 200
            return render_template(
                template,
                FS3V_CONTENTS=content_pages[current_page - 1] if content_pages else [],
                FS3V_PREFIXES=prefixes,
                FS3V_NEXT_TOKEN=next_token,
                current_prefix=prefix,
                current_search=search or '',
                current_page=current_page,
                total_pages=total_pages,
            )
    except HTTPException as e:
        response_code = e.code or response_code
        audit_exc = e
        raise
    except Exception as e:
        response_code = 500
        audit_exc = e
        raise
    finally:
        # Per-file paths (POST upload loop / duplicate / disallowed /
        # conflict) set the sentinel through ``_audit_emit_file``. This
        # block only fires for the "no file iterated" cases — GET list,
        # mkdir-only, invalid prefix, and the auth-denied short-circuit
        # which also sets the sentinel itself.
        if not getattr(g, 'FSV_AUDIT_EMITTED', False):
            audit_emit(
                action=action,
                namespace=getattr(g, 'BUCKET_NAMESPACE', None),
                key=audit_key,
                user=getattr(g, 'FSV_AUTH_EMAIL', None) or 'anonymous',
                result='ok' if response_code < 400 else 'error',
                status_code=response_code,
                exc=audit_exc,
            )
            g.FSV_AUDIT_EMITTED = True


@auth_blueprint.route("/login")
def login() -> Any:
    """Kick off the Google OAuth dance. Returns 404 when no viewer on
    this app has Google configured — the route exists app-wide, but
    the flow isn't enabled.
    """
    if not _any_oauth_configured():
        abort(404)
    from ..auth.google import login as _login
    return _login()


@auth_blueprint.route("/callback")
def callback() -> Any:
    """Google OAuth redirect target. App-level (not namespaced) so the
    deployer registers a single redirect URI in Google Console even when
    the app hosts multiple FlaskS3Viewer namespaces.
    """
    if not _any_oauth_configured():
        abort(404)
    from ..auth.google import auth_callback as _cb
    return _cb()


@auth_blueprint.route("/logout")
def logout() -> Any:
    """Drop the session marker. Available whenever any viewer on the
    app has auth wired up (Google or a custom auth_callback).
    """
    if not _any_auth_enabled():
        abort(404)
    from ..auth.google import logout as _logout
    return _logout()


@blueprint.context_processor
def utility_processor() -> dict:
    def list_append(lst: list, k: Any) -> list:
        if k:
            if k not in lst:
                lst.append(k)
        return lst

    def split(key: str, needle: str = '/') -> list:
        if key:
            return key.split(needle)
        return []

    def unquote_plus(key: str) -> str:
        return urllib.parse.unquote_plus(key)

    def humansize(n: Any) -> str:
        if n is None or n == '':
            return ''
        try:
            size = float(n)
        except (TypeError, ValueError):
            return str(n)
        if size < 1024:
            return f"{int(size)} B"
        for unit in ('KB', 'MB', 'GB', 'TB'):
            size /= 1024
            if size < 1024:
                return f"{size:.1f} {unit}"
        return f"{size:.1f} PB"

    def format_datetime(value: Any) -> str:
        if value is None:
            return ''
        target_timezone = None
        if hasattr(g, 'BUCKET_NAMESPACE'):
            viewer = current_app.extensions.get(NAMESPACE, {}).get(g.BUCKET_NAMESPACE)
            target_timezone = getattr(viewer, 'display_timezone', None)
        if not target_timezone or not hasattr(value, 'astimezone'):
            return str(value)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(target_timezone).strftime('%Y-%m-%d %H:%M:%S %Z')

    # Per-namespace state for the header — branding + auth widget.
    # Both used to be re-passed by each individual ``render_template``
    # call, which made it easy to forget (e.g. the listing GET handler
    # dropped ``FS3V_TITLE`` for a while). Centralising here means every
    # template — full page, HTMX partial, error — sees the same values.
    user_email: str | None = None
    auth_enabled = False
    google_configured = False
    title: str | None = None
    logo_url: str | None = None
    upload_type: str | None = None
    object_hostname: str | None = None
    object_base_path: str | None = None
    if hasattr(g, 'BUCKET_NAMESPACE'):
        viewer = current_app.extensions.get(NAMESPACE, {}).get(g.BUCKET_NAMESPACE)
        if viewer is not None:
            title = getattr(viewer, 'title', None)
            logo_url = getattr(viewer, 'logo_url', None)
            upload_type = getattr(viewer, 'upload_type', None)
            object_hostname = getattr(viewer, 'object_hostname', None)
            object_base_path = getattr(viewer, '_base_path', None)
            auth_enabled = bool(getattr(viewer, 'auth_enabled', False))
            google_configured = bool(getattr(viewer, 'google_client_id', None))
            if auth_enabled:
                try:
                    user_email = viewer.auth_callback(request)
                except Exception:  # pragma: no cover - deployer callback safety
                    user_email = None
    user_avatar: str | None = None
    if user_email:
        try:
            from ..auth.google import session_avatar_url
            user_avatar = session_avatar_url()
        except Exception:  # pragma: no cover - optional auth helper safety
            user_avatar = None
    visible_namespaces: list[dict[str, str]] = []
    current_namespace = getattr(g, 'BUCKET_NAMESPACE', None)
    registry = current_app.extensions.get(NAMESPACE, {})
    if current_namespace and registry:
        active_viewer = registry.get(current_namespace)
        allowed_namespaces: set[str] | None = None
        callback = getattr(active_viewer, 'visible_namespaces_callback', None)
        if callback:
            try:
                allowed = callback(user_email, registry)
                allowed_namespaces = {str(ns) for ns in allowed}
            except Exception:  # pragma: no cover - deployer callback safety
                allowed_namespaces = set()
        for namespace, viewer in registry.items():
            if allowed_namespaces is not None and namespace not in allowed_namespaces:
                continue
            visible_namespaces.append({
                'namespace': namespace,
                'title': getattr(viewer, 'title', None) or namespace,
            })

    return dict(
        split=split,
        unquote_plus=unquote_plus,
        list_append=list_append,
        humansize=humansize,
        format_datetime=format_datetime,
        FS3V_TITLE=title,
        FS3V_LOGO_URL=logo_url,
        FS3V_UPLOAD_TYPE=upload_type,
        FS3V_OBJECT_HOSTNAME=object_hostname,
        FS3V_OBJECT_BASE_PATH=object_base_path,
        FSV_USER_EMAIL=user_email,
        FSV_USER_AVATAR=user_avatar,
        FSV_AUTH_ENABLED=auth_enabled,
        FSV_GOOGLE_CONFIGURED=google_configured,
        FSV_CURRENT_NAMESPACE=current_namespace,
        FSV_VISIBLE_NAMESPACES=visible_namespaces,
    )
