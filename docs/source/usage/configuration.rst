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
            'bucket_name': 'S3_BUCKET_NAME',
            'base_path': 'path/to/your/folder',
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

The recommended path is the CLI scaffold plus the ``template_folder=``
constructor argument:

.. code-block:: bash

    # Copy just the Jinja templates (most common)
    flask_s3_viewer -p ./fsv-templates

    # Fork the whole UI bundle (templates + static/css/app.css + htmx + core.js)
    flask_s3_viewer -p ./fsv-templates --with-static

Edit any of ``layout.html`` / ``files.html`` / ``_file_list.html`` /
``_pagination.html`` / ``_upload_form.html`` / ``error.html`` in the
scaffolded directory, then point the viewer at it:

.. code-block:: python
    :linenos:

    FlaskS3Viewer(
        app,
        namespace='my-bucket',
        template_folder='./fsv-templates',
        config={...},
    )

Behind the scenes the extension prepends a ``FileSystemLoader`` to the
Flask app's Jinja loader via ``ChoiceLoader``, so any not-overridden
template still resolves against the bundle and other blueprints'
templates are unaffected.

``layout.html`` also exposes a ``{% block extra_head %}`` hook for the
common case where you only need to inject CSS / JS / ``<meta>`` tags:

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

STS AssumeRole / MFA
--------------------

For cross-account or multi-tenant deployments, the viewer can run
``sts:AssumeRole`` on top of the base credentials (profile / env /
IRSA / IMDS — whatever boto3 resolves by default). Pass the role
config inside the ``config`` dict:

.. code-block:: python
    :linenos:

    FlaskS3Viewer(
        app,
        namespace='cross-account',
        config={
            'bucket_name': 'target-bucket',
            'region_name': 'us-east-1',
            # Base credentials still come from boto3's default chain.
            'role_arn': 'arn:aws:iam::123456789012:role/AppRole',
            'external_id': 'shared-secret',     # optional
            'role_session_name': 'my-app',      # default: flask-s3-viewer
            'duration_seconds': 3600,           # 15 min ~ 12 h
        },
    )

