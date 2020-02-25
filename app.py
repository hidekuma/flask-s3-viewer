import sys

from flask import Flask
from flask_s3up import FlaskS3Up

app = Flask(__name__)

# templates caching time
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# flask_s3up Initialize
s3up = FlaskS3Up()
s3up.init_app(app, config={
    'S3UP_PROFILE': 'hwjeong',
    'S3UP_BUCKET': 'hwjeong',
    'S3UP_SERVICE_POINT': None,
    'S3UP_IS_COMPATIBLE': False,
    'S3UP_VIEW_PATH': '/flask-s3up',
    'S3UP_OBJECT_HOSTNAME': 'http://test.com',
    'S3UP_USE_CACHING': True,
    'S3UP_CACHE_DIR': '/tmp/flask_s3up',
    'S3UP_TTL': 600
})

if __name__ == '__main__':
    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            debug = True
    app.run(debug=debug, port=3000)

