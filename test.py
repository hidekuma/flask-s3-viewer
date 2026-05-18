import logging
import os

from flask import Flask, request, session

from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.aws.ref import Region

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(asctime)s: %(message)s")

# ---------------------------------------------------------------------------
# Audit logger setup (flask_s3_viewer.audit)
#
# Independent of the host root logger above. The audit logger emits one
# record per S3 CRUD action (list/download/upload/delete/presign) with
# extra fields:
#   action / namespace / key / user / result / status_code /
#   client_ip / user_agent / request_id (+ error on failure)
#
# Multi-file uploads emit one row per file; every row in the same Flask
# request shares one `request_id` (8 hex chars) so plain-text grep can
# group them, e.g. `grep "req=a1b2c3d4" audit.log`.
#
# Copy this block into your own app to start auditing — adjust the
# handler (StreamHandler / FileHandler / structured JSON via
# python-json-logger) and the formatter to fit your log pipeline.
# ---------------------------------------------------------------------------
audit_logger = logging.getLogger("flask_s3_viewer.audit")
audit_handler = logging.StreamHandler()
audit_handler.setFormatter(logging.Formatter(
    "AUDIT %(asctime)s %(levelname)s "
    "action=%(action)s namespace=%(namespace)s "
    "key=%(key)s user=%(user)s result=%(result)s "
    "status=%(status_code)s req=%(request_id)s "
    "ip=%(client_ip)s"
))
audit_logger.addHandler(audit_handler)
audit_logger.setLevel(logging.INFO)
# Set False if you do NOT want audit lines also reaching the root
# handler installed by logging.basicConfig above. Left True here so
# the demo shows both streams side by side.
# audit_logger.propagate = False


# Optional: demo-only PII-soft user field. Production policies should
# replace this with the redaction filter that matches your compliance
# requirements (see docs/source/usage/configuration.rst).
class _DemoUserRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        user = getattr(record, "user", None)
        if user and "@" in user:
            local, domain = user.split("@", 1)
            record.user = f"{local[:2]}***@{domain}"
        return True


# Comment the next line out to see raw email addresses in the demo log.
audit_logger.addFilter(_DemoUserRedactFilter())

app = Flask(__name__)

# For test, disable template caching
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 1
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Google OAuth requires a signed-cookie session. Use a fixed value during
# local testing so the session survives restarts; rotate (or use
# os.urandom(32)) anywhere near production.
app.secret_key = os.environ.get("FSV_SECRET_KEY", "local-dev-secret-key-change-me")

# ---------------------------------------------------------------------------
# Google OAuth — fill these in (or export GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).
#
# Setup in Google Cloud Console (https://console.cloud.google.com/apis/credentials):
#   1. Create credentials → OAuth client ID → Web application
#   2. Authorized redirect URI:
#        http://localhost:3000/auth/callback
#      (auth routes live OUTSIDE the namespace prefix — one URI per app,
#       independent of how many FlaskS3Viewer namespaces you mount.)
#   3. Copy Client ID + Client secret here (or into the env vars).
#
# Install the optional extra once:
#   pip install -e ".[auth]"
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

# Either explicit emails, or whole domains, or both. Leave both empty during
# the first round-trip if you just want to verify the OAuth dance — every
# logged-in Google user will pass, and you can tighten later.
ALLOWED_EMAILS: list[str] = [
    # "you@example.com",
]
ALLOWED_DOMAINS: list[str] = [
    # "mycompany.com",
]

# ---------------------------------------------------------------------------
# RBAC example
#
# The UI bucket switcher uses `visible_namespaces_callback`, but hard
# authorization still lives in `permission_callback`. This example scopes
# access by namespace *and* prefix, so the same bucket can expose different
# folders to different users.
#
# Note: this is a route-level gate. If you need the root listing itself to hide
# every disallowed object, add row-level filtering in the listing query too.
# ---------------------------------------------------------------------------
RBAC_POLICY: dict[str, dict[str, dict[str, set[str]]]] = {
    # Replace these with your real Google account emails.
    "joseph.jeong@kakaopiccoma.com": {
        "flask-s3-viewer": {
            "list": {""},
            "upload": {"test/aaaa/"},
            "presign": {"test/aaaa/"},
            "download": {"test/aaaa/"},
            "delete": {"test/aaaa/"},
        },
        "private": {
            "list": {""},
            "upload": {""},
            "presign": {""},
            "download": {""},
            "delete": {""},
        },
    },
    # "viewer@example.com": {
    #     "flask-s3-viewer": {
    #         "list": {"root/shared/"},
    #         "download": {"root/shared/"},
    #     },
    # },
}


