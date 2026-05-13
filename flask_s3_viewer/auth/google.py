"""Google OAuth 2.0 sign-in built on top of Authlib.

Installs ``/auth/login``, ``/auth/callback``, ``/auth/logout`` on the
viewer blueprint. The ``auth_callback`` reads the signed-cookie session
that the callback writes after a successful OIDC userinfo lookup.

Activation: pass ``google_client_id`` + ``google_client_secret`` to
``FlaskS3Viewer(...)`` and install the optional ``[auth]`` extra::

    pip install "flask_s3_viewer[auth]"

Configure OAuth in Google Cloud Console:

  - OAuth client type: Web application
  - Authorized redirect URI: ``https://<your-host>/<namespace>/auth/callback``
  - Authorized scopes: ``openid email profile`` (the wrapper requests these)

Note: there is exactly one OAuth client per Flask app (shared across all
namespaces). Per-namespace allow-lists are evaluated in the
``permission_callback``, not at the OAuth layer.
"""
from __future__ import annotations

from typing import Any

from flask import (
    Flask,
    abort,
    current_app,
    redirect,
    request,
    session,
    url_for,
)

_AUTHLIB_MISSING_MSG = (
    "Google OAuth requires the optional 'authlib' dependency. "
    "Install with: pip install 'flask_s3_viewer[auth]'"
)


def configure_google_oauth(
    app: Flask,
    client_id: str,
    client_secret: str,
) -> None:
    """Register a Google OAuth client on ``app.extensions['authlib.integrations.flask_client']``.

    Called exactly once per app at ``init_app`` time. Safe to call again
    with the same credentials (idempotent — Authlib's ``OAuth.register``
    skips duplicates).
    """
    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError as e:  # pragma: no cover - import-time only
        raise RuntimeError(_AUTHLIB_MISSING_MSG) from e

    oauth = app.extensions.get('flask_s3_viewer.oauth')
    if oauth is None:
        oauth = OAuth(app)
        app.extensions['flask_s3_viewer.oauth'] = oauth

    if 'google' not in oauth._clients:
        oauth.register(
            name='google',
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )

    # The Flask session cookie needs a SECRET_KEY; warn loudly if the
    # deployer forgot. We don't set it ourselves — that would be a
    # silent security regression.
    if not app.secret_key:
        raise RuntimeError(
            "Flask app.secret_key must be set before enabling Google OAuth — "
            "it signs the session cookie that carries the logged-in email."
        )


def session_auth_callback(_request: Any) -> str | None:
    """Default ``auth_callback`` for the Google flow — reads the email
    that the OAuth callback wrote into the session.
    """
    return session.get('fsv_user_email')


# ---------------------------------------------------------------------------
# Route handlers — wired by view.py only when google_client_id is set
# ---------------------------------------------------------------------------

def login() -> Any:
    """Kick off the OAuth dance by redirecting to Google."""
    oauth = current_app.extensions.get('flask_s3_viewer.oauth')
    if oauth is None:
        abort(500, 'Google OAuth not configured on this app.')
    google = oauth.google
    # Where to come back AFTER the callback. Default: current namespace's files.
    next_url = request.args.get('next') or url_for('flask_s3_viewer.files')
    session['fsv_login_next'] = next_url
    redirect_uri = url_for('flask_s3_viewer.auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


def auth_callback() -> Any:
    """Google returns here. Exchange the code, fetch userinfo, persist
    the email in the session, then redirect back to the caller.
    """
    oauth = current_app.extensions.get('flask_s3_viewer.oauth')
    if oauth is None:
        abort(500, 'Google OAuth not configured on this app.')
    google = oauth.google
    token = google.authorize_access_token()
    # Authlib parses the OIDC id_token into ``userinfo`` automatically
    # when the discovery doc was loaded. Fall back to /userinfo just
    # in case (some installs disable the inline parse).
    info = token.get('userinfo') or google.userinfo()
    email = (info or {}).get('email')
    if not email:
        abort(401, 'Google did not return a verified email.')
    session['fsv_user_email'] = email
    return redirect(session.pop('fsv_login_next', '/'))


def logout() -> Any:
    """Drop the session marker. Google's session is untouched (the
    deployer can wire ``hd`` / ``prompt=login`` if they need a hard
    re-auth at the IdP).
    """
    session.pop('fsv_user_email', None)
    next_url = request.args.get('next') or '/'
    return redirect(next_url)
