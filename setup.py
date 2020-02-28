from setuptools import setup, find_packages

setup(
    name='flask_s3up',
    version='0.0.1',
    url='https://github.com/hidekuma/flask_s3up',
    license='',
    author='Hidekuma',
    author_email='d.hidekuma@gmail.com',
    description='Flask S3up is an extension for Flask that adds s3\'s browsing support to any Flask application.',
    packages=find_packages(
        exclude=[
            'tests',
            'example.py'
        ]
    ),
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    zip_safe=False,
    keywords=['aws', 's3', 'file', 'upload', 'flask', 'python', 'python3', 'browsing', 'uploader'],
    install_requires=[
    ],
    python_requires = '>=3.7',
    test_suite='tests'
)
