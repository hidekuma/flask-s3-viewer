import urllib
import unicodedata
import os

from werkzeug.wsgi import FileWrapper
from werkzeug.urls import url_quote
from flask import Response, request, render_template, current_app
from .. import get_s3_client
from .. import blueprint
from .. import NAMESPACE
from .. import FLASK_S3UP_BUCKET_PATH_CONFIGS

@blueprint.route("/files/<path:key>", methods=['GET'])
def files_download(key):
    if request.method == "GET":
        """
        key: encoded
        """
        key = urllib.parse.unquote_plus(key)
        s3_client = get_s3_client()
        obj = s3_client.get_object(key)
        # TODO: if obj is none
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

@blueprint.route("/files/<path:key>", methods=['DELETE'])
def files_delete(key):
    if request.method == 'DELETE':
        """
        key: decoded
        """
        s3_client = get_s3_client()
        s3_client.delete_objects(
            key
        )
        return {}, 204

@blueprint.route("/files", methods=['GET', 'POST'])
def files():
    print('----')
    print(request.url_rule.rule)
    print(FLASK_S3UP_BUCKET_PATH_CONFIGS)
    print('----')
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
        s3_client = get_s3_client()
        prefix = s3_client.prefixer(prefix)
        if not files and prefix:
            is_exists = s3_client.is_exists(prefix)
            if is_exists:
                raise Exception('Already exists')
            s3_client.put_object(prefix, mkdir=True)
            return {}, 201
        else:
            for f in files:
                f.filename = f'{prefix}{f.filename}'
                s3_client.upload_object(f, f.filename)
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
        if not starting_token:
            starting_token = None

        s3_client = get_s3_client()
        if prefix:
            prefixes, contents, next_token = s3_client.list_objects(
                prefix=prefix,
                starting_token=starting_token,
                search=search
            )
        else:
            prefixes, contents, next_token = s3_client.list_objects(
                starting_token=starting_token,
                search=search
            )


        return render_template(
            f'{NAMESPACE}/files.html',
            contents=contents,
            prefixes=prefixes,
            next_token=next_token,
            object_hostname=current_app.config['S3UP_OBJECT_HOSTNAME']
        )


@blueprint.context_processor
def utility_processor():
    def split(key):
        return map(lambda k: f'{k}/', key.split('/'))

    def unquote_plus(key):
        return urllib.parse.unquote_plus(key)

    return dict(
        split=split,
        unquote_plus=unquote_plus
    )
