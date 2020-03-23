import sys

from flask import Flask
from flask_s3up import FlaskS3Up
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(asctime)s: %(message)s'
)

app = Flask(__name__)

# templates caching time
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# FlaskS3Up Init
s3up = FlaskS3Up(
    app,
    namespace='flask-s3up',
    object_hostname='http://flask-s3up.com',
    config={
        'profile_name': 'test',
        'region_name': None,
        'endpoint_url': None,
        'bucket_name': 'hwjeongtest',
        'cache_dir': '/tmp/flask_s3up',
        'use_cache': True,
        'ttl': 86400,
    }
)

s3up.add_new_one(
    namespace='why',
    object_hostname='http://why.com',
    config={
        'profile_name': 'test',
        'region_name': None,
        'endpoint_url': None,
        'bucket_name': 'dgate-dev-assets',
        'cache_dir': '/tmp/flask_s3up',
        'use_cache': True,
        'ttl': 86400,
    }
)

s3up.register()

@app.route('/index')
def index ():
    return 'index'

# print(app.url_map)

if __name__ == '__main__':
    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            debug = True
    app.run(debug=debug, port=3000)