def current_user_email(req: request) -> str | None:
    return session.get("fsv_user_email")


def _path_allowed(key: str | None, allowed_prefixes: set[str]) -> bool:
    if key is None:
        return False
    if not allowed_prefixes:
        return False
    return any(key == prefix or key.startswith(prefix) for prefix in allowed_prefixes)


def can_access(email: str | None, action: str, namespace: str, key: str | None) -> bool:
    if not email:
        return False
    namespace_policy = RBAC_POLICY.get(email, {}).get(namespace, {})
    return _path_allowed(key, namespace_policy.get(action, set()))


def visible_buckets(email: str | None, registry: dict) -> set[str]:
    if not email:
        return set()
    # Returning only registered namespaces keeps stale policy entries out of
    # the switcher if a bucket is temporarily disabled.
    return set(RBAC_POLICY.get(email, {})).intersection(registry.keys())


# FlaskS3Viewer Init
s3viewer = FlaskS3Viewer(
    app,  # Flask app
    namespace="flask-s3-viewer",  # namespace be unique
    title="Asset Hub",
    logo_path="./logo.svg",
    upload_type="presign",
    object_hostname="https://fsv-test-0513.s3.ap-northeast-1.amazonaws.com",  # file's hostname
    # ---- Google OAuth (optional) ----
    # Comment out the four kwargs below to fall back to the legacy
    # anonymous experience.
    google_client_id=GOOGLE_CLIENT_ID or None,
    google_client_secret=GOOGLE_CLIENT_SECRET or None,
    auth_callback=current_user_email,
    permission_callback=can_access,
    visible_namespaces_callback=visible_buckets,
    config={  # Bucket configs and else
        "profile_name": "fsv-test",
        "access_key": None,
        "secret_key": None,
        "region_name": Region.TOKYO.value,
        "endpoint_url": None,
        "bucket_name": "fsv-test-0513",
        "cache_dir": "/tmp/flask_s3_viewer",
        "use_cache": False,
        "base_path": "/test",
        "timezone": "Asia/Tokyo",
        "ttl": 86400,
    },
)

s3viewer.add_new_one(
    namespace="private",
    title="Storage Console",
    logo_path="./logo.svg",
    upload_type="presign",
    object_hostname="https://fsv-test-0513.s3.ap-northeast-1.amazonaws.com",
    config={
        "profile_name": "fsv-test",
        "access_key": None,
        "secret_key": None,
        "region_name": Region.TOKYO.value,
        "endpoint_url": None,
        "bucket_name": "fsv-test-0513",
        "cache_dir": "/tmp/flask_s3_viewer_private",
        "use_cache": False,
        "base_path": "/private",
        "timezone": "Asia/Tokyo",
        "ttl": 86400,
    },
)


@app.route("/whoami")
def whoami() -> dict:
    """Debug endpoint — inspect the OAuth session state."""
    return {
        "fsv_user_email": session.get("fsv_user_email"),
        "session_keys": list(session.keys()),
        "auth_enabled": s3viewer.auth_enabled,
        "google_configured": bool(s3viewer.google_client_id),
        "visible_buckets": sorted(
            visible_buckets(session.get("fsv_user_email"), app.extensions["flask_s3_viewer"])
        ),
    }


# Init another one
# s3viewer.add_new_one(
#     object_hostname='http://namespace2.com',
#     namespace='np2',  # namespace be unique
#     upload_type='presign',
#     config={
#         'profile_name': 'test',
#         'region_name': Region.SEOUL.value,
#         'bucket_name': 'hwjeongtest'
#     }
# )

# You can see registerd configs
# print(s3viewer.FLASK_S3_VIEWER_BUCKET_CONFIGS)

# You can use boto3's session and client if you want
# print(FlaskS3Viewer.get_boto_client(app, FS3V_NAMESPACE))
# print(FlaskS3Viewer.get_boto_session(app, FS3V_NAMESPACE))

# v1.0+: blueprint registration is automatic in FlaskS3Viewer(app, ...).
# The legacy `s3viewer.register()` call is no longer needed and has been removed.


@app.route("/")
def index():
    return "Your app index page"


# Usage: python example.py test (run debug mode)
if __name__ == "__main__":
    app.run(debug=True, port=3000)
