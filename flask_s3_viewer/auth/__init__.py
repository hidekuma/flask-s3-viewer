"""Authentication & authorization for flask-s3-viewer.

Two layers, both opt-in (the package works exactly as before when
nothing here is wired up):

  - **Hook framework** (no extra dependency)
      ``auth_callback(request) -> email | None``  — *who is asking*
      ``permission_callback(email, action, namespace, key) -> bool`` —
      *can they do it*
      Both default to "allow everyone" which preserves the legacy
      anonymous experience.

  - **Google OAuth built-in** (requires ``flask_s3_viewer[auth]``,
    i.e. ``authlib``)
      ``FlaskS3Viewer(..., google_client_id=..., google_client_secret=...,
                       allowed_emails=[...], allowed_domains=[...])``
      Installs ``/auth/login``, ``/auth/callback``, ``/auth/logout``
      routes on the blueprint and a default ``auth_callback`` that
      reads the signed-cookie session. Emails / domains form the
      built-in allow-list.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Any

# Action constants — used by view.py and permission_callback callers.
ACTION_LIST = 'list'         # GET /files (folder listing)
ACTION_DOWNLOAD = 'download' # GET /files/<key>
ACTION_UPLOAD = 'upload'     # POST /files (mkdir or file)
ACTION_DELETE = 'delete'     # DELETE /files/<key>
ACTION_PRESIGN = 'presign'   # POST /files/presign

ALL_ACTIONS = (
    ACTION_LIST,
    ACTION_DOWNLOAD,
    ACTION_UPLOAD,
    ACTION_DELETE,
    ACTION_PRESIGN,
)

# Type aliases — keep at module scope so they're importable from tests.
AuthCallback = Callable[[Any], 'str | None']
PermissionCallback = Callable[[str, str, str, 'str | None'], bool]


def allow_all_auth(_request: Any) -> str | None:
    """Default ``auth_callback``: anonymous (no user, no enforcement).

    Returning ``None`` does NOT mean "deny" — the view layer treats a
    ``None`` viewer auth_callback as "no auth required". This preserves
    the legacy unauthenticated experience verbatim.
    """
    return None


def allow_all_permissions(
    _email: str, _action: str, _namespace: str, _key: str | None,
) -> bool:
    """Default ``permission_callback``: allow any action for any user."""
    return True


def email_allowlist(emails: list[str] | set[str] | None = None,
                    domains: list[str] | set[str] | None = None
                    ) -> PermissionCallback:
    """Convenience builder: permit the listed emails / domains, deny
    everyone else regardless of action.

    Either argument can be omitted; passing both is "OR" (an email
    matches if it's literally listed OR ends with ``@<allowed_domain>``).
    """
    def _norm(value: str) -> str:
        return unicodedata.normalize('NFKC', value).strip().lower()

    email_set = {_norm(e) for e in (emails or [])}
    domain_set = {_norm(d).lstrip('@') for d in (domains or [])}

    def check(email: str, _action: str, _namespace: str, _key: str | None) -> bool:
        if not email:
            return False
        e = _norm(email)
        if e in email_set:
            return True
        if '@' in e:
            domain = e.rsplit('@', 1)[1]
            if domain in domain_set:
                return True
        return False

    return check
