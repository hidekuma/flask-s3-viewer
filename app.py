import sys

from flask import Flask
from flask_s3up import FlaskS3Up
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 1
s3up = FlaskS3Up()
s3up.init_app(app, config={
    'PATH': '/flask-s3up',
    'PROFILE': 'hwjeong',
    'BUCKET': 'hwjeong',
})

if __name__ == '__main__':
    debug = False
    if len(sys.argv) > 1:
        if sys.argv[1] == 'test':
            debug = True
    app.run(debug=debug, port=3000)

