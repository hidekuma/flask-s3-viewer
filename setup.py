from setuptools import setup, find_packages
from flask_s3up import __version__ as VERSION

setup(
    name                          = 'flask_s3up',
    version                       = VERSION,
    url                           = 'https://github.com/hidekuma/flask_s3up',
    license                       = '',
    author                        = 'Hidekuma',
    author_email                  = 'd.hidekuma@gmail.com',
    download_url                  = f'https://github.com/hidekuma/flask_s3up/archive/{VERSION}.tar.gz',
    description                   = 'Flask S3up is a powerful extension that makes it easy to browse S3 in any Flask application.',
    packages                      = find_packages(exclude = ['tests*', 'test*', 'example*', 'i/*']),
    long_description              = open('README.md').read(),
    long_description_content_type = 'text/markdown',
    package_data = {
        'flask_s3up': [
            'blueprints/view.py',
            'blueprints/templates/mdl/contents.html',
            'blueprints/templates/mdl/controller.html',
            'blueprints/templates/mdl/error.html',
            'blueprints/templates/mdl/files.html',
            'blueprints/templates/mdl/layout.html',
            'blueprints/templates/mdl/prefixes.html',
            'blueprints/templates/mdl/NOTICE',
            'blueprints/templates/mdl/LICENSE',
            'blueprints/templates/base/contents.html',
            'blueprints/templates/base/controller.html',
            'blueprints/templates/base/error.html',
            'blueprints/templates/base/files.html',
            'blueprints/templates/base/layout.html',
            'blueprints/templates/base/prefixes.html',
        ]
    },
    include_package_data=True,
    zip_safe                      = False,
    keywords                      = ['aws', 's3', 'file', 'upload', 'flask', 'python', 'python3', 'browsing', 'uploader'],
    install_requires              = [
        'boto3>=1.12.2',
        'click>=7.1.1'
    ],
    python_requires               = '>= 3.7',
    test_suite                    = 'tests',
    entry_points                  = {
        'console_scripts': [
            'flask_s3up=flask_s3up.cli:handle',
        ]
    },
)
