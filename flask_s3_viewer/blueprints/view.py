from collections.abc import Iterable
from typing import Any
import urllib
import urllib.parse
import unicodedata
import os

from werkzeug.datastructures import FileStorage
from werkzeug.wsgi import FileWrapper
from urllib.parse import quote as url_quote
from flask import Response, request, render_template, Blueprint, g, abort, jsonify
from .. import FlaskS3Viewer, APP_TEMPLATE_FOLDER
from ..config import NAMESPACE

blueprint = Blueprint(
    NAMESPACE,
    __name__,
    template_folder=APP_TEMPLATE_FOLDER,
    static_folder='static',
    static_url_path='flasks3viewerassets',
    url_prefix='/<path:BUCKET_NAMESPACE>'
)


def is_allowed(fs3viewer, filename):
    if fs3viewer.allowed_extensions:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in fs3viewer.allowed_extensions
    return True


@blueprint.url_defaults
def add_division(endpoint, values):
    values.setdefault(
        'BUCKET_NAMESPACE',
        g.BUCKET_NAMESPACE
    )


@blueprint.url_value_preprocessor
def pull_division(endpoint, values):
    g.BUCKET_NAMESPACE = values.pop('BUCKET_NAMESPACE')


@blueprint.route("/files/<path:key>", methods=['GET'])
def files_download(key) -> Any:
    if request.method == "GET":
        """
        key: encoded
        """
        key = urllib.parse.unquote_plus(key)
        fs3viewer: FlaskS3Viewer = FlaskS3Viewer.get_instance(
            g.BUCKET_NAMESPACE)
        obj = fs3viewer.find_one(key)
        if obj:
            try:
                key = os.path.basename(key).encode('latin-1')
            except UnicodeEncodeError:
                encoded_key = unicodedata.normalize(
                    'NFKD',
                    key
                ).encode('latin-1', 'ignore')
                filenames = {
                    'filename': encoded_key,
                    'filename*': "UTF-8''{}".format(url_quote(key)),
                }
            else:
                filenames = {'filename': key.decode('utf-8')}
            rv = Response(
                FileWrapper(obj.get('Body', '')),
                direct_passthrough=True,
                mimetype=obj['ContentType']
            )
            rv.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            rv.headers['Pragma'] = 'no-cache'
            rv.headers['Expires'] = '0'
            rv.headers.set('Content-Disposition', 'attachment', **filenames)
            return rv
        else:
            return render_template(
                f'{fs3viewer.template_namespace}/error.html',
                FS3V_TEMPLATE_NAMESPACE=fs3viewer.template_namespace,
                FS3V_MESSAGE="Can't not found resource.",
                FS3V_CODE=404
            ), 404


@blueprint.route("/files/<path:key>", methods=['DELETE'])
def files_delete(key) -> Any:
    if request.method == 'DELETE':
        """
        key: decoded
        """
        fs3viewer = FlaskS3Viewer.get_instance(g.BUCKET_NAMESPACE)
        try:
            fs3viewer.remove(key)
            return '', 204
        except Exception:
            abort(500)


@blueprint.route("/files/presign", methods=['POST'])
def files_presign():
    prefix = request.form.get('prefix', '')
    prefix = urllib.parse.unquote_plus(prefix)
    fs3viewer = FlaskS3Viewer.get_instance(g.BUCKET_NAMESPACE)
    prefix = fs3viewer.prefixer(prefix)
    file_list = request.form.get("file_list")
    rtns = []
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
        prefix = request.form.get('prefix', '')
        prefix = urllib.parse.unquote_plus(prefix)
        files: Iterable[FileStorage] = request.files.getlist("files[]")
        fs3viewer = FlaskS3Viewer.get_instance(g.BUCKET_NAMESPACE)
        prefix = fs3viewer.prefixer(prefix)
        if not files and prefix:
            if fs3viewer.is_exists(prefix):
                abort(409, 'Already exists.')
            if fs3viewer.mkdir(prefix):
                return {}, 201
            else:
                abort(500)
        else:
            for f in files:
                f.filename = os.path.join(
                    prefix, f.filename if f.filename else "")
                if fs3viewer.is_exists(f.filename):
                    abort(409, 'Already exists.')
                if not is_allowed(fs3viewer, f.filename):
                    abort(403, 'Not allowd file extension')
                fs3viewer.add_one(f, f.filename)
                return {}, 201

    elif request.method == "GET":
        """
        prefix: encoded
        search: decoded
        """
        # args
        prefix = request.args.get('prefix', '')
        prefix = urllib.parse.unquote_plus(prefix)
        starting_token = request.args.get('starting_token')
        search = request.args.get('search')
        page = int(request.args.get('page', 1)) - 1
        if not starting_token or starting_token == 'None':
            starting_token = None

        fs3viewer = FlaskS3Viewer.get_instance(g.BUCKET_NAMESPACE)
        max_items = fs3viewer.max_items
        max_pages = fs3viewer.max_pages
        if prefix:
            prefixes, contents, next_token = fs3viewer.find(
                prefix=prefix,
                starting_token=starting_token,
                max_items=max_items*max_pages,
                search=search
            )
        else:
            prefixes, contents, next_token = fs3viewer.find(
                starting_token=starting_token,
                max_items=max_items*max_pages,
                search=search
            )
        content_pages = [
            contents[i:i+max_items] for i in range(
                0,
                len(contents),
                max_items
            )
        ]

        return render_template(
            f'{fs3viewer.template_namespace}/files.html',
            FS3V_UPLOAD_TYPE=fs3viewer.upload_type,
            FS3V_TEMPLATE_NAMESPACE=fs3viewer.template_namespace,
            FS3V_MAX_PAGES=max_pages,
            FS3V_PAGES=len(content_pages),
            FS3V_CONTENTS=content_pages[page] if content_pages else [],
            FS3V_PREFIXES=prefixes,
            FS3V_NEXT_TOKEN=next_token,
            FS3V_OBJECT_HOSTNAME=fs3viewer.object_hostname
        )


@blueprint.context_processor
def utility_processor():
    def list_append(l, k):
        if k:
            if k not in l:
                l.append(k)
        return l

    def split(key, needle='/'):
        if key:
            return key.split(needle)
        return []

    def unquote_plus(key):
        return urllib.parse.unquote_plus(key)

    return dict(
        split=split,
        unquote_plus=unquote_plus,
        list_append=list_append
    )
