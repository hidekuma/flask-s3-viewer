import logging
import os

from flask import Flask, session

from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.aws.ref import Region

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(asctime)s: %(message)s")

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

# FlaskS3Viewer Init
FS3V_NAMESPACE = "flask-s3-viewer"
s3viewer = FlaskS3Viewer(
    app,  # Flask app
    namespace=FS3V_NAMESPACE,  # namespace be unique
    title="Piccoma BOX",
    # upload_type="presign",
    object_hostname="http://flask-s3-viewer.com",  # file's hostname
    # ---- Google OAuth (optional) ----
    # Comment out the four kwargs below to fall back to the legacy
    # anonymous experience.
    google_client_id=GOOGLE_CLIENT_ID or None,
    google_client_secret=GOOGLE_CLIENT_SECRET or None,
    allowed_emails=ALLOWED_EMAILS or None,
    allowed_domains=ALLOWED_DOMAINS or None,
    config={  # Bucket configs and else
        "profile_name": "fsv-test",
        "access_key": None,
        "secret_key": None,
        "region_name": Region.TOKYO.value,
        "endpoint_url": None,
        "bucket_name": "fsv-test-0513",
        "cache_dir": "/tmp/flask_s3_viewer",
        "use_cache": True,
        "base_path": "/test",
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


@app.route("/index")
def index():
    return "Your app index page"


# Usage: python example.py test (run debug mode)
if __name__ == "__main__":
    app.run(debug=True, port=3000)
