"""Tests for the optional auth + permission framework (v1.0).

Covers:
  - allow-all defaults (legacy anonymous experience preserved).
  - ``auth_enabled`` toggle: stays False until the caller opts in.
  - ``email_allowlist`` builder behaviour.
  - ``@require`` enforcement: 401 on missing identity, 403 on permission deny.
  - Google OAuth route registration (404 when not configured).
  - ``/auth/login`` redirect kicks the user into Google sign-in.
  - ``configure_google_oauth`` fails loudly without ``app.secret_key``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.auth import (
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_LIST,
    ACTION_UPLOAD,
    allow_all_auth,
    allow_all_permissions,
    email_allowlist,
)


def _make_app(s3_bucket, tmp_path, **viewer_kwargs) -> Flask:
    """Spin up a fresh Flask app + viewer with optional auth kwargs."""
    _client, bucket = s3_bucket
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret-key'
    config = {
        'profile_name': None,
        'bucket_name': bucket,
        'region_name': 'us-east-1',
        'access_key': 'testing',
        'secret_key': 'testing',
        'cache_dir': str(tmp_path / 'cache'),
        'use_cache': True,
        'ttl': 60,
    }
    config.update(viewer_kwargs.pop('config', {}))
    FlaskS3Viewer(
        app,
        namespace='fsv-auth',
        config=config,
        **viewer_kwargs,
    )
    return app


# ---------------------------------------------------------------------------
# Default behaviour — no auth wired up
# ---------------------------------------------------------------------------

def test_auth_disabled_by_default(s3_bucket, tmp_path):
    """The legacy anonymous experience: no callbacks → auth_enabled = False."""
    app = _make_app(s3_bucket, tmp_path)
    viewer = app.extensions['flask_s3_viewer']['fsv-auth']
    assert viewer.auth_enabled is False
    assert viewer.auth_callback is allow_all_auth
    assert viewer.permission_callback is allow_all_permissions


def test_listing_is_public_when_auth_disabled(s3_bucket, tmp_path):
    """Without auth wiring, file listing returns 200 to an anonymous client."""
    app = _make_app(s3_bucket, tmp_path)
    resp = app.test_client().get('/fsv-auth/files')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# auth_enabled toggle — any opt-in flag flips it on
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    'kwargs',
    [
        {'auth_callback': lambda _req: 'a@b.com'},
        {'permission_callback': lambda *a, **kw: True},
        {'allowed_emails': ['a@b.com']},
        {'allowed_domains': ['b.com']},
        {'google_client_id': 'xyz.apps.googleusercontent.com',
         'google_client_secret': 'secret'},
    ],
)
def test_any_auth_opt_in_enables_enforcement(s3_bucket, tmp_path, kwargs):
    """Each opt-in path (callback, allow-list, Google) flips ``auth_enabled``."""
    app = _make_app(s3_bucket, tmp_path, **kwargs)
    viewer = app.extensions['flask_s3_viewer']['fsv-auth']
    assert viewer.auth_enabled is True


def test_visible_namespaces_callback_drives_bucket_switcher(s3_bucket, tmp_path):
    s3_client, bucket = s3_bucket
    s3_client.create_bucket(Bucket='fsv-auth-private')

    allowed_by_email = {
        'alice@example.com': {'fsv-auth', 'private'},
        'bob@example.com': {'fsv-auth'},
    }

    def auth_callback(request):
        return request.headers.get('X-User')

    def visible_namespaces(email, _registry):
        return allowed_by_email.get(email, set())

    app = _make_app(
        s3_bucket,
        tmp_path,
        title='Public Bucket',
        auth_callback=auth_callback,
        permission_callback=lambda email, _action, namespace, _key: namespace in allowed_by_email.get(email, set()),
        visible_namespaces_callback=visible_namespaces,
    )
    app.extensions['flask_s3_viewer']['fsv-auth'].add_new_one(
        namespace='private',
        title='Private Bucket',
        auth_callback=auth_callback,
        permission_callback=lambda email, _action, namespace, _key: namespace in allowed_by_email.get(email, set()),
        visible_namespaces_callback=visible_namespaces,
        config={
            'profile_name': None,
            'bucket_name': 'fsv-auth-private',
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'private-cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )

    client = app.test_client()
    alice = client.get('/fsv-auth/files', headers={'X-User': 'alice@example.com'})
    bob = client.get('/fsv-auth/files', headers={'X-User': 'bob@example.com'})
    forbidden = client.get('/private/files', headers={'X-User': 'bob@example.com'})

    assert alice.status_code == 200
    assert b'Public Bucket' in alice.data
    assert b'Private Bucket' in alice.data
    assert bob.status_code == 200
    assert b'Public Bucket' in bob.data
    assert b'Private Bucket' not in bob.data
    assert forbidden.status_code == 403


# ---------------------------------------------------------------------------
# email_allowlist builder
# ---------------------------------------------------------------------------

def test_email_allowlist_matches_literal():
    check = email_allowlist(emails=['alice@example.com'])
    assert check('alice@example.com', ACTION_LIST, 'ns', None) is True
    assert check('Alice@Example.com', ACTION_LIST, 'ns', None) is True  # case-insensitive
    assert check('bob@example.com', ACTION_LIST, 'ns', None) is False


def test_email_allowlist_matches_domain():
    check = email_allowlist(domains=['example.com'])
    assert check('anyone@example.com', ACTION_LIST, 'ns', None) is True
    assert check('anyone@other.com', ACTION_LIST, 'ns', None) is False


def test_email_allowlist_domain_strips_leading_at():
    """``@example.com`` and ``example.com`` should behave identically."""
    check = email_allowlist(domains=['@example.com'])
    assert check('anyone@example.com', ACTION_LIST, 'ns', None) is True


def test_email_allowlist_rejects_empty_email():
    check = email_allowlist(emails=['a@b.com'], domains=['b.com'])
    assert check('', ACTION_LIST, 'ns', None) is False


def test_email_allowlist_either_emails_or_domains():
    """Builder accepts both, neither, or just one — OR semantics."""
    check = email_allowlist(emails=['vip@anywhere.io'], domains=['example.com'])
    assert check('vip@anywhere.io', ACTION_LIST, 'ns', None) is True
    assert check('staff@example.com', ACTION_LIST, 'ns', None) is True
    assert check('stranger@nope.org', ACTION_LIST, 'ns', None) is False


def test_email_allowlist_nfkc_normalizes_email_and_domain():
    check = email_allowlist(
        emails=['alice@example.com'],
        domains=['example.com'],
    )
    assert check('alice@ｅxample.com', ACTION_LIST, 'ns', None) is True
    assert check('ａｌｉｃｅ@example.com', ACTION_LIST, 'ns', None) is True


# ---------------------------------------------------------------------------
# @require enforcement on routes
# ---------------------------------------------------------------------------

def test_listing_returns_401_when_auth_required_but_anonymous(s3_bucket, tmp_path):
    """auth_callback returns None → @require kicks back a 401."""
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: None,
        permission_callback=lambda *a, **kw: True,
    )
    resp = app.test_client().get('/fsv-auth/files')
    assert resp.status_code == 401


def test_listing_returns_403_when_permission_denied(s3_bucket, tmp_path):
    """auth_callback succeeds but permission_callback returns False → 403."""
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'stranger@example.com',
        allowed_emails=['vip@example.com'],
    )
    resp = app.test_client().get('/fsv-auth/files')
    assert resp.status_code == 403


def test_htmx_permission_denied_returns_error_fragment_for_toast(s3_bucket, tmp_path):
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'stranger@example.com',
        permission_callback=lambda *_args: False,
    )

    resp = app.test_client().post(
        '/fsv-auth/files',
        headers={'HX-Request': 'true'},
    )

    assert resp.status_code == 403
    assert b'Forbidden' in resp.data
    assert b'<html' not in resp.data


def test_listing_returns_200_when_permitted(s3_bucket, tmp_path):
    """Identity + allow-list match → request flows through."""
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'vip@example.com',
        allowed_emails=['vip@example.com'],
    )
    resp = app.test_client().get('/fsv-auth/files')
    assert resp.status_code == 200


def test_delete_uses_action_delete_permission(s3_bucket, tmp_path):
    """Permission callback receives the ACTION_DELETE constant for delete routes."""
    seen: list[str] = []
    def perm(_email, action, _ns, _key):
        seen.append(action)
        return False  # always deny so the route stops at 403

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'a@b.com',
        permission_callback=perm,
    )
    resp = app.test_client().delete('/fsv-auth/files/some-key')
    assert resp.status_code == 403
    assert seen == [ACTION_DELETE]


def test_download_uses_action_download_permission(s3_bucket, tmp_path):
    seen: list[str] = []
    def perm(_email, action, _ns, _key):
        seen.append(action)
        return False

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'a@b.com',
        permission_callback=perm,
    )
    resp = app.test_client().get('/fsv-auth/files/foo.txt')
    assert resp.status_code == 403
    assert seen == [ACTION_DOWNLOAD]


def test_upload_path_uses_action_upload(s3_bucket, tmp_path):
    """POST /files routes through ACTION_UPLOAD even though it isn't @require'd."""
    seen: list[str] = []
    def perm(_email, action, _ns, _key):
        seen.append(action)
        return False

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'a@b.com',
        permission_callback=perm,
    )
    resp = app.test_client().post('/fsv-auth/files')
    assert resp.status_code == 403
    assert ACTION_UPLOAD in seen


def test_download_permission_receives_canonical_key(s3_bucket, tmp_path):
    seen: list[str | None] = []

    def perm(_email, _action, _ns, key):
        seen.append(key)
        return False

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'a@b.com',
        permission_callback=perm,
        config={
            'profile_name': None,
            'bucket_name': s3_bucket[1],
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'cache'),
            'use_cache': True,
            'ttl': 60,
            'base_path': 'team-a',
        },
    )
    resp = app.test_client().get('/fsv-auth/files/report.txt')
    assert resp.status_code == 403
    assert seen == ['team-a/report.txt']


def test_listing_permission_receives_canonical_prefix(s3_bucket, tmp_path):
    seen: list[str | None] = []

    def perm(_email, action, _ns, key):
        if action == ACTION_LIST:
            seen.append(key)
        return False

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'a@b.com',
        permission_callback=perm,
        config={
            'profile_name': None,
            'bucket_name': s3_bucket[1],
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'cache'),
            'use_cache': True,
            'ttl': 60,
            'base_path': 'team-a',
        },
    )
    resp = app.test_client().get('/fsv-auth/files?prefix=docs/')
    assert resp.status_code == 403
    assert seen == ['team-a/docs/']


def test_listing_cache_salt_varies_by_authenticated_user(s3_bucket, tmp_path):
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda req: req.headers.get('X-User'),
        permission_callback=lambda *a, **kw: True,
    )
    viewer = app.extensions['flask_s3_viewer']['fsv-auth']
    original_make_hash = viewer._cache.make_hash
    seen: list[str] = []

    def capture_make_hash(key: str) -> str:
        seen.append(key)
        return original_make_hash(key)

    viewer._cache.make_hash = capture_make_hash
    client = app.test_client()
    assert client.get('/fsv-auth/files', headers={'X-User': 'alice@example.com'}).status_code == 200
    assert client.get('/fsv-auth/files', headers={'X-User': 'bob@example.com'}).status_code == 200
    assert len(seen) >= 2
    assert 'alice@example.com' in seen[0]
    assert 'bob@example.com' in seen[1]


# ---------------------------------------------------------------------------
# Google OAuth route surface
# ---------------------------------------------------------------------------

def test_login_callback_return_404_when_google_not_configured(s3_bucket, tmp_path):
    """``/auth/login`` and ``/auth/callback`` are gated on ``google_client_id``."""
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: None,  # auth enabled, but no google_client_id
    )
    client = app.test_client()
    assert client.get('/auth/login').status_code == 404
    assert client.get('/auth/callback').status_code == 404


def test_logout_route_returns_404_when_auth_disabled(s3_bucket, tmp_path):
    """The logout route exists but 404s for the legacy no-auth deployment."""
    app = _make_app(s3_bucket, tmp_path)  # no auth wired
    assert app.test_client().get('/auth/logout').status_code == 404


def test_logout_route_available_even_without_google(s3_bucket, tmp_path):
    """Logout is gated on ``auth_enabled``, not on Google specifically — a
    custom auth_callback deployment can still call /auth/logout to clear
    whatever session marker was set up.
    """
    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: None,
    )
    resp = app.test_client().get('/auth/logout', follow_redirects=False)
    assert resp.status_code in (301, 302)


def test_google_oauth_requires_secret_key():
    """configure_google_oauth raises RuntimeError when app.secret_key is unset."""
    app = Flask(__name__)
    # No secret_key on purpose.
    from flask_s3_viewer.auth.google import configure_google_oauth
    with pytest.raises(RuntimeError, match='secret_key'):
        configure_google_oauth(app, 'cid', 'csecret')


def test_google_login_redirects_to_google(s3_bucket, tmp_path):
    """/auth/login kicks off the OAuth dance — Authlib emits a 302 to accounts.google.com."""
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
    )

    class FakeGoogle:
        def authorize_redirect(self, redirect_uri):
            from flask import redirect

            return redirect(
                f'https://accounts.google.com/o/oauth2/auth?redirect_uri={redirect_uri}'
            )

    app.extensions['flask_s3_viewer.oauth'] = SimpleNamespace(google=FakeGoogle())
    client = app.test_client()
    resp = client.get('/auth/login', follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert 'accounts.google.com' in resp.headers.get('Location', '')


def test_google_logout_clears_session(s3_bucket, tmp_path):
    """/auth/logout drops fsv_user_email from the session and redirects."""
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
    )
    client = app.test_client()
    with client.session_transaction() as s:
        s['fsv_user_email'] = 'me@example.com'
    resp = client.get('/auth/logout', follow_redirects=False)
    assert resp.status_code in (301, 302)
    with client.session_transaction() as s:
        assert 'fsv_user_email' not in s


def test_logout_rejects_external_next_redirect(s3_bucket, tmp_path):
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
    )
    resp = app.test_client().get(
        '/auth/logout?next=https://evil.example/phish',
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302)
    assert resp.headers['Location'] == '/'


def test_anonymous_get_redirects_to_login_when_google_configured(s3_bucket, tmp_path):
    """Browser-friendly behaviour: GET without identity → login redirect, not 401."""
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
    )
    resp = app.test_client().get('/fsv-auth/files', follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert '/auth/login' in resp.headers.get('Location', '')


def test_header_shows_user_email_and_logout_when_logged_in(s3_bucket, tmp_path):
    """The files header renders the user's email + a logout link
    pointing at the namespace-less ``/auth/logout`` route.
    """
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
        allowed_emails=['vip@example.com'],
    )
    client = app.test_client()
    with client.session_transaction() as s:
        s['fsv_user_email'] = 'vip@example.com'
    body = client.get('/fsv-auth/files').get_data(as_text=True)
    assert 'vip@example.com' in body
    assert '/auth/logout?next=' in body


def test_header_hides_user_widget_when_auth_disabled(s3_bucket, tmp_path):
    """No auth wired → no user widget / logout link in the rendered page."""
    app = _make_app(s3_bucket, tmp_path)
    body = app.test_client().get('/fsv-auth/files').get_data(as_text=True)
    assert 'Log out' not in body
    assert '/auth/logout' not in body


def test_session_auth_callback_reads_session(s3_bucket, tmp_path):
    """The default session-based callback returns whatever Google wrote earlier."""
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
        allowed_emails=['logged-in@example.com'],
    )
    client = app.test_client()
    with client.session_transaction() as s:
        s['fsv_user_email'] = 'logged-in@example.com'
    resp = client.get('/fsv-auth/files')
    assert resp.status_code == 200


def test_google_oauth_sets_secure_session_cookie_defaults(s3_bucket, tmp_path):
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
    )
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


# ---------------------------------------------------------------------------
# add_new_one — auth-related kwargs are now explicit and overridable
# ---------------------------------------------------------------------------

def test_add_new_one_inherits_auth_callback_when_omitted(s3_bucket, tmp_path):
    """Omitting ``auth_callback`` keeps the legacy behaviour: the child
    viewer inherits the parent's auth_callback. Regression guard for the
    backward-compat half of the v1.1.0 ``_INHERIT`` sentinel work."""
    s3_client, _ = s3_bucket
    s3_client.create_bucket(Bucket='fsv-auth-child')

    def parent_cb(_req):
        return 'parent@example.com'

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=parent_cb,
        permission_callback=lambda *a, **kw: True,
    )
    parent = app.extensions['flask_s3_viewer']['fsv-auth']
    child = parent.add_new_one(
        namespace='child-ns',
        config={
            'profile_name': None,
            'bucket_name': 'fsv-auth-child',
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'child-cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )
    assert child.auth_callback is parent_cb
    assert child.permission_callback is parent.permission_callback


def test_add_new_one_explicit_none_disables_auth_on_child(s3_bucket, tmp_path):
    """Passing ``auth_callback=None`` explicitly opts the child out of auth
    even when the parent has it wired up. Without the sentinel-based
    resolution this case was previously unreachable (``None or self.x``
    silently fell back to the parent)."""
    s3_client, _ = s3_bucket
    s3_client.create_bucket(Bucket='fsv-auth-open')

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'parent@example.com',
        permission_callback=lambda *a, **kw: True,
    )
    parent = app.extensions['flask_s3_viewer']['fsv-auth']
    child = parent.add_new_one(
        namespace='open-ns',
        auth_callback=None,
        permission_callback=None,
        config={
            'profile_name': None,
            'bucket_name': 'fsv-auth-open',
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'open-cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )
    # With no Google credentials inherited and explicit None on both
    # callbacks, the child falls back to the allow-all defaults.
    assert child.auth_callback is allow_all_auth
    assert child.permission_callback is allow_all_permissions
    # Listing is reachable anonymously on the open child namespace even
    # while the parent still enforces auth.
    resp = app.test_client().get('/open-ns/files')
    assert resp.status_code == 200


def test_add_new_one_custom_callback_replaces_parent(s3_bucket, tmp_path):
    """A custom callable handed to ``add_new_one`` is used verbatim,
    bypassing the parent's callback."""
    s3_client, _ = s3_bucket
    s3_client.create_bucket(Bucket='fsv-auth-custom')

    def custom_cb(_req):
        return 'custom@example.com'

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'parent@example.com',
        permission_callback=lambda *a, **kw: True,
    )
    parent = app.extensions['flask_s3_viewer']['fsv-auth']
    child = parent.add_new_one(
        namespace='custom-ns',
        auth_callback=custom_cb,
        config={
            'profile_name': None,
            'bucket_name': 'fsv-auth-custom',
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'custom-cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )
    assert child.auth_callback is custom_cb


def test_add_new_one_allowed_emails_inherits_when_omitted(s3_bucket, tmp_path):
    """``allowed_emails`` is now a private parent attribute, so omitting it
    on ``add_new_one`` re-applies the same allowlist to the child via a
    freshly-built ``email_allowlist`` permission callback."""
    s3_client, _ = s3_bucket
    s3_client.create_bucket(Bucket='fsv-auth-inherit-list')

    app = _make_app(
        s3_bucket, tmp_path,
        auth_callback=lambda _req: 'vip@example.com',
        allowed_emails=['vip@example.com'],
    )
    parent = app.extensions['flask_s3_viewer']['fsv-auth']
    # ``permission_callback`` is omitted too — the child must rebuild a
    # fresh email_allowlist from the inherited emails/domains.
    child = parent.add_new_one(
        namespace='inherit-list-ns',
        config={
            'profile_name': None,
            'bucket_name': 'fsv-auth-inherit-list',
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'inherit-list-cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )
    # The inherited allowlist still authorises vip@ and still denies others.
    assert child.permission_callback('vip@example.com', ACTION_LIST, 'ns', None) is True
    assert child.permission_callback('stranger@example.com', ACTION_LIST, 'ns', None) is False


def test_oauth_callback_requires_verified_email(s3_bucket, tmp_path):
    app = _make_app(
        s3_bucket, tmp_path,
        google_client_id='cid.apps.googleusercontent.com',
        google_client_secret='secret',
    )

    class FakeGoogle:
        def authorize_access_token(self):
            return {'userinfo': {'email': 'me@example.com', 'email_verified': False}}

    app.extensions['flask_s3_viewer.oauth'] = SimpleNamespace(google=FakeGoogle())
    client = app.test_client()
    resp = client.get('/auth/callback')
    assert resp.status_code == 401
