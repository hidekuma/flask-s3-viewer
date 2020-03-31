from flask import Flask
from flask_s3up import FlaskS3Up
from flask_s3up.aws.ref import Region

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(asctime)s: %(message)s'
)

app = Flask(__name__)

# For test, disable template caching
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# FlaskS3Up Init
S3UP_NAMESPACE = 'flask-s3up'
s3up = FlaskS3Up(
    app, # Flask app
    namespace=S3UP_NAMESPACE, # namespace be unique
    object_hostname='http://flask-s3up.com', # file's hostname
    config={ # Bucket configs and else
        'profile_name': 'test',
        'access_key': None,
        'secret_key': None,
        'region_name': Region.SEOUL.value,
        'endpoint_url': None,
        'bucket_name': 'hwjeongtest',
        'cache_dir': '/tmp/flask_s3up',
        'use_cache': True,
        'ttl': 86400,
    }
)

# Init another one
s3up.add_new_one(
    namespace='namespace2',
    object_hostname='http://why.com',
    config={
        'profile_name': 'test',
        'bucket_name': 'hwjeongtest'
    }
)

# You can see registerd configs
# print(s3up.FLASK_S3UP_BUCKET_CONFIGS)

# You can use boto3's session and client if you want
# print(FlaskS3Up.get_boto_client(S3UP_NAMESPACE))
# print(FlaskS3Up.get_boto_session(S3UP_NAMESPACE))

# Apply FlaskS3Up blueprint
s3up.register()

@app.route('/index')
def index ():
    return 'Your app index page'

# Usage: python example.py test (run debug mode)
if __name__ == '__main__':
    app.run(debug=True, port=3000)

