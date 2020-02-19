from flask import Blueprint, request, send_file, Response, redirect, render_template
from werkzeug.wsgi import FileWrapper
from ..aws.s3 import AWSS3Client

NAMESPACE = 'flask_s3up_api'

blueprint = Blueprint(NAMESPACE, __name__ )


@blueprint.route("/")
@blueprint.route("/index")
def index():
    return render_template(f'{NAMESPACE}/index.html')

@blueprint.route("/upload")
def upload():
    return render_template(f'{NAMESPACE}/upload.html')

@blueprint.route("/files")
def files():
    s3_client = AWSS3Client(profile_name='hwjeong')
    pages = s3_client.list_bucket_objects_with_pager('hwjeong')

    next_token = pages.build_full_result().get('NextToken', None)
    contents = pages.search('Contents') # generator

    return render_template(f'{NAMESPACE}/files.html', data=contents, next_token=next_token)
