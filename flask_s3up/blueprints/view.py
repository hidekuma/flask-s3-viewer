import urllib
import unicodedata
import os

from werkzeug.wsgi import FileWrapper
from werkzeug.urls import url_quote
from flask import Response, request, render_template, Blueprint, g, abort
from .. import FlaskS3Up, FLASK_S3UP_NAMESPACE, FLASK_S3UP_TEMPLATE_NAMESPACE

blueprint = Blueprint(
    FLASK_S3UP_NAMESPACE,
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='flasks3upassets',
    url_prefix='/<path:FLASK_S3UP_BUCKET_NAMESPACE>'
)

def is_allowed(fs3up, filename):
    if fs3up.allowed_extensions:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in fs3up.allowed_extensions
    return True

@blueprint.url_defaults
def add_division(endpoint, values):
    values.setdefault(
        'FLASK_S3UP_BUCKET_NAMESPACE',
        g.FLASK_S3UP_BUCKET_NAMESPACE
    )

@blueprint.url_value_preprocessor
def pull_division(endpoint, values):
    g.FLASK_S3UP_BUCKET_NAMESPACE = values.pop('FLASK_S3UP_BUCKET_NAMESPACE')

@blueprint.route("/files/<path:key>", methods=['GET'])
def files_download(key):
    if request.method == "GET":
        """
        key: encoded
        """
        key = urllib.parse.unquote_plus(key)
        fs3up = FlaskS3Up.get_instance(g.FLASK_S3UP_BUCKET_NAMESPACE)
        obj = fs3up.find_one(key)
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
                filenames = {'filename': key}
            rv = Response(
                FileWrapper(obj.get('Body')),
                direct_passthrough=True,
                mimetype=obj['ContentType']
            )
            rv.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            rv.headers['Pragma'] = 'no-cache'
            rv.headers['Expires'] = '0'
            rv.headers.set('Content-Disposition', 'attachment', **filenames)
            return rv
        else:
            g.setdefault('template_namespace', FLASK_S3UP_TEMPLATE_NAMESPACE)
            return render_template(
                f'{FLASK_S3UP_TEMPLATE_NAMESPACE}/error.html',
                g=g,
                message="Can't not found resource.",
                code=404
            ), 404

@blueprint.route("/files/<path:key>", methods=['DELETE'])
def files_delete(key):
    if request.method == 'DELETE':
        """
        key: decoded
        """
        fs3up = FlaskS3Up.get_instance(g.FLASK_S3UP_BUCKET_NAMESPACE)
        try:
            fs3up.remove(key)
            return '', 204
        except Exception:
            abort(500)

@blueprint.route("/files", methods=['GET', 'POST'])
def files():
    if request.method == "POST":
        """
        prefix: encoded
        files[].f.filename: decoded
        prefixer(): 탐색 및 폴더생성시
        """
        # form
        prefix = request.form.get('prefix', '')
        prefix = urllib.parse.unquote_plus(prefix)
        files = request.files.getlist("files[]")
        fs3up = FlaskS3Up.get_instance(g.FLASK_S3UP_BUCKET_NAMESPACE)
        prefix = fs3up.prefixer(prefix)
        if not files and prefix:
            if fs3up.is_exists(prefix):
                abort(409, 'Already exists.')
            if fs3up.put_one(prefix, mkdir=True):
                return {}, 201
            else:
                abort(500)
        else:
            for f in files:
                f.filename = f'{prefix}{f.filename}'
                if fs3up.is_exists(f.filename):
                    abort(409, 'Already exists.')
                if not is_allowed(fs3up, f.filename):
                    abort(403, 'Already exists.')
                fs3up.add_one(f, f.filename)
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

        fs3up = FlaskS3Up.get_instance(g.FLASK_S3UP_BUCKET_NAMESPACE)
        max_items = fs3up.max_items
        max_pages = fs3up.max_pages
        if prefix:
            prefixes, contents, next_token = fs3up.find(
                prefix=prefix,
                starting_token=starting_token,
                max_items=max_items*max_pages,
                search=search
            )
        else:
            prefixes, contents, next_token = fs3up.find(
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

        g.setdefault('template_namespace', FLASK_S3UP_TEMPLATE_NAMESPACE)
        return render_template(
            f'{FLASK_S3UP_TEMPLATE_NAMESPACE}/files.html',
            g=g,
            max_pages=max_pages,
            pages=len(content_pages),
            contents=content_pages[page] if content_pages else [],
            prefixes=prefixes,
            next_token=next_token,
            object_hostname=fs3up.object_hostname
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
