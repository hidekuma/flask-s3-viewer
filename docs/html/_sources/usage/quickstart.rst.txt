Quick Start
============

Minimum setting
---------------

First install the dependency packages and configure.

.. code-block:: bash

    pip install flask flask_s3up

Import flask and flask_s3up

.. code-block:: python
    :linenos:
    :emphasize-lines: 3-4

    import flask

    from flask_s3up import FlaskS3Up
    from flask_s3up.aws.ref import Region

Initiailize Flask application and FlaskS3Up.

.. code-block:: python
    :linenos:
    :emphasize-lines: 4-20

    # Init Flask
    app = Flask(__name__)

    # Init Flask S3Up
    s3up = FlaskS3Up(
        # Flask App
        app,
        # Namespace must be unique
        namespace='flask-s3up',
        # Hostname, e.g. Cloudfront endpoint
        object_hostname='http://flask-s3up.com',
        # Put your AWS's profile name and Bucket name
        config={
            'profile_name': 'PROFILE_NAME',
            'bucket_name': 'S3_BUCKET_NAME'
        }
    )

    # Register Flask S3Up's router
    s3up.register()

    if __name__ == '__main__':
        app.run(debug=True, port=3000)

The values in the code above are mandatory. If the setting is finished, run your Flask application and visit ``http://localhost/{namespace}/files``, e.g. http://localhost:3000/flask-s3up/files.

You can get example codes over here_.

.. _here: https://github.com/hidekuma/flask-s3up/tree/master/example


Multiple bucket settings
------------------------
You can also initiailize multiple bucket.

.. code-block:: python
    :linenos:
    :emphasize-lines: 7-8

    ...

    s3up = FlaskS3Up(
        ...
    )

    # Init another bucket
    s3up.add_new_one(
        namespace='another_namespace',
        object_hostname='http://anotherbucket.com',
        config={
            'profile_name': 'PROFILE_NAME',
            'bucket_name': 'S3_BUCKET_NAME'
        }
    )
    s3up.register()

Limit the file extensions
--------------------------
You can limit the file extensions that are uploaded, if you want.

.. code-block:: python
    :linenos:
    :emphasize-lines: 4-5

    s3up = FlaskS3Up(
        ...

        # allowed extension
        allowed_extensions={'jpg', 'jpeg'},
        config={
            ...
        }
    )

Choose the design template
---------------------------
Flask S3up supports the templates below.

================== ==================== ============================
Template namespace Design type          Description
================== ==================== ============================
base               *Default*             Not designed at all
mdl                Material Design Lite `link <https://getmdl.io>`__
================== ==================== ============================

.. code-block:: python
    :linenos:
    :emphasize-lines: 3-4

    s3up = FlaskS3Up(
        ...
        # Enter template namespace (default: base)
        template_namespace='mdl',
        config={
            ...
        }
    )
    s3up.register()

Controll large files
--------------------
If you want to controll large files (maybe larger than 5MB ~ maximum 5TB), I recommand to set like below.
Flask S3Up is going to use S3's presigned URL. It's nice to controll large files.

.. code-block:: python
    :linenos:
    :emphasize-lines: 3-4

    s3up = FlaskS3Up(
        ...
        # Change upload type to 'presign'
        upload_type='presign',
        config={
            ...
        }
    )
    s3up.register()

but you must do S3’s CORS settings before like set above.

.. code-block:: xml
    :linenos:

     <CORSConfiguration>
         <CORSRule>
             <AllowedOrigin>http://www.yourdomain.com</AllowedOrigin>
             <AllowedMethod>GET</AllowedMethod>
             <AllowedMethod>POST</AllowedMethod>
             <AllowedHeader>*</AllowedHeader>
         </CORSRule>
     </CORSConfiguration>

Use Caching
-----------
S3 is charged per call. Therefore, Flask S3Up supports caching (currently only supports file caching, in-memory database will be supported later).

.. code-block:: python
    :linenos:
    :emphasize-lines: 5-10

    s3up = FlaskS3Up(
        ...
        config={
            ...
            # Flask S3Up will cache the list of s3 objects, if you set True
            'use_cache': True,
            # Where cached files will be written
            'cache_dir': '/tmp/flask_s3up',
            # Time To Live
            'ttl': 86400
        }
    )
    s3up.register()

Full example
------------

.. code-block:: python
    :linenos:

    ...

     s3up = FlaskS3Up(
         # Flask app
         app,
         # Namespace must be unique
         namespace='flask-s3up',
         # Enter template namespace(default: base)
         template_namespace='mdl',
         # File's hostname
         object_hostname='http://flask-s3up.com',
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
             # Flask S3Up will cache the list of s3 objects, if you set True
             'use_cache': True,
             # Where cached files will be written
             'cache_dir': '/tmp/flask_s3up',
             # Time To Live
             'ttl': 86400,
         }
     )

Things to know
--------------

Searching
`````````
- Search only working in EN, because of JMESPath.
