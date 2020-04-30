import sys

from flask import Flask
from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.aws.ref import Region

app = Flask(__name__)

# For test, disable template caching
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# FlaskS3Viewer Init
s3viewer = FlaskS3Viewer(
    app, # Flask app
    namespace='flask-s3-viewer', # namespace be unique
    template_namespace='mdl', # set template
    object_hostname='http://flask-s3-viewer.com', # file's hostname
    allowed_extensions={}, # allowed extension
    config={ # Bucket configs and else
        'profile_name': 'PROFILE_NAME',
        'access_key': None,
        'secret_key': None,
        'region_name': Region.SEOUL.value,
        'endpoint_url': None,
        'bucket_name': 'BUCKET_NAME',
        'cache_dir': '/tmp/flask_s3_viewer',
        'use_cache': True,
        'ttl': 86400,
    }
)

# Init another one
s3viewer.add_new_one(
    namespace='example',
    object_hostname='http://example.com',
    config={
        'profile_name': 'PROFILE_NAME',
        'region_name': Region.SEOUL.value,
        'bucket_name': 'BUCKET_NAME'
    }
)

# You can see registerd configs
# print(s3viewer.FLASK_S3_VIEWER_BUCKET_CONFIGS)

# You can use boto3's session and client if you want
# print(FlaskS3Viewer.get_boto_client(FS3V_NAMESPACE))
# print(FlaskS3Viewer.get_boto_session(FS3V_NAMESPACE))

# Apply FlaskS3Viewer blueprint
s3viewer.register()

@app.route('/index')
def index ():
    return 'Your app index page'

# Usage: python example.py test (run debug mode)
if __name__ == '__main__':
    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            debug = True
    app.run(debug=debug, port=3000)

