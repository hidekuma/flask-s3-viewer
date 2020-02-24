import urllib
import unicodedata
import os

from werkzeug.wsgi import FileWrapper
from werkzeug.urls import url_quote
from flask import Blueprint, Response, request, render_template, current_app

from ..aws.s3 import AWSS3Client

NAMESPACE = 'flask_s3up'

blueprint = Blueprint(NAMESPACE, __name__ , template_folder=f'./{NAMESPACE}/templates/{NAMESPACE}', static_folder='static')

def get_s3_instance():
    return AWSS3Client(
        profile_name=current_app.config['S3UP_PROFILE'],
        use_cache=current_app.config['S3UP_USE_CACHING'],
        cache_dir=current_app.config['S3UP_CACHE_DIR']
    )

@blueprint.route("/files/<path:key>", methods=['GET', 'DELETE'])
def files_download(key):
    # key = urllib.parse.unquote_plus(key)
    if request.method == "GET":
        s3_client = get_s3_instance()
        r, obj = s3_client.get_object(
            current_app.config['S3UP_BUCKET'],
            key
        )
        if r:
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
    elif request.method == 'DELETE':
        s3_client = get_s3_instance()
        if key.endswith('/'):
            s3_client.delete_fileobjs(
                current_app.config['S3UP_BUCKET'],
                get_all_of_objects(key)
            )
        else:
            s3_client.delete_fileobj(
                current_app.config['S3UP_BUCKET'],
                key
            )
        return {}, 204

def get_all_of_objects(prefix):
    s3_client = get_s3_instance()
    next_token=None
    while True:
        prefixes, contents, next_token = s3_client.list_bucket_objects_with_pager(
            current_app.config['S3UP_BUCKET'],
            prefix=prefix,
            delimiter='',
            starting_token=next_token
        )
        # next_token = pages.build_full_result().get('NextToken', None)
        # contents = pages.search('Contents') # generator
        for item in contents:
            if item:
                key = urllib.parse.unquote_plus(item['Key'])
                yield key
        if not next_token:
            break


@blueprint.route("/upload", methods=['GET'])
def upload():
    return render_template(f'{NAMESPACE}/upload.html')

@blueprint.route("/files", methods=['GET', 'POST'])
def files():
    if request.method == "POST":
        prefix = request.form.get('prefix', '')
        prefix = urllib.parse.unquote(prefix)
        files = request.files.getlist("files[]")
        s3_client = get_s3_instance()
        if prefix:
            if not prefix.endswith('/'):
               prefix = f'{prefix}/'
        if not files and prefix:
            s3_client.put_object(
                current_app.config['S3UP_BUCKET'],
                prefix,
                mkdir=True
            )
        else:
            for f in files:
                f.filename = f'{prefix}{f.filename}'
                s3_client.upload_fileobj(
                    current_app.config['S3UP_BUCKET'],
                    f,
                    f.filename
                )
        return {}, 201

    elif request.method == "GET":
        prefix = request.args.get('prefix', '')
        prefix = urllib.parse.unquote_plus(prefix)
        starting_token = request.args.get('starting_token')
        search = request.args.get('search')
        if not starting_token:
            starting_token = None

        s3_client = get_s3_instance()
        if prefix:
            prefixes, contents, next_token = s3_client.list_bucket_objects_with_pager(
                current_app.config['S3UP_BUCKET'],
                prefix=prefix,
                starting_token=starting_token,
                search=search
            )
        else:
            prefixes, contents, next_token = s3_client.list_bucket_objects_with_pager(
                current_app.config['S3UP_BUCKET'],
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
    def unquote_plus(key):
        return urllib.parse.unquote_plus(key)
    return dict(unquote_plus=unquote_plus)


