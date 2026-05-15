# Migration guide: 0.x → 1.0

`flask_s3_viewer` 1.0 is a major rewrite. This guide walks through every breaking change with before/after examples.

## At a glance

| Area              | 0.x                                                      | 1.0                                                       |
|-------------------|----------------------------------------------------------|-----------------------------------------------------------|
| Registration      | `FlaskS3Viewer(app, ...).register()`                     | `FlaskS3Viewer(app, ...)` — auto-registers                |
| Instance lookup   | `FlaskS3Viewer.get_instance("ns")`                       | `FlaskS3Viewer.get_instance(app, "ns")`                   |
| Duplicate namespace| silent reuse                                            | `ValueError`                                              |
| Unknown namespace | `KeyError` → HTTP 500                                    | HTTP 404                                                  |
| Templates         | `template_namespace="base" \| "mdl"` (two designs)       | single unified Tailwind design                            |
| CLI               | `flask_s3_viewer -p out/ -t mdl`                         | `flask_s3_viewer -p out/`                                 |
| Path traversal    | reached `cache.py` and crashed (`OSError`) or wrote outside `cache_dir` | rejected with HTTP 400 + `InvalidPrefix`        |
| Flask version     | Flask 2.x                                                | Flask 3.0+ required                                       |
| boto3 version     | 1.28.x                                                   | 1.34+ required                                            |
| Type hints        | partial                                                  | mypy-checked                                              |

## Step-by-step

### 1. Bump Python and dependency floor

- Python 3.10+ is required.
- Update `requirements.txt` / `pyproject.toml`:
  ```diff
  - flask==2.3.2
  - boto3==1.28.22
  + flask==3.0.3
  + boto3==1.34.131
  ```

### 2. Drop `.register()`

**Before**
```python
s3viewer = FlaskS3Viewer(app, namespace="bucket", config={...})
s3viewer.register()
```

**After**
```python
FlaskS3Viewer(app, namespace="bucket", config={...})
```

The constructor stores the instance in `app.extensions["flask_s3_viewer"][namespace]` and registers the blueprint exactly once per app.

For deferred initialization (factory pattern):
```python
viewer = FlaskS3Viewer(namespace="bucket", config={...})

def create_app():
    app = Flask(__name__)
    viewer.init_app(app)
    return app
```

### 3. Add an `app` argument to `get_instance` / `get_boto_client` / `get_boto_session`

These are now `staticmethod(app, namespace)`.

**Before**
```python
inst   = FlaskS3Viewer.get_instance("bucket")
client = FlaskS3Viewer.get_boto_client("bucket")
sess   = FlaskS3Viewer.get_boto_session("bucket")
```

**After**
```python
inst   = FlaskS3Viewer.get_instance(app, "bucket")
client = FlaskS3Viewer.get_boto_client(app, "bucket")
sess   = FlaskS3Viewer.get_boto_session(app, "bucket")
```

Inside a request you can also use `current_app`:
```python
from flask import current_app
inst = current_app.extensions["flask_s3_viewer"]["bucket"]
```

### 4. Handle duplicate-namespace errors

Registering the same namespace twice now raises:
```
ValueError: FlaskS3Viewer namespace 'bucket' is already registered on this app.
```

If your code intentionally re-initialized the same namespace, restructure to construct once and reuse the returned instance (or use distinct namespaces).

### 5. Expect HTTP 404 for unknown namespaces

A request to `/<unregistered-ns>/files` previously hit a `KeyError` and returned HTTP 500. It now returns 404 with no body. Update any client that depended on the 500 status.

### 6. Single template design

The `base/` and `mdl/` template directories are gone. Everything is unified under `flask_s3_viewer/blueprints/templates/` with a Tailwind + HTMX design.

If you customized templates by overriding the `template_folder`:
- Update your overrides to the new file names: `layout.html`, `files.html`, `_file_list.html`, `_pagination.html`, `_upload_form.html`, `error.html`.
- The `template_namespace="base"|"mdl"` constructor argument still accepts a value (for compatibility) but emits a `DeprecationWarning` and is ignored.

### 7. CLI: drop `--template`

**Before**
```bash
flask_s3_viewer -p ./templates_out -t mdl
```

**After**
```bash
flask_s3_viewer -p ./templates_out
```

The CLI now copies the single unified `templates/` directory.

### 8. `prefix` path-traversal validation

User-supplied prefixes (`/files?prefix=...`, `POST /files`, `POST /files/presign`, `DELETE /files/<key>`) are now validated. The following tokens raise `InvalidPrefix` → HTTP 400:

- `..` (parent traversal)
- `.` (current dir)
- empty segments (e.g. `foo//bar`)
- backslash (`\`)

If your clients sent any of these, expect HTTP 400 instead of the previous 200/500. URL-encoded variants (`%2e%2e`, `%2f%2f`, `%5c`) decode and are rejected too.

### 9. `base_path` normalization

A leading `/` in `base_path` (e.g. `"/test"`) used to crash with `OSError: Read-only file system: '/test'` because the cache layer treated it as an absolute path. It is now stripped on construction so `"/test"`, `"//test"`, and `"test"` are all normalized to `"test"`.

### 10. HTMX `DELETE` response status

The HTMX flow returns HTTP **200** on successful delete (so HTMX can swap the row out). Non-HTMX clients (no `HX-Request` header) still receive **204**. If you wrote a custom client that always expected 204, switch to accepting 200 or stop sending the `HX-Request` header.

### 11. `Singleton` metaclass is gone

If you relied on `FlaskS3Viewer._instances` (an undocumented class variable populated by the metaclass), use the new app-bound registry:

```python
app.extensions["flask_s3_viewer"]            # {namespace: FlaskS3Viewer}
```

`type(FlaskS3Viewer).__name__` is now `'type'`.

## What did *not* change

- Constructor signature for the common case: `FlaskS3Viewer(app, namespace=..., config={...})` still works.
- `add_new_one(...)` is still the recommended way to add another bucket.
- URL patterns: `/<bucket-namespace>/files`, `/<bucket-namespace>/files/<key>`, `/<bucket-namespace>/files/presign` — unchanged.
- Template variables (`FS3V_CONTENTS`, `FS3V_PREFIXES`, `FS3V_NEXT_TOKEN`, `FS3V_OBJECT_HOSTNAME`, `FS3V_UPLOAD_TYPE`) — unchanged.
- Cache file format — same `pickle`-based scheme. Old caches remain readable; only the *paths* may differ if you used a leading `/` in `base_path`.
- Presigned upload flow — same JSON contract on `/files/presign`.

## Smoke test after migration

```bash
pip install --upgrade flask_s3_viewer
python -c "from flask import Flask; from flask_s3_viewer import FlaskS3Viewer; \
    FlaskS3Viewer(Flask(__name__), namespace='smoke', config={'bucket_name': 'x', 'region_name': 'us-east-1'}); \
    print('OK')"
```

## Getting help

- Open an issue: https://github.com/hidekuma/flask-s3-viewer/issues
- Stable release: `1.0.0`
