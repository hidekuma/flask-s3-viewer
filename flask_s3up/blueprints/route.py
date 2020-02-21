import urllib
import unicodedata
import os

from werkzeug.wsgi import FileWrapper
from werkzeug.urls import url_quote
from flask import Blueprint, Response, request, render_template, current_app

from ..aws.s3 import AWSS3Client

NAMESPACE = 'flask_s3up'

blueprint = Blueprint(NAMESPACE, __name__ , template_folder=f'./{NAMESPACE}/templates/{NAMESPACE}', static_folder='static')

@blueprint.route("/files/<path:key>", methods=['GET', 'DELETE'])
def files_download(key):
    # key = urllib.parse.unquote_plus(key)
    if request.method == "GET":
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        r, obj = s3_client.get_object(
            current_app.config['BUCKET'],
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
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        if key.endswith('/'):
            s3_client.delete_fileobjs(
                current_app.config['BUCKET'],
                get_all_of_objects(key)
            )
        else:
            s3_client.delete_fileobj(
                current_app.config['BUCKET'],
                key
            )
        return {}, 204

def get_all_of_objects(prefix):
    s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
    next_token=None
    # objects = []
    while True:
        pages = s3_client.list_bucket_objects_with_pager(
            current_app.config['BUCKET'],
            prefix=prefix,
            delimiter='',
            starting_token=next_token
        )
        next_token = pages.build_full_result().get('NextToken', None)
        contents = pages.search('Contents') # generator
        for item in contents:
            if item:
                key = urllib.parse.unquote_plus(item['Key'])
                # objects.append(key)
                yield key
        # if objects:
            # r = s3.delete_fileobjs(bucket, objects)
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
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        if prefix:
            if not prefix.endswith('/'):
               prefix = f'{prefix}/'
        if not files and prefix:
            s3_client.put_object(
                current_app.config['BUCKET'],
                prefix,
                mkdir=True
            )
        else:
            for f in files:
                f.filename = f'{prefix}{f.filename}'
                s3_client.upload_fileobj(
                    current_app.config['BUCKET'],
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

        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        if prefix:
            pages = s3_client.list_bucket_objects_with_pager(
                current_app.config['BUCKET'],
                prefix=prefix,
                starting_token=starting_token
            )
        else:
            pages = s3_client.list_bucket_objects_with_pager(
                current_app.config['BUCKET'],
                starting_token=starting_token
            )

        next_token = pages.build_full_result().get('NextToken', None)
        if search:
            contents = pages.search(f'Contents[?Size > `0` && contains(Key, `{search}`)]') # generator
            prefixes = pages.search(f'CommonPrefixes[?contains(Prefix, `{search}`)]') # generator
        else:
            contents = pages.search('Contents[?Size > `0`]') # generator
            prefixes = pages.search('CommonPrefixes') # generator

        return render_template(
            f'{NAMESPACE}/files.html',
            contents=contents,
            prefixes=prefixes,
            next_token=next_token,
        )

@blueprint.context_processor
def utility_processor():
    def unquote_plus(key):
        return urllib.parse.unquote_plus(key)
    return dict(unquote_plus=unquote_plus)


