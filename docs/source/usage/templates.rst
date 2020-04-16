.. meta::
    :description: Flask S3up is a powerful extension that makes it easy to browse S3 in any Flask application
    :keywords: Flask, s3, aws, upload, uploader, browsing, python3, python, mount, objectstorage, s3up

Templates
=========
Flask S3Up provides CLI to help customize templates.

Get template source
--------------------------------------
You can customize the template with CLI tool.

See help.

.. code-block:: bash

    # You can see the details
    flask_s3up -h

     ____  __     __   ____  __ _    ____  ____  _  _  ____
    (  __)(  )   / _\ / ___)(  / )  / ___)( __ \/ )( \(  _ \
     ) _) / (_/\/    \\___ \ )  (   \___ \ (__ () \/ ( ) __/
    (__)  \____/\_/\_/(____/(__\_)  (____/(____/\____/(__)

    ============= Flask S3Up Command Line Tool ==============

    optional arguments:
      -h, --help            show this help message and exit
      -p PATH, --path PATH  Enter the directory path where the template will be
                            located
      -t {base,mdl}, --template {base,mdl}
                            Enter the name of the template to import. (mdl means
                            material-design-lite and base means not designed
                            template).

Get the template to your repository.

.. code-block:: bash

    # Get a Material-design-lite template
    flask_s3up --path templates/mdl --template mdl

    # Get a base template (not designed at all)
    flask_s3up -p templates/base -t base


When you run the command, you can see the
``{repository}/{path}/{template}`` has been created on your
repository. then rerun the Flask application.

And you can also change template directory if you want.

For examples, Get Material-design-lite template to ``templates/customized`` directory on your root path.

.. code-block:: bash

   flask_s3up -p templates/customized -t mdl

Then change template_namespace. it will be routed to defined directory (``templates/customized``).

.. code-block:: bash

   s3up = FlaskS3Up(
       ...
       template_namespace='customized',
       ...
   )

.. warning::
    The template folder of Flask S3Up is fixed as ``templates``. so if you change ``template_namespace``, It will be routed **{repository}/templates/{defined template_namespace_by_you}**.
