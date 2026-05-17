.. meta::
    :description: Flask S3 Viewer is a powerful extension that makes it easy to browse S3 in any Flask application
    :keywords: Flask, s3, aws, upload, uploader, browsing, python3, python, mount, objectstorage, s3viewer

Installation
============
You can `download FlaskS3Viewer executable`_ and `binary distributions from PyPI`_

.. _download FlaskS3Viewer executable: https://github.com/hidekuma/flask-s3-viewer/releases
.. _binary distributions from PyPI: https://pypi.org/project/flask-s3-viewer/

Support versions
----------------------------------------

Since v1.0, FlaskS3Viewer targets a modern Flask 3 / boto3 1.34 baseline.

======= ====== ============
Type    Name   Version
======= ====== ============
Runtime Python >=3.10
Library boto3  >=1.34.0
Library Flask  >=3.0,<4
======= ====== ============

The optional Google OAuth integration requires the ``[auth]`` extra::

    pip install "flask_s3_viewer[auth]"   # adds Authlib >=1.3.1

Using pip
---------
.. code-block:: bash

    pip install flask_s3_viewer
