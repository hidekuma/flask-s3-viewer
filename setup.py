import re
import ast
from setuptools import setup, find_packages

_version_re = re.compile(r"__version__\s+=\s+(.*)")

with open("flask_s3_viewer/__init__.py", "rb") as f:
    VERSION = str(
        ast.literal_eval(_version_re.search(f.read().decode("utf-8")).group(1))
    )


setup(
    name                          = 'flask_s3_viewer',
    version                       = VERSION,
    url                           = 'https://github.com/hidekuma/flask-s3-viewer',
    license                       = '',
    author                        = 'Hidekuma',
    author_email                  = 'd.hidekuma@gmail.com',
    download_url                  = 'https://github.com/hidekuma/flask-s3-viewer/releases',
    description                   = 'Flask S3 Viewer is a powerful extension that makes it easy to browse S3 in any Flask application.',
    packages                      = find_packages(exclude = ['tests*', 'test*', 'example*', 'i/*']),
    long_description              = open('README.md').read(),
    long_description_content_type = 'text/markdown',
    package_data = {
        'flask_s3_viewer': [
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
            'blueprints/static/js/flask.s3viewer.core.js'
        ]
    },
    include_package_data=True,
    zip_safe                      = False,
    keywords                      = ['aws', 's3', 'file', 'upload', 'flask', 'python', 'python3', 'browsing', 'uploader'],
    install_requires              = [
        'boto3>=1.28.22',
        'flask>=2.0.0'
    ],
    python_requires               = '>= 3.10',
    test_suite                    = 'tests',
    entry_points                  = {
        'console_scripts': [
            'flask_s3_viewer=flask_s3_viewer.cli:handle',
        ]
    },
)
