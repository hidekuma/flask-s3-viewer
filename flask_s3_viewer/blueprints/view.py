import os
import unicodedata
import urllib
import urllib.parse
from collections.abc import Iterable
from typing import Any, Tuple, Union
from urllib.parse import quote as url_quote

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    g,
    jsonify,
    render_template,
    request,
)
from werkzeug.datastructures import FileStorage

from .. import APP_TEMPLATE_FOLDER, FlaskS3Viewer
from ..config import NAMESPACE
from ..errors import InvalidPrefix

blueprint = Blueprint(
    NAMESPACE,
    __name__,
    template_folder=APP_TEMPLATE_FOLDER,
    static_folder='static',
    static_url_path='flasks3viewerassets',
    url_prefix='/<path:BUCKET_NAMESPACE>',
)


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
def files_download(key: str) -> Any:
    if request.method == "GET":
        """
        key: encoded
        """
        key = urllib.parse.unquote_plus(key)
        fs3viewer = _get_viewer(g.BUCKET_NAMESPACE)
        obj = fs3viewer.find_one(key)
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
                    'filename*': "UTF-8''{}".format(url_quote(key)),
                }
            else:
                filenames = {'filename': key_bytes.decode('utf-8')}
            # boto3 응답의 'Body' (StreamingBody)는 file-like / iterable 이므로
            # Werkzeug WSGI 헬퍼 없이도 Response가 직접 chunk 스트리밍을 처리한다.
            rv = Response(
                obj.get('Body', b''),
                direct_passthrough=True,
                mimetype=obj['ContentType'],
            )
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
def files_delete(key: str) -> Tuple[str, int]:
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
        starting_token: Union[str, None] = request.args.get('starting_token')
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
