.. meta::
    :description: Flask S3 Viewer is a powerful extension that makes it easy to browse S3 in any Flask application
    :keywords: Flask, s3, aws, upload, uploader, browsing, python3, python, mount, objectstorage, s3viewer

Templates
=========

Since v1.0, Flask S3 Viewer ships a single unified UI built with
**Tailwind CSS + HTMX**, with light/dark mode and inline heroicons.
The legacy ``base/`` and ``mdl/`` template bundles are removed and the
``template_namespace`` constructor argument is deprecated — passing it
emits :class:`DeprecationWarning` and is otherwise ignored.

Use the CLI to scaffold a copy of the bundled templates into your own
repository, edit them, then point the viewer at the scaffolded
directory via ``template_folder=``.

Scaffold the templates
----------------------

See help.

.. code-block:: bash

    flask_s3_viewer -h
    =================== Flask S3Viewer Command Line Tool ====================

    optional arguments:
      -h, --help            show this help message and exit
      -p PATH, --path PATH  Enter the directory path where the template will be
                            located.
      --with-static         Also copy the bundled static assets (CSS / HTMX /
                            core.js) alongside the templates.

Copy just the Jinja templates (most common):

.. code-block:: bash

    flask_s3_viewer -p ./fsv-templates

Or fork the whole UI bundle (templates + ``static/css/app.css`` + HTMX +
``core.js``) when you need to restyle from scratch:

.. code-block:: bash

    flask_s3_viewer -p ./fsv-templates --with-static

After scaffolding, the directory contains:

- ``layout.html`` — page chrome, theme toggle, brand widget, ``extra_head`` block
- ``files.html`` — full listing page
- ``_file_list.html`` — HTMX partial swapped on navigation / search / pagination
- ``_pagination.html`` — pager partial
- ``_upload_form.html`` — upload UI partial
- ``error.html`` / ``_error_panel.html`` — error states

Wire the override
-----------------

Point the viewer at the scaffolded directory:

.. code-block:: python
    :linenos:

    FlaskS3Viewer(
        app,
        namespace='my-bucket',
        template_folder='./fsv-templates',
        config={...},
    )

Behind the scenes the extension prepends a ``FileSystemLoader`` to the
Flask app's Jinja loader via ``ChoiceLoader``, so any template you
didn't override still resolves against the bundled defaults and other
blueprints' templates remain unaffected.

Inject CSS / JS without forking
-------------------------------

For the common case where you only need to add a stylesheet, script, or
meta tag, extend ``layout.html`` and use the ``extra_head`` block — no
``template_folder=`` needed if you place this template on Flask's
existing search path:

.. code-block:: jinja

    {% extends "flask_s3_viewer/layout.html" %}
    {% block extra_head %}
      <link rel="stylesheet" href="{{ url_for('static', filename='custom.css') }}">
    {% endblock %}

Branding without overriding templates
-------------------------------------

If you only want a custom title and logo, prefer the constructor
options over a template override:

.. code-block:: python
    :linenos:

    FlaskS3Viewer(
        app,
        namespace='my-bucket',
        title='ACME File Vault',
        logo_path='/opt/acme/assets/logo.svg',     # local file, auto-inlined as data: URI
        # logo_url='https://cdn.acme.io/logo.svg', # alternatively, any URL
        config={...},
    )

``logo_path`` reads the file once at construction time and embeds it as
a ``data:`` URI, so you don't need to expose it via a separate static
route. ``logo_url`` accepts any browser-resolvable URL. ``logo_path``
takes precedence over ``logo_url`` when both are provided.
