.. meta::
    :description: Flask S3 Viewer is a powerful extension that makes it easy to browse S3 in any Flask application
    :keywords: Flask, s3, aws, upload, uploader, browsing, python3, python, mount, objectstorage, s3viewer

Configuration
=============
Before you can begin using Flask S3Viewer, you should set up authentication credentials. Credentials for your AWS account can be found in the IAM Console. You can create or use an existing user. Go to manage access keys and generate a new set of keys.

Configure credentials
---------------------
Install AWS CLI.

.. code-block:: bash

    pip install awscli

If you have the AWS CLI installed, then you can use it to configure your credentials file:

.. code-block:: bash

    aws configure

Alternatively, you can create the credential file yourself. By default, its location is at ~/.aws/credentials. and Flask S3Viewer is going to use the credential file.

Minimum settings
----------------
This is a minimal setup for using flask s3viewer.
First install the dependency packages.

.. code-block:: bash

    pip install flask flask_s3_viewer

Import flask and flask_s3_viewer

.. code-block:: python
    :linenos:
    :emphasize-lines: 3-4

    from flask import Flask

    from flask_s3_viewer import FlaskS3Viewer
    from flask_s3_viewer.aws.ref import Region

Initiailize Flask application and FlaskS3Viewer.

.. code-block:: python
    :linenos:
    :emphasize-lines: 4-20

    # Init Flask
    app = Flask(__name__)

    # Init Flask S3Viewer (auto-registers in v1.0+)
    FlaskS3Viewer(
        # Flask App
        app,
        # Namespace must be unique
        namespace='flask-s3-viewer',
        # Hostname, e.g. Cloudfront endpoint
        object_hostname='http://flask-s3-viewer.com',
        # Put your AWS's profile name and Bucket name
        config={
            'profile_name': 'PROFILE_NAME',
            'bucket_name': 'S3_BUCKET_NAME'
        }
    )

    if __name__ == '__main__':
        app.run(debug=True, port=3000)

.. note::
   In v1.0+, the constructor auto-registers the blueprint via Flask extension pattern.
   The legacy ``s3viewer.register()`` call has been removed. For deferred registration,
   pass ``app=None`` and call ``viewer.init_app(app)`` later.

The values in the code above are mandatory. If the setting is finished, run your Flask application and visit ``http://localhost/{namespace}/files``, e.g. http://localhost:3000/flask-s3-viewer/files.

You can get example codes over here_.

.. _here: https://github.com/hidekuma/flask-s3-viewer/tree/master/example

----

User Guides
=================
It is about various advanced settings.


Multiple bucket settings
------------------------
You can also initiailize multiple bucket.

.. code-block:: python
    :linenos:
    :emphasize-lines: 7-8

    ...

    s3viewer = FlaskS3Viewer(
        ...
    )

    # Init another bucket
    s3viewer.add_new_one(
        namespace='another_namespace',
        object_hostname='http://anotherbucket.com',
        config={
            'profile_name': 'PROFILE_NAME',
            'bucket_name': 'S3_BUCKET_NAME'
        }
    )

Mount a specific path in a bucket for browsing
----------------------------------------------
You can mount a specific path in the bucket to the browser.
( Be careful not to end the path with / )

.. code-block:: python
    :linenos:
    :emphasize-lines: 14

    ...

    s3viewer = FlaskS3Viewer(
        ...
    )

    # Init another bucket
    s3viewer.add_new_one(
        namespace='another_namespace',
        object_hostname='http://anotherbucket.com',
        config={
            'profile_name': 'PROFILE_NAME',
            'bucket_name': 'S3_BUCKET_NAME'
            'base_path': 'path/to/your/folder'
        }
    )



Limit the file extensions
--------------------------
You can limit the file extensions that are uploaded, if you want.

.. code-block:: python
    :linenos:
    :emphasize-lines: 4-5

    s3viewer = FlaskS3Viewer(
        ...

        # allowed extension
        allowed_extensions={'jpg', 'jpeg'},
        config={
            ...
        }
    )

Design template
---------------

Since v1.0, Flask S3 Viewer ships a single unified design built with
**Tailwind CSS + HTMX**, with light/dark mode and inline heroicons.

