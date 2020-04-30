from flask import Flask
from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.aws.ref import Region

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(asctime)s: %(message)s'
)

app = Flask(__name__)

# For test, disable template caching
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# FlaskS3Viewer Init
FS3V_NAMESPACE = 'flask-s3-viewer'
s3viewer = FlaskS3Viewer(
    app, # Flask app
    namespace=FS3V_NAMESPACE, # namespace be unique
    template_namespace='mdl',
    object_hostname='http://flask-s3-viewer.com', # file's hostname
    config={ # Bucket configs and else
        'profile_name': 'test',
        'access_key': None,
        'secret_key': None,
        'region_name': Region.SEOUL.value,
        'endpoint_url': None,
        'bucket_name': 'hwjeongtest',
        'cache_dir': '/tmp/flask_s3_viewer',
        'use_cache': True,
        'ttl': 86400,
    }
)

# Init another one
s3viewer.add_new_one(
    object_hostname='http://namespace2.com',
    namespace='np2', # namespace be unique
    upload_type='presign',
    config={
        'profile_name': 'test',
        'region_name': Region.SEOUL.value,
        'bucket_name': 'hwjeongtest'
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
    app.run(debug=True, port=3000)