For MFA-protected roles, supply either ``token_code`` directly or a
``token_code_callback`` callable that returns the current code on demand
(useful for interactive prompts that mustn't expire):

.. code-block:: python
    :linenos:

    FlaskS3Viewer(
        app,
        namespace='mfa-account',
        config={
            'bucket_name': 'secure-bucket',
            'region_name': 'us-east-1',
            'role_arn': 'arn:aws:iam::123456789012:role/AdminRole',
            'mfa_serial': 'arn:aws:iam::123456789012:mfa/alice',
            'token_code_callback': lambda: input('MFA code: ').strip(),
        },
    )

If ``role_arn`` is omitted, no STS call happens — the direct credential
path is used. That covers static keys, named profiles (including
profiles that themselves declare ``role_arn``+``source_profile`` in
``~/.aws/config`` — boto3 handles AssumeRole automatically), env vars,
EC2 IMDS, ECS task role, AWS SSO, and EKS IRSA.

Range requests / partial downloads
----------------------------------

Since v1.0, ``GET /<namespace>/files/<key>`` honors the HTTP ``Range``
header (RFC 7233). A well-formed range returns ``206 Partial Content``
with ``Content-Range`` and ``Content-Length`` populated; every download
response advertises ``Accept-Ranges: bytes``. Malformed or unsatisfiable
ranges return ``416 Range Not Satisfiable``.

This is what lets ``curl -C -``, video/audio ``<video>``/``<audio>``
players, and chunked mobile downloaders resume or seek without
re-fetching the whole object.

.. code-block:: bash
    :linenos:

    # Resume a partially downloaded file
    curl -C - -O http://localhost:3000/flask-s3-viewer/files/big.bin

    # Or request a specific byte range explicitly
    curl -H "Range: bytes=0-1023" -O \
        http://localhost:3000/flask-s3-viewer/files/big.bin


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

Authentication & permissions
----------------------------

Two opt-in layers, both off by default — the package keeps the legacy
anonymous experience verbatim until you wire something up.

**Hook framework** — bring your own login. Two callables:

.. code-block:: python
    :linenos:

    from flask_s3_viewer.auth import ACTION_DELETE

    def auth_callback(request):
        # Return the user's email/id, or None for anonymous.
        return request.headers.get("X-Forwarded-Email")

    def permission_callback(email, action, namespace, key):
        # ``action`` is one of ACTION_LIST / ACTION_DOWNLOAD /
        # ACTION_UPLOAD / ACTION_DELETE / ACTION_PRESIGN.
        if action == ACTION_DELETE:
            return email.endswith("@admin.example.com")
        return True

    FlaskS3Viewer(
        app, namespace="bucket",
        auth_callback=auth_callback,
        permission_callback=permission_callback,
        config={...},
    )

Returning ``None`` from ``auth_callback`` triggers a ``401`` (or a Google
login redirect — see below). ``permission_callback`` returning ``False``
triggers a ``403``.

**Built-in Google OAuth** — requires the optional ``[auth]`` extra::

    pip install "flask_s3_viewer[auth]"

.. code-block:: python
    :linenos:

    app.secret_key = "..."  # required — signs the session cookie

    FlaskS3Viewer(
        app, namespace="bucket",
        google_client_id="...apps.googleusercontent.com",
        google_client_secret="...",
        allowed_emails=["alice@example.com"],
        allowed_domains=["example.com"],
        config={...},
    )

Routes ``/auth/login``, ``/auth/callback``, ``/auth/logout`` are
registered as app-level routes — they live OUTSIDE the FlaskS3Viewer
namespace prefix. Configure the redirect URI as
``https://<host>/auth/callback`` in Google Cloud Console. One URI per
app even when you mount multiple namespaces via ``add_new_one()``;
renaming a namespace does not require updating Google Console.
Anonymous browser GETs are redirected through Google sign-in;
non-browser clients still get a bare ``401``.

``allowed_emails`` / ``allowed_domains`` are a shortcut for the common
allow-list case — internally they wire up the
``email_allowlist(emails=..., domains=...)`` builder as the
``permission_callback``. Pass your own ``permission_callback`` for
fine-grained per-action policy.

Audit logging
-------------

Every S3 CRUD action that flows through the blueprint emits a single
structured record on the ``flask_s3_viewer.audit`` logger. The logger
is always present — host applications opt in by attaching a handler
and/or adjusting its level via the standard ``logging`` API. No
constructor flag toggles audit on or off; the v1.0 public API is
unchanged.

**Logger name:** ``flask_s3_viewer.audit``
**Default level:** unset (records propagate to root and are filtered
by the host's effective level). Successful actions emit at
``INFO``; permission denials emit at ``WARNING``; unexpected
exceptions emit at ``ERROR``.

**Record fields** (attached as ``LogRecord`` attributes via ``extra=``):

  - ``action`` — one of ``list``, ``download``, ``upload``, ``delete``,
    ``presign``
  - ``namespace`` — viewer namespace the request landed on
  - ``key`` — canonical S3 key / prefix (post-``base_path``)
  - ``user`` — authenticated email or the literal string ``anonymous``
  - ``result`` — ``ok`` / ``denied`` / ``error``
  - ``status_code`` — HTTP status emitted to the client
  - ``client_ip`` — ``request.remote_addr``
  - ``user_agent`` — capped at 256 bytes; sanitised
  - ``error`` — present only when an exception was attached

The human-readable message is a single space-separated key=value line:

.. code-block:: text

    action=download namespace=fsv-test key=docs/report.pdf
    user=alice@example.com result=ok status=200

Newlines, carriage returns, and other ASCII control bytes inside
attacker-controllable fields (key, email, User-Agent, exception
message) are escaped as ``\\xNN`` before the record is built, so a
crafted request cannot smuggle a fake row into the log stream.

**Plain file handler example:**

.. code-block:: python
    :linenos:

    import logging

    handler = logging.FileHandler('/var/log/flask_s3_viewer/audit.log')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger('flask_s3_viewer.audit').addHandler(handler)
    logging.getLogger('flask_s3_viewer.audit').setLevel(logging.INFO)

**Structured JSON handler example** (uses
`python-json-logger <https://github.com/madzak/python-json-logger>`_):

.. code-block:: python
    :linenos:

    import logging
    from pythonjsonlogger import jsonlogger

    audit_handler = logging.FileHandler('/var/log/flask_s3_viewer/audit.jsonl')
    audit_handler.setFormatter(jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(action)s %(namespace)s '
        '%(key)s %(user)s %(result)s %(status_code)s '
        '%(client_ip)s %(user_agent)s'
    ))
    audit = logging.getLogger('flask_s3_viewer.audit')
    audit.addHandler(audit_handler)
    audit.setLevel(logging.INFO)
    # The library leaves propagate=True by default — disable it here
    # if you do NOT also want these records flowing to root handlers.
    audit.propagate = False

**PII / secret redaction.** Emails and S3 keys are written verbatim,
which may be sensitive depending on deployment policy. Attach a
``logging.Filter`` if you need to mask, hash, or drop fields before
they hit disk — for example to GDPR-truncate the user field, or to
strip ARNs/bucket names from ``error`` messages produced by boto3
``ClientError`` stringification.

.. code-block:: python
    :linenos:

    class RedactFilter(logging.Filter):
        def filter(self, record):
            if getattr(record, 'user', None):
                user = record.user
                record.user = user.split('@', 1)[0][:2] + '***@' + user.split('@', 1)[-1]
            return True

    audit.addFilter(RedactFilter())

For ``key`` and ``error`` — which can carry full S3 paths and boto3
``ClientError`` text containing bucket names / ARNs / request IDs —
attach a second filter that keeps just enough breadcrumb to trace the
incident without leaking the rest of the path or the AWS account
topology:

.. code-block:: python
    :linenos:

    import re

    _ARN_RE = re.compile(r'arn:aws:[^\s"\']+')
    _BUCKET_RE = re.compile(r'(?i)\bbucket[\s:=]+[^\s"\',]+')

    class KeyErrorRedactFilter(logging.Filter):
        """Redact prefix tails on ``key`` and AWS identifiers on ``error``."""
        def filter(self, record):
            key = getattr(record, 'key', None)
            if key:
                # Keep only the first path segment ("docs/...") so the
                # audit trail still distinguishes top-level folders but
                # the leaf filename / nested path is masked.
                head, sep, _tail = key.partition('/')
                record.key = f'{head}{sep}***' if sep else '***'
            err = getattr(record, 'error', None)
            if err:
                err = _ARN_RE.sub('arn:aws:***', err)
                err = _BUCKET_RE.sub('bucket=***', err)
                record.error = err
            return True

    audit.addFilter(KeyErrorRedactFilter())

The two filters compose — install both if you want the user, key, and
error fields all masked. Tune the regex set to your environment;
``ClientError`` text varies by API call.

**Capturing the real client IP behind a reverse proxy.** ``client_ip``
is sourced from ``request.remote_addr``, which Werkzeug fills from the
*last hop* on the TCP connection. When the app sits behind a load
balancer, ALB / ELB / nginx / Cloudflare, that hop is the proxy and
every audit row records the proxy IP — not the originating client.
For the audit trail to actually identify clients you must install
Werkzeug's ``ProxyFix`` middleware (or an equivalent) so
``X-Forwarded-For`` / ``Forwarded`` headers are honored:

.. code-block:: python
    :linenos:

    from werkzeug.middleware.proxy_fix import ProxyFix

    # ``x_for=1`` trusts exactly one X-Forwarded-For hop (your edge LB).
    # If the request transits N reverse proxies you control end-to-end,
    # raise this to N. Trusting too many hops lets clients spoof the IP.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

Without ProxyFix (or a host-supplied equivalent), every ``client_ip``
field in the audit stream is the LB's address and the audit trail
loses most of its forensic value. The value of ``x_for`` is
deployment-specific — adjust it for nested LB / CDN topologies, and
**only** trust hops you operate.

**Calling :func:`emit` from host code.** The ``emit`` function is part
of the public surface: host integrations may import it and emit
extra audit lines for non-CRUD operations they layer on top of the
viewer (e.g. a custom admin route that bulk-tags objects). Usage:

.. code-block:: python
    :linenos:

    from flask_s3_viewer.audit import emit as audit_emit
    from flask_s3_viewer.auth import ACTION_LIST  # or ACTION_DOWNLOAD/...

    # Call from inside a Flask request context so client_ip / user_agent
    # are populated automatically; outside a request both fields emit as
    # empty strings.
    audit_emit(
        action=ACTION_LIST,
        namespace='my-bucket',
        key='reports/2026/',   # caller pre-normalises (post-base_path)
        user=current_user_email,
        result='ok',
        status_code=200,
    )

Prefer the ``flask_s3_viewer.auth.ACTION_*`` constants over raw
strings; ``action`` and ``result`` are sanitised but the level mapping
(``ok``→INFO, ``denied``→WARNING, ``error``→ERROR) depends on
``result``. The signature is part of v1.x stability — additions will
be backwards-compatible.

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
Case-insensitive substring match applied in Python. Notable properties:

- **Unicode-safe.** Korean, Japanese, accented Latin, and emoji all
  match — the EN-only JMESPath limitation in earlier versions is gone.
- **NFC-normalised.** macOS Finder uploads land in S3 as
  NFD-decomposed Hangul while the browser IME emits NFC; both sides
  are normalised before comparison so the bytes line up.
- **Recursive.** When the search box is non-empty the listing
  switches to a flat (``delimiter=''``) S3 call scoped to the current
  prefix, so a matching filename three folders deep is visible
  without manual drill-in.
- **Folder rows are synthesized.** Any sub-prefix whose own segment
  contains the query appears as a clickable folder, alongside the
  matching files.
- **``base_path`` is excluded from the comparison.** The namespace
  mount point itself doesn't bleed into every match.
- **Cache-bypassed.** Search results are not persisted to the disk
  cache, so a code-level change in matching semantics never gets
  served stale from an old deployment.

Matching is bounded by ``max_items × max_pages`` per request (default
1000 keys). For very large prefixes a query may need to be combined
with a narrower prefix to surface deeper matches.
