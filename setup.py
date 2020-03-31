from setuptools import setup, find_packages

VERSION = '0.0.6'
setup(
    name                          = 'flask_s3up',
    version                       = VERSION,
    url                           = 'https://github.com/hidekuma/flask_s3up',
    license                       = '',
    author                        = 'Hidekuma',
    author_email                  = 'd.hidekuma@gmail.com',
    download_url                  = f'https://github.com/hidekuma/flask_s3up/archive/{VERSION}.tar.gz',
    description                   = 'Flask S3Up is an extension for Flask that adds s3\'s browsing support to any Flask application.',
    packages                      = find_packages(exclude = ['tests*', 'example.py']),
    long_description              = open('README.md').read(),
    long_description_content_type = 'text/markdown',
    package_data = {
        'flask_s3up': [
            'blueprints/view.py',
            'blueprints/static/js/flask.s3up.core.js',
            'blueprints/templates/flask_s3up/contents.html',
            'blueprints/templates/flask_s3up/controller.html',
            'blueprints/templates/flask_s3up/error.html',
            'blueprints/templates/flask_s3up/files.html',
            'blueprints/templates/flask_s3up/layout.html',
            'blueprints/templates/flask_s3up/prefixes.html',
            'blueprints/templates/flask_s3up_skeleton/contents.html',
            'blueprints/templates/flask_s3up_skeleton/controller.html',
            'blueprints/templates/flask_s3up_skeleton/error.html',
            'blueprints/templates/flask_s3up_skeleton/files.html',
            'blueprints/templates/flask_s3up_skeleton/layout.html',
            'blueprints/templates/flask_s3up_skeleton/prefixes.html',
        ]
    },
    include_package_data=True,
    zip_safe                      = False,
    keywords                      = ['aws', 's3', 'file', 'upload', 'flask', 'python', 'python3', 'browsing', 'uploader'],
    install_requires              = [
        'boto3>=1.12.2'
    ],
    python_requires               = '>= 3.7',
    test_suite                    = 'tests',
    entry_points                  = {
        'console_scripts': [
            'flask_s3up=flask_s3up.cli:handle',
        ]
    },
)
