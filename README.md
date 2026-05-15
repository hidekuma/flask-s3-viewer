![logo](https://raw.githubusercontent.com/hidekuma/flask-s3-viewer/main/i/logo.png)

# Flask S3 Viewer

Browse, upload, and manage Amazon S3 buckets from any Flask application.

[![PyPI version](https://badge.fury.io/py/flask-s3-viewer.svg)](https://badge.fury.io/py/flask-s3-viewer)
[![CI](https://github.com/hidekuma/flask-s3-viewer/actions/workflows/ci.yml/badge.svg)](https://github.com/hidekuma/flask-s3-viewer/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **v1.0 is a major rewrite.** Modern UI (Tailwind + HTMX, dark mode), Flask 3 support, hardened path-traversal defenses, Flask extension pattern, type hints, pytest + moto test suite, GitHub Actions CI. See [migration guide](MIGRATION.md) if upgrading from `0.x`.


## Highlights

- **Modern UI** — Tailwind CSS, HTMX-driven partial updates, light/dark mode, inline heroicons. Parent-folder (`..`) row and logged-in user widget in the header. No build pipeline required for end users (CSS ships pre-built).
- **Optional auth** — Hook framework (`auth_callback` + `permission_callback` with per-action constants) plus built-in Google OAuth via the `[auth]` extra. Auth routes (`/auth/{login,callback,logout}`) live outside the namespace prefix so one redirect URI covers every viewer on the app.
- **Smart search** — Case-insensitive substring match, Unicode-safe (Korean / Japanese / accented Latin), NFC-normalised so macOS uploads match the browser IME, scoped to the current folder, and surfaces matching child folder rows.
- **Secure by default** — Rejects path-traversal tokens (`..`, `.`, `//`, `\`) at every prefix boundary. Cache directory escape blocked by `realpath` containment, and cache files are stored as JSON with restrictive file permissions.
- **Flask extension pattern** — `FlaskS3Viewer(app, namespace=...)` auto-registers. Supports multiple buckets per app via `add_new_one(...)`. Works with `init_app(app)` for deferred binding.
- **Multi-bucket** — Independent namespaces, optional per-bucket CloudFront / external `object_hostname`.
- **Presigned uploads** — Multi-file presigned POST flow for large files; default form upload also supported.
- **Caching** — File-system JSON cache with TTL; automatically invalidated on writes (search bypasses the cache, and authenticated listings are user-isolated).
- **Tested** — 203 pytest cases, ruff + mypy clean, moto-based S3 mock.

## Installation

```bash
pip install flask_s3_viewer
```

Requires Python 3.10+, Flask 3.0+, boto3 1.34+.

## Quick start

```python
from flask import Flask
from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.aws.ref import Region

app = Flask(__name__)

# Auto-register. No `register()` call needed.
FlaskS3Viewer(
    app,
    namespace="my-bucket",
    object_hostname="https://cdn.example.com",  # optional CloudFront host
    config={
        "profile_name": "default",
        "region_name": Region.SEOUL.value,
        "bucket_name": "my-bucket",
        "cache_dir": "/tmp/flask_s3_viewer",
        "use_cache": True,
        "ttl": 86400,
    },
)

@app.route("/")
def index():
    return "App index"

if __name__ == "__main__":
    app.run(debug=True, port=3000)
```

Visit `http://localhost:3000/my-bucket/files` to browse the bucket.

### Branding (title + logo)

```python
FlaskS3Viewer(
    app,
    namespace="my-bucket",
    title="ACME File Vault",
    logo_path="/opt/acme/assets/logo.svg",   # local file, auto inlined as a data: URI
    # or: logo_url="https://cdn.acme.io/logo.svg",
    config={...},
)
```

`logo_path` reads the file once at construction time and embeds it as a `data:` URI so you don't need a separate static route. `logo_url` accepts any browser-resolvable URL (CDN, `url_for("static", filename=...)`, etc.). `logo_path` takes precedence.

### Customizing templates (`template_folder`)

Scaffold a writable copy of the bundled templates with the CLI, edit, then point the viewer at that folder:

```bash
# Templates only (default — covers most theming needs)
flask_s3_viewer -p ./fsv-templates

# Or, fork the entire UI bundle (templates + static/css/app.css + htmx + core.js)
flask_s3_viewer -p ./fsv-templates --with-static
```

```python
FlaskS3Viewer(
    app,
    namespace="my-bucket",
    template_folder="./fsv-templates",   # files here win over bundled defaults
    config={...},
)
```

Behind the scenes the extension prepends a `FileSystemLoader(template_folder)` to the app's Jinja loader via `ChoiceLoader`, so any not-overridden template (e.g. `error.html` when you only edited `files.html`) still resolves against the bundle. Other blueprints' template resolution is untouched.

### Multiple buckets

```python
viewer = FlaskS3Viewer(app, namespace="primary", config={...})
viewer.add_new_one(namespace="backups", config={...})
```

Each namespace gets its own URL prefix and its own configuration.

### Deferred initialization

```python
viewer = FlaskS3Viewer(namespace="my-bucket", config={...})

def create_app():
    app = Flask(__name__)
    viewer.init_app(app)
    return app
```

### Accessing the underlying boto3 client

```python
from flask import current_app
from flask_s3_viewer import FlaskS3Viewer

# Inside a request:
client = current_app.extensions["flask_s3_viewer"]["my-bucket"]._s3

# Or via the helper:
client = FlaskS3Viewer.get_boto_client(app, "my-bucket")
session = FlaskS3Viewer.get_boto_session(app, "my-bucket")
```

## Configuration

All `config` keys are forwarded to the underlying S3 client:

| Key              | Type             | Default | Notes                                          |
|------------------|------------------|---------|------------------------------------------------|
| `bucket_name`    | str              | —       | Required.                                      |
| `profile_name`   | str \| None      | None    | Uses boto3 default credential chain if None.   |
| `region_name`    | str \| None      | None    | e.g. `ap-northeast-2`.                         |
| `endpoint_url`   | str \| None      | None    | Custom S3 endpoint (MinIO, etc.).              |
| `access_key`     | str \| None      | None    | Prefer profiles / IAM roles.                   |
| `secret_key`     | str \| None      | None    |                                                |
| `session_token`  | str \| None      | None    |                                                |
| `verify`         | bool \| str      | False   | TLS verify (or path to CA bundle).             |
| `base_path`      | str              | `""`    | Object key prefix scope for this viewer.       |
| `use_cache`      | bool             | False   | File-system JSON cache.                        |
| `cache_dir`      | str \| None      | None    | Required when `use_cache=True`.                |
| `ttl`            | int (seconds)    | 300     | Cache time-to-live.                            |
| `timezone`       | str \| None      | None    | IANA timezone for Modified display, e.g. `Asia/Seoul`. If None, boto3's original timestamp string is shown. |
| `role_arn`       | str \| None      | None    | If set, the wrapper runs STS `AssumeRole` on top of the base credentials and uses the returned temporary keys (cross-account, multi-tenant). |
| `role_session_name` | str \| None   | `"flask-s3-viewer"` | Identifier for the assumed session.    |
| `external_id`    | str \| None      | None    | Forwarded to STS for cross-account roles that require it. |
| `duration_seconds` | int \| None    | None    | Lifetime of the assumed credentials in seconds (15 min – 12 h). |
| `mfa_serial`     | str \| None      | None    | MFA device ARN/serial for STS `AssumeRole`.    |
| `token_code`     | str \| None      | None    | One-time MFA code (paired with `mfa_serial`).  |
| `token_code_callback` | callable    | None    | Alternative to `token_code` — called once to prompt the user. |

Constructor options:

| Option               | Notes                                                            |
|----------------------|------------------------------------------------------------------|
| `app`                | Flask app (optional; pass later via `init_app(app)`).            |
| `namespace`          | Unique per app. Becomes the URL prefix.                          |
| `object_hostname`    | External link prefix (e.g. CloudFront).                          |
| `allowed_extensions` | `set[str] \| None` — only allow these uploads.                   |
| `upload_type`        | `"default"` (multipart form post) or `"presign"`.                |
| `title`              | Heading + browser tab title text. Default `"Flask S3 Viewer"`.   |
| `logo_url`           | URL of a custom logo image (absolute, `url_for(...)`, or `/static/...`). |
| `logo_path`          | Local filesystem path to a logo image — auto-inlined as a `data:` URI. Takes precedence over `logo_url`. |
| `template_folder`    | Directory whose Jinja files override the bundled templates (Flask `ChoiceLoader` pattern). Seed it via the CLI scaffold. |

## AWS authentication

`flask-s3-viewer` defers to boto3's default credential chain, so these all work out of the box:

- Static keys (`access_key` / `secret_key` / `session_token`)
- Named profile (`profile_name='my-profile'`) — including profiles with `role_arn` + `source_profile` in `~/.aws/config` (boto3 handles AssumeRole automatically)
- `AWS_*` environment variables
- EC2 IMDS / ECS task role / AWS SSO cache / EKS IRSA (Web Identity OIDC) — picked up automatically when nothing else is set.

For workflows that need **explicit STS AssumeRole** (cross-account, multi-tenant, ad-hoc role delegation from a base credential), pass `role_arn` in the `config`:

```python
FlaskS3Viewer(
    app,
    namespace="cross-account",
    config={
        "bucket_name": "target-bucket",
        "region_name": "us-east-1",
        # Base credentials come from the default chain (profile/env/IRSA).
        "role_arn": "arn:aws:iam::123456789012:role/AppRole",
        "external_id": "shared-secret",          # optional
        "role_session_name": "my-app",           # default: "flask-s3-viewer"
        "duration_seconds": 3600,                # 15 min – 12 h
    },
)
```

For MFA-protected roles, supply a token (or a callback for interactive prompting):

```python
FlaskS3Viewer(
    app,
    namespace="mfa-account",
    config={
        "bucket_name": "secure-bucket",
        "region_name": "us-east-1",
        "role_arn": "arn:aws:iam::123456789012:role/AdminRole",
        "mfa_serial": "arn:aws:iam::123456789012:mfa/alice",
        "token_code_callback": lambda: input("MFA code: ").strip(),
    },
)
```

## Authentication & permissions

`flask-s3-viewer` ships with two opt-in layers. **The package works exactly as before with no auth wiring** — both default to "allow everyone".

### Layer 1: hook framework (no extra dependency)

Plug in your existing login system with two callables:

```python
from flask_s3_viewer.auth import ACTION_LIST, ACTION_UPLOAD, ACTION_DELETE

def who_is_asking(request):
    """Return the user's email (or any opaque id) — None means anonymous."""
    return request.headers.get("X-Forwarded-Email")

def can_they(email, action, namespace, key):
    """Authorize a single action. action is one of the ACTION_* constants."""
    if action == ACTION_DELETE:
        return email.endswith("@admin.example.com")
    return True

FlaskS3Viewer(
    app, namespace="bucket",
    auth_callback=who_is_asking,
    permission_callback=can_they,
    config={...},
)
```

The five action constants are `ACTION_LIST`, `ACTION_DOWNLOAD`, `ACTION_UPLOAD`, `ACTION_DELETE`, `ACTION_PRESIGN`.

### RBAC bucket switcher

For multi-bucket apps, keep hard authorization in `permission_callback` and use
`visible_namespaces_callback(email, registry)` to control which buckets appear
in the header switcher:

```python
RBAC = {
    "alice@example.com": {"assets", "private"},
    "bob@example.com": {"assets"},
}

def visible_buckets(email, registry):
    return RBAC.get(email, set())

def can_they(email, action, namespace, key):
    return namespace in RBAC.get(email, set())

viewer = FlaskS3Viewer(
    app,
    namespace="assets",
    title="Assets",
    auth_callback=who_is_asking,
    permission_callback=can_they,
    visible_namespaces_callback=visible_buckets,
    config={...},
)

viewer.add_new_one(
    namespace="private",
    title="Private",
    config={...},
)
```

The switcher only hides inaccessible namespaces from the UI. Direct URL access
is still checked by `permission_callback`, so RBAC remains server-side.

### Layer 2: built-in Google OAuth (optional `[auth]` extra)

```bash
pip install "flask_s3_viewer[auth]"
```

```python
app.secret_key = "..."  # required — signs the session cookie

FlaskS3Viewer(
    app, namespace="bucket",
    google_client_id="...apps.googleusercontent.com",
    google_client_secret="...",
    allowed_emails=["alice@example.com"],
    allowed_domains=["example.com"],
    config={...},
)
```

Installs `/auth/login`, `/auth/callback`, `/auth/logout` as app-level routes (outside the FlaskS3Viewer namespace prefix). Configure the redirect URI as `https://<host>/auth/callback` in Google Cloud Console — one URI per app even when you mount multiple namespaces. Anonymous browser visits to a protected page are redirected through Google sign-in automatically.

Mix and match: pass your own `auth_callback` / `permission_callback` even when Google is enabled, or use `email_allowlist()` as a permission builder for non-Google deployments.

## Security

- **Path traversal hardening** — Every user-supplied `prefix` is validated. Tokens `..`, `.`, empty segments, and `\` are rejected with HTTP 400.
- **Defense in depth** — The cache layer additionally enforces `realpath` containment, preventing any path that would resolve outside `cache_dir`.
- **Subresource Integrity** — Bundled `htmx.min.js` references its `sha384` hash; the Tailwind output is shipped pre-built and signed by the package.
- **Credentials** — Never log credentials. Prefer named profiles or instance roles over hard-coded keys.

## Development

The frontend assets are pre-built and committed to the repo. To rebuild after editing templates:

```bash
cd frontend
npm install
npm run build       # writes flask_s3_viewer/blueprints/static/css/app.css
```

CI verifies the CSS is up to date (`git diff --exit-code`).

Tests:

```bash
pip install -e ".[dev]"
ruff check flask_s3_viewer/ tests/
mypy flask_s3_viewer/
pytest tests/ --cov=flask_s3_viewer
```

## Migrating from 0.x

See [`MIGRATION.md`](MIGRATION.md) for the full guide. Highlights:

- Drop `s3viewer.register()` — the constructor now auto-registers.
- `FlaskS3Viewer.get_instance(ns)` → `FlaskS3Viewer.get_instance(app, ns)` (same for `get_boto_client`, `get_boto_session`).
- Duplicate namespace registration now raises `ValueError` instead of silently reusing.
- Unknown namespaces return HTTP 404 instead of 500.
- Single template namespace — `template_namespace="base"|"mdl"` is ignored with a deprecation warning.
- CLI `--template` option removed.
- Path-traversal tokens in `prefix` now return HTTP 400.
- Requires Flask 3.0+ and boto3 1.34+.

## License

[MIT](LICENSE) © Hoiwoong Jung
