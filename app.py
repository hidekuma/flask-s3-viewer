import sys

from flask import Flask
from flask_s3up import FlaskS3Up, routers

app = Flask(__name__)

# templates caching time
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
app.config['TEMPLATES_AUTO_RELOAD'] = True

# FlaskS3Up Init
s3up = FlaskS3Up()

# FlaskS3Up Configs
s3up.init_app(app, config={
    'S3UP_BUCKET_CONFIGS': {
        'flask-s3up': {
            'bucket': 'hwjeongtest',
            'profile': 'test',
            'is_compatible': False,
            'service_point': None,
            'object_hostname': 'http://test.com',
            'use_cache': True,
            'region': '',
            'ttl': 86400,
            'cache_dir': '/tmp/flask_s3up'
        }
    }
})
app.register_blueprint(routers.FlaskS3UpViewRouter, url_prefix='/flask-s3up')
app.register_blueprint(routers.FlaskS3UpViewRouter, url_prefix='/test')

if __name__ == '__main__':
    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            debug = True
    app.run(debug=debug, port=3000)