.. note::
   The ``template_namespace='base'|'mdl'`` argument is deprecated. Passing it
   emits a :class:`DeprecationWarning` and is otherwise ignored. The previous
   ``base/`` and ``mdl/`` template directories have been removed.

Branding (title + logo)
-----------------------

Three constructor options let you brand the UI without overriding templates:

.. code-block:: python
    :linenos:

    FlaskS3Viewer(
        app,
        namespace='my-bucket',
        title='ACME File Vault',
        logo_path='/opt/acme/assets/logo.svg',   # local file, auto-inlined
        # logo_url='https://cdn.acme.io/logo.svg',  # alternatively, any URL
        config={...},
    )

``logo_path`` reads the file once at construction time and embeds it as a
``data:`` URI so you don't need to expose it via a separate static route.
``logo_url`` accepts any browser-resolvable URL (CDN, ``url_for("static",
filename=...)`` result, or absolute URL). ``logo_path`` takes precedence
over ``logo_url`` when both are provided.

Template overrides
------------------

To customize the design further, override the templates in
``flask_s3_viewer/blueprints/templates/`` (``layout.html``, ``files.html``,
``_file_list.html``, ``_pagination.html``, ``_upload_form.html``,
``error.html``) using Flask's standard template override mechanism.

``layout.html`` exposes a ``{% block extra_head %}`` hook so downstream apps
can inject custom ``<link>`` / ``<script>`` / ``<meta>`` tags without
replacing the whole layout:

.. code-block:: jinja

    {% extends "flask_s3_viewer/layout.html" %}
    {% block extra_head %}
      <link rel="stylesheet" href="{{ url_for('static', filename='custom.css') }}">
    {% endblock %}

Controll large files
--------------------
If you want to controll large files (maybe larger than 5MB ~ maximum 5TB), I recommand to set like below.
Flask S3Viewer is going to use S3's presigned URL. It's nice to controll large files.

.. code-block:: python
    :linenos:
    :emphasize-lines: 3-4

    s3viewer = FlaskS3Viewer(
        ...
        # Change upload type to 'presign'
        upload_type='presign',
        config={
            ...
        }
    )

but you must do S3’s CORS settings before like set above.

.. code-block:: json
    :linenos:

    [
        {
            "AllowedHeaders": [
                "*"
            ],
            "AllowedMethods": [
                "POST",
                "PUT",
                "GET",
                "HEAD",
                "DELETE"
            ],
            "AllowedOrigins": [
                "http://localhost:3000"
            ],
        }
    ]

Use Caching
-----------
S3 is charged per call. Therefore, Flask S3Viewer supports caching (currently only supports file caching, in-memory database will be supported later).

.. code-block:: python
    :linenos:
    :emphasize-lines: 5-10

    s3viewer = FlaskS3Viewer(
        ...
        config={
            ...
            # Flask S3Viewer will cache the list of s3 objects, if you set True
            'use_cache': True,
            # Where cached files will be written
            'cache_dir': '/tmp/flask_s3_viewer',
            # Time To Live
            'ttl': 86400
        }
    )

Full example
------------

.. code-block:: python
    :linenos:

    ...

     FlaskS3Viewer(
         # Flask app
         app,
         # Namespace must be unique
         namespace='flask-s3-viewer',
         # File's hostname
         object_hostname='http://flask-s3-viewer.com',
         # Allowed extension
         allowed_extensions={},
         # Bucket configs and else
         config={
             # Required
             'profile_name': 'PROFILE_NAME',
             # Required
             'bucket_name': 'S3_BUCKET_NAME',
             'region_name': Region.SEOUL.value,
             # Not necessary, if you configure aws settings, e.g. ~/.aws
             'access_key': 'AWS_IAM_ACCESS_KEY',
             'secret_key': 'AWS_IAM_SECRET_KEY',
             # For S3 compatible
             'endpoint_url': None,
             # Flask S3Viewer will cache the list of s3 objects, if you set True
             'use_cache': True,
             # Where cached files will be written
             'cache_dir': '/tmp/flask_s3_viewer',
             # Time To Live
             'ttl': 86400,
         }
     )

Things to know
--------------

Searching
`````````
- Search only working in EN, because of JMESPath.
