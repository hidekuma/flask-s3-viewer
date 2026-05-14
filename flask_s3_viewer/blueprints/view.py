import os
import unicodedata
import urllib
import urllib.parse
from collections.abc import Iterable
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

from .. import APP_TEMPLATE_FOLDER, FlaskS3Viewer
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
        # client (the dominant case) needs.
        if request.method == 'GET' and fs3viewer.google_client_id:
            return redirect(url_for(
                'flask_s3_viewer_auth.login',
                next=request.url,
            ))
        abort(401, 'Authentication required.')
    if not fs3viewer.permission_callback(email, action, g.BUCKET_NAMESPACE, key):
        abort(403, 'Forbidden.')
    return email


def require(action: str) -> Any:
    """Decorator: enforce ``_enforce_auth`` before running the route.

    The decorated handler receives the regular Flask URL kwargs unchanged.
    ``action`` is one of the ACTION_* constants from ``flask_s3_viewer.auth``.
    """
    def deco(fn: Any) -> Any:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            viewer = _get_viewer(g.BUCKET_NAMESPACE)
            maybe_redirect = _enforce_auth(viewer, action, kwargs.get('key'))
            # `_enforce_auth` may have returned a redirect response (Google login).
            if maybe_redirect is not None and not isinstance(maybe_redirect, str):
                return maybe_redirect
            return fn(*args, **kwargs)
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
        key = urllib.parse.unquote_plus(key)
        fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
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
@require(ACTION_PRESIGN)
def files_presign() -> Any:
    prefix = request.form.get('prefix', '')
    prefix = urllib.parse.unquote_plus(prefix)
    fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
    try:
        prefix = fs3viewer.prefixer(prefix)
    except InvalidPrefix:
        abort(400, 'Invalid prefix')
    file_list = request.form.get("file_list")
    rtns: list[dict] = []
    if file_list:
        for f in file_list.split(','):
            try:
                filename = os.path.join(prefix, f)
                if fs3viewer.is_exists(filename):
                    rtns.append({'status_code': 409})
                elif not is_allowed(fs3viewer, filename):
                    rtns.append({'status_code': 403})
                else:
                    r = fs3viewer.post_presign(filename)
                    rtns.append(r)
            except Exception:
                rtns.append({'status_code': 500})

    fs3viewer.purge(prefix)

    return jsonify(rtns), 200


@blueprint.route("/files", methods=['GET', 'POST'])
def files() -> Any:
    # files() carries two distinct actions (LIST vs UPLOAD) so it can't
    # use the @require decorator wholesale — enforce per branch.
    fs3viewer_for_auth = _get_viewer(g.BUCKET_NAMESPACE)
    _auth_action = ACTION_UPLOAD if request.method == 'POST' else ACTION_LIST
    _redirect = _enforce_auth(fs3viewer_for_auth, _auth_action)
    if _redirect is not None and not isinstance(_redirect, str):
        return _redirect
    if request.method == "POST":
        """
        prefix: encoded
        files[].f.filename: decoded
        prefixer(): 탐색 및 폴더생성시
        """
        # form
        raw_prefix = request.form.get('prefix', '')
        raw_prefix = urllib.parse.unquote_plus(raw_prefix)
        files_list: Iterable[FileStorage] = request.files.getlist("files[]")
        fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
        try:
            full_prefix = fs3viewer.prefixer(raw_prefix)
        except InvalidPrefix:
            abort(400, 'Invalid prefix')
        if not files_list and full_prefix:
            if fs3viewer.is_exists(full_prefix):
                abort(409, 'Already exists.')
            if not fs3viewer.mkdir(full_prefix):
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
            targets = [
                os.path.join(full_prefix, f.filename or "")
                for f in files_list
            ]
            if not allow_overwrite:
                conflicts = [t for t in targets if fs3viewer.is_exists(t)]
                if conflicts:
                    return jsonify({'conflicts': conflicts}), 409
            for f, target in zip(files_list, targets, strict=True):
                f.filename = target
                if not is_allowed(fs3viewer, f.filename):
                    abort(403, 'Not allowd file extension')
                fs3viewer.add_one(f, f.filename)
            # upload: stay on the same prefix the user was viewing.
            listing_prefix = raw_prefix
        if request.headers.get('HX-Request'):
            prefixes, contents, next_token = fs3viewer.find(prefix=listing_prefix)
            return render_template(
                '_file_list.html',
                FS3V_UPLOAD_TYPE=fs3viewer.upload_type,
                FS3V_CONTENTS=contents,
                FS3V_PREFIXES=prefixes,
                FS3V_NEXT_TOKEN=next_token,
                FS3V_OBJECT_HOSTNAME=fs3viewer.object_hostname,
                FS3V_TITLE=fs3viewer.title,
                FS3V_LOGO_URL=fs3viewer.logo_url,
                current_prefix=listing_prefix,
            ), 200
        return {}, 201

    elif request.method == "GET":
        """
        prefix: encoded
        search: decoded
        """
        # args
        prefix = request.args.get('prefix', '')
        prefix = urllib.parse.unquote_plus(prefix)
        starting_token: str | None = request.args.get('starting_token')
        search = request.args.get('search')
        page = int(request.args.get('page', 1)) - 1
        if not starting_token or starting_token == 'None':
            starting_token = None

        fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
        max_items = fs3viewer.max_items
        max_pages = fs3viewer.max_pages
        try:
            if prefix:
                prefixes, contents, next_token = fs3viewer.find(
                    prefix=prefix,
                    starting_token=starting_token,
                    max_items=max_items * max_pages,
                    search=search,
                )
            else:
                prefixes, contents, next_token = fs3viewer.find(
                    starting_token=starting_token,
                    max_items=max_items * max_pages,
                    search=search,
                )
        except InvalidPrefix:
            abort(400, 'Invalid prefix')
        content_pages = [
            contents[i:i + max_items] for i in range(
                0,
                len(contents),
                max_items,
            )
        ]

        # HTMX partial swap returns only the inner #file-list fragment;
        # full-page navigation returns the layout-wrapped page.
        template = (
            '_file_list.html'
            if request.headers.get('HX-Request')
            else 'files.html'
        )
        return render_template(
            template,
            FS3V_UPLOAD_TYPE=fs3viewer.upload_type,
            FS3V_CONTENTS=content_pages[page] if content_pages else [],
            FS3V_PREFIXES=prefixes,
            FS3V_NEXT_TOKEN=next_token,
            FS3V_OBJECT_HOSTNAME=fs3viewer.object_hostname,
            current_prefix=prefix,
        )


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

    return dict(
        split=split,
        unquote_plus=unquote_plus,
        list_append=list_append,
        humansize=humansize,
    )
