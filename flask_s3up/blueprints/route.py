import urllib
from flask import Blueprint, request, redirect, render_template, current_app, url_for
from ..aws.s3 import AWSS3Client

NAMESPACE = 'flask_s3up'

blueprint = Blueprint(NAMESPACE, __name__ , template_folder=f'./{NAMESPACE}/templates/{NAMESPACE}')

@blueprint.route("/upload", methods=['GET'])
def upload():
    return render_template(f'{NAMESPACE}/upload.html')

@blueprint.route("/files", methods=['GET', 'POST'])
def files():
    if request.method == "POST":
        current_path = request.form.get('current_path', None)
        print(current_path, type(current_path))
        files = request.files.getlist("files[]")
        s3_client = AWSS3Client(profile_name=current_app.config['PROFILE'])
        for f in files:
            if current_path:
                f.filename = f'{current_path}{f.filename}'
            s3_client.upload_fileobj(
                current_app.config['BUCKET'],
                f,
                f.filename
            )

        return redirect(url_for(f'{NAMESPACE}.files', prefix=current_path))

    elif request.method == "GET":
        prefix = request.args.get('prefix')
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


