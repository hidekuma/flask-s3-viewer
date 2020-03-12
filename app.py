import sys

from flask import Flask
from flask_s3up import FlaskS3Up, routers

app = Flask(__name__)

# templates caching time
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# FlaskS3Up Init
s3up = FlaskS3Up(
    app,
    url_prefix='/flask-s3up',
    object_hostname='http://test.com',
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

app.register_blueprint(routers.FlaskS3UpViewRouter, url_prefix=s3up.url_prefix)

if __name__ == '__main__':
    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            debug = True
    app.run(debug=debug, port=3000)

