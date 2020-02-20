import urllib

from werkzeug.wsgi import FileWrapper
from flask import Blueprint, Response, request, redirect, render_template, current_app, url_for

from ..aws.s3 import AWSS3Client

NAMESPACE = 'flask_s3up'

blueprint = Blueprint(NAMESPACE, __name__ , template_folder=f'./{NAMESPACE}/templates/{NAMESPACE}', static_folder='static')

@blueprint.route("/delete", methods=['DELETE'])
def delete():
    key = request.args.get('key')
    if key:
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        s3_client.delete_fileobj(
            current_app.config['BUCKET'],
            key
        )

@blueprint.route("/files/<path:key>", methods=['GET', 'DELETE'])
def files_download(key):
    print(request.method)
    if request.method == "GET":
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        r, obj = s3_client.get_object(
            current_app.config['BUCKET'],
            key
        )
        if r:
            rv = Response(
                FileWrapper(obj.get('Body')),
                direct_passthrough=True,
                mimetype=obj['ContentType']
            )
            filenames = {'filename': key}
            rv.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            rv.headers['Pragma'] = 'no-cache'
            rv.headers['Expires'] = '0'
            rv.headers.set('Content-Disposition', 'attachment', **filenames)
            return rv
    elif request.method == 'DELETE':
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        s3_client.delete_fileobj(
            current_app.config['BUCKET'],
            key
        )

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
        for f in files:
            if prefix:
                if prefix.endswith('/'):
                    f.filename = f'{prefix}{f.filename}'
                else:
                    f.filename = f'{prefix}/{f.filename}'
            s3_client.upload_fileobj(
                current_app.config['BUCKET'],
                f,
                f.filename
            )
        return {}, 201

        # return redirect(url_for(f'{NAMESPACE}.files', prefix=prefix))

    elif request.method == "GET":
        prefix = request.args.get('prefix', '')
        prefix = urllib.parse.unquote_plus(prefix)
        starting_token = request.args.get('starting_token')
        search = request.args.get('search')

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


