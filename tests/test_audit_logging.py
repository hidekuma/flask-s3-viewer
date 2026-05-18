"""Audit logging tests for flask_s3_viewer.audit.

Verifies that every S3 CRUD blueprint action produces exactly one
structured audit record, that user identity flows into the ``user``
field, that denied/error cases set the right level + status_code, and
that log injection via control characters in user-controllable fields
is neutralised.

These tests use a dedicated ``logging.Handler`` attached to the
``flask_s3_viewer.audit`` logger so they do not depend on caplog's
propagation configuration; the audit logger is left with its default
``propagate=True`` so host apps can still route records through root.
"""
from __future__ import annotations

import io
import logging
import urllib.parse
from typing import Any

import pytest
from flask import Flask

from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.audit import MAX_UA_LEN, _sanitize


# ---------------------------------------------------------------------------
# Handler that captures every record emitted by flask_s3_viewer.audit
# ---------------------------------------------------------------------------

class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        self.records.append(record)


@pytest.fixture
def audit_records() -> Any:
    """Attach a capture handler to flask_s3_viewer.audit for the test duration."""
    handler = _CaptureHandler()
    audit_logger = logging.getLogger('flask_s3_viewer.audit')
    previous_level = audit_logger.level
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.DEBUG)
    try:
        yield handler.records
    finally:
        audit_logger.removeHandler(handler)
        audit_logger.setLevel(previous_level)


def _make_app(s3_bucket, tmp_path, **viewer_kwargs) -> Flask:
    """Build a fresh Flask app + FlaskS3Viewer for one test."""
    _client, bucket = s3_bucket
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'audit-test-secret'
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
        namespace='fsv-audit',
        config=config,
        **viewer_kwargs,
    )
    return app


def _ns_path(suffix: str) -> str:
    return f'/fsv-audit{suffix}'


def _records_for(records, action: str) -> list[logging.LogRecord]:
    return [r for r in records if getattr(r, 'action', None) == action]


# ---------------------------------------------------------------------------
# Action-by-action happy path: one record per request, correct fields.
# ---------------------------------------------------------------------------

class TestActionHappyPath:
    def test_list_emits_one_record(self, s3_bucket, tmp_path, audit_records) -> None:
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().get(_ns_path('/files'))
        assert resp.status_code == 200
        listing = _records_for(audit_records, 'list')
        assert len(listing) == 1
        r = listing[0]
        assert r.user == 'anonymous'
        assert r.result == 'ok'
        assert r.status_code == 200
        assert r.namespace == 'fsv-audit'
        # Default INFO level for success.
        assert r.levelno == logging.INFO

    def test_download_emits_record_with_canonical_key(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='hello.txt', Body=b'world')
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().get(_ns_path('/files/hello.txt'))
        assert resp.status_code == 200
        download = _records_for(audit_records, 'download')
        assert len(download) == 1
        assert download[0].key == 'hello.txt'
        assert download[0].result == 'ok'
        assert download[0].status_code == 200

    def test_upload_emits_record(self, s3_bucket, tmp_path, audit_records) -> None:
        app = _make_app(s3_bucket, tmp_path)
        data = {
            'files[]': (io.BytesIO(b'payload'), 'audit-upload.txt'),
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 201
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 1
        assert upload[0].result == 'ok'
        assert upload[0].status_code == 201

    def test_delete_emits_record(self, s3_bucket, tmp_path, audit_records) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='gone.txt', Body=b'bye')
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().delete(_ns_path('/files/gone.txt'))
        assert resp.status_code == 204
        deletes = _records_for(audit_records, 'delete')
        assert len(deletes) == 1
        assert deletes[0].result == 'ok'
        assert deletes[0].status_code == 204
        assert deletes[0].key == 'gone.txt'

    def test_presign_emits_record(self, s3_bucket, tmp_path, audit_records) -> None:
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().post(
            _ns_path('/files/presign'),
            data={'prefix': '', 'file_list': 'new.txt'},
        )
        assert resp.status_code == 200
        presigns = _records_for(audit_records, 'presign')
        assert len(presigns) == 1
        assert presigns[0].result == 'ok'
        assert presigns[0].status_code == 200


# ---------------------------------------------------------------------------
# Denied paths — 401 (anonymous when auth required), 403 (permission denied)
# ---------------------------------------------------------------------------

class TestDenied:
    def test_anonymous_blocked_emits_warning_401(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: None,
            permission_callback=lambda *a, **kw: True,
        )
        resp = app.test_client().get(_ns_path('/files'))
        assert resp.status_code == 401
        listing = _records_for(audit_records, 'list')
        assert len(listing) == 1
        r = listing[0]
        assert r.result == 'denied'
        assert r.status_code == 401
        assert r.user == 'anonymous'
        assert r.levelno == logging.WARNING

    def test_permission_denied_emits_warning_403(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: 'stranger@example.com',
            permission_callback=lambda *a, **kw: False,
        )
        resp = app.test_client().get(_ns_path('/files'))
        assert resp.status_code == 403
        listing = _records_for(audit_records, 'list')
        assert len(listing) == 1
        r = listing[0]
        assert r.result == 'denied'
        assert r.status_code == 403
        assert r.user == 'stranger@example.com'
        assert r.levelno == logging.WARNING

    def test_delete_denied_carries_canonical_key(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: 'a@b.com',
            permission_callback=lambda *a, **kw: False,
        )
        resp = app.test_client().delete(_ns_path('/files/locked.txt'))
        assert resp.status_code == 403
        deletes = _records_for(audit_records, 'delete')
        assert len(deletes) == 1
        assert deletes[0].key == 'locked.txt'
        assert deletes[0].user == 'a@b.com'


# ---------------------------------------------------------------------------
# Anonymous user: callback unset → user='anonymous'.
# ---------------------------------------------------------------------------

class TestAnonymous:
    def test_no_auth_callback_records_anonymous(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().get(_ns_path('/files'))
        assert resp.status_code == 200
        listing = _records_for(audit_records, 'list')
        assert listing[0].user == 'anonymous'

    def test_email_propagates_into_record(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: 'vip@example.com',
            permission_callback=lambda *a, **kw: True,
        )
        resp = app.test_client().get(_ns_path('/files'))
        assert resp.status_code == 200
        listing = _records_for(audit_records, 'list')
        assert listing[0].user == 'vip@example.com'


# ---------------------------------------------------------------------------
# Error / abort paths — status_code reflects the response code.
# ---------------------------------------------------------------------------

class TestErrors:
    def test_invalid_prefix_records_400(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().get(_ns_path('/files?prefix=../etc'))
        assert resp.status_code == 400
        listing = _records_for(audit_records, 'list')
        assert len(listing) == 1
        assert listing[0].status_code == 400
        assert listing[0].result == 'error'

    def test_missing_object_records_download_404(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        # GET on a missing key returns a rendered 404 body — not an
        # abort — so the wrapping decorator extracts 404 from the
        # tuple response.
        resp = app.test_client().get(_ns_path('/files/missing.txt'))
        assert resp.status_code == 404
        download = _records_for(audit_records, 'download')
        assert len(download) == 1
        assert download[0].status_code == 404
        assert download[0].result == 'error'

    def test_unsatisfiable_range_records_416(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='small.txt', Body=b'abc')
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().get(
            _ns_path('/files/small.txt'),
            headers={'Range': 'bytes=999-1000'},
        )
        assert resp.status_code == 416
        download = _records_for(audit_records, 'download')
        assert len(download) == 1
        assert download[0].status_code == 416


# ---------------------------------------------------------------------------
# Log injection — control bytes are escaped in user-controllable fields.
# ---------------------------------------------------------------------------

class TestLogInjection:
    @pytest.mark.parametrize(
        'control_char',
        ['\n', '\r', '\t', '\x00', '\x07', '\x1b'],
    )
    def test_key_with_control_chars_is_escaped_at_emit(
        self, audit_records, control_char,
    ) -> None:
        """Direct unit check on emit(): every ASCII control byte in a key
        argument is replaced with a \\xNN escape sequence so an attacker
        can't smuggle a fake row into the audit stream.
        """
        from flask_s3_viewer.audit import emit

        emit(
            action='download',
            namespace='ns',
            key=f'forged{control_char}key',
            user='a@b.com',
            result='ok',
            status_code=200,
        )
        assert audit_records, 'expected one audit record'
        r = audit_records[-1]
        assert control_char not in r.key
        msg = r.getMessage()
        # Forged newlines/CRs must never reach the on-disk line.
        assert '\n' not in msg
        assert '\r' not in msg
        # The req=<id> tail token must always be present.
        assert 'req=' in msg

    def test_blueprint_request_with_tab_in_key_escapes_field(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """End-to-end check: a printable-but-control byte (TAB) survives
        the werkzeug router and the emit layer must still escape it.
        """
        app = _make_app(s3_bucket, tmp_path)
        app.test_client().get(_ns_path('/files/' + urllib.parse.quote('with\tcontrol')))
        download = _records_for(audit_records, 'download')
        assert download, 'expected one download record'
        r = download[0]
        assert '\t' not in r.key
        assert '\\x09' in r.key

    def test_email_with_newline_is_escaped(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: 'evil@b.com\nAUDIT-LINE-FORGED',
            permission_callback=lambda *a, **kw: True,
        )
        app.test_client().get(_ns_path('/files'))
        listing = _records_for(audit_records, 'list')
        assert listing, 'expected one listing record'
        r = listing[0]
        assert '\n' not in r.user
        assert '\\x0a' in r.user

    def test_ua_truncated_when_oversized(self) -> None:
        # Direct unit check on _sanitize so the test does not rely on a
        # browser sending a multi-KB UA through the Flask test client.
        massive = 'x' * (MAX_UA_LEN + 100)
        result = _sanitize(massive, limit=MAX_UA_LEN)
        assert len(result) == MAX_UA_LEN + 3  # "..." suffix
        assert result.endswith('...')


# ---------------------------------------------------------------------------
# Required extra fields exist on every record.
# ---------------------------------------------------------------------------

class TestRecordShape:
    def test_record_has_all_audit_fields(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        app.test_client().get(_ns_path('/files'))
        listing = _records_for(audit_records, 'list')
        r = listing[0]
        for field in (
            'action', 'namespace', 'key', 'user',
            'result', 'status_code', 'client_ip', 'user_agent',
            'request_id',
        ):
            assert hasattr(r, field), f'audit record missing {field}'

    def test_record_propagates_to_root(
        self, s3_bucket, tmp_path,
    ) -> None:
        """propagate=True: a handler on root receives every audit record."""
        captured = _CaptureHandler()
        root = logging.getLogger()
        root.addHandler(captured)
        previous = root.level
        root.setLevel(logging.DEBUG)
        try:
            app = _make_app(s3_bucket, tmp_path)
            app.test_client().get(_ns_path('/files'))
        finally:
            root.removeHandler(captured)
            root.setLevel(previous)
        audit_records_root = [
            r for r in captured.records if r.name == 'flask_s3_viewer.audit'
        ]
        assert audit_records_root, 'root handler should have seen the audit line'


# ---------------------------------------------------------------------------
# Redirect path — Google login redirect must NOT emit an audit record.
# ---------------------------------------------------------------------------

class TestRedirectNoEmit:
    def test_anonymous_browser_get_redirect_emits_no_audit(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """When ``google_client_id``/``google_client_secret`` are configured
        and an anonymous browser GET arrives, ``_enforce_auth`` returns a
        302 to ``/auth/login`` rather than 401. The redirect itself is not
        a CRUD action and MUST NOT produce an audit record — otherwise the
        log would be polluted by every unauthenticated page load before
        the user even attempts an S3 operation.
        """
        app = _make_app(
            s3_bucket, tmp_path,
            google_client_id='cid.apps.googleusercontent.com',
            google_client_secret='secret',
        )
        resp = app.test_client().get(_ns_path('/files'), follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert '/auth/login' in resp.headers.get('Location', '')
        # No record on any action — listing/upload/download/delete/presign
        # are all CRUD verbs that the redirect short-circuits before reaching.
        assert audit_records == [], (
            f'redirect path must not emit audit records, got: '
            f'{[(r.action, r.result, r.status_code) for r in audit_records]}'
        )


# ---------------------------------------------------------------------------
# Per-file emit — multi-file upload/presign requests emit one row per file
# instead of one aggregate row per request.
# ---------------------------------------------------------------------------

class TestPerFileEmit:
    def test_upload_three_files_non_htmx_emits_three_records(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        data = {
            'files[]': [
                (io.BytesIO(b'one'), 'a.txt'),
                (io.BytesIO(b'two'), 'b.txt'),
                (io.BytesIO(b'three'), 'c.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 201
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 3
        keys = [r.key for r in upload]
        assert keys == ['a.txt', 'b.txt', 'c.txt']
        for r in upload:
            assert r.result == 'ok'
            assert r.status_code == 201

    def test_upload_three_files_htmx_emits_three_records_with_200(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        data = {
            'files[]': [
                (io.BytesIO(b'one'), 'h1.txt'),
                (io.BytesIO(b'two'), 'h2.txt'),
                (io.BytesIO(b'three'), 'h3.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
            headers={'HX-Request': 'true'},
        )
        assert resp.status_code == 200
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 3
        for r in upload:
            assert r.result == 'ok'
            assert r.status_code == 200

    def test_mkdir_only_emits_single_record(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().post(
            _ns_path('/files'),
            data={'prefix': 'newdir/'},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 201
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 1
        # mkdir uses the prefix as the audit key.
        assert upload[0].key == 'newdir/'
        assert upload[0].status_code == 201
        assert upload[0].result == 'ok'

    def test_duplicate_basename_emits_one_per_duplicate(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(s3_bucket, tmp_path)
        # Two payloads sharing the same target key → duplicate detection
        # fires before add_one, atomic fail with one row per duplicate.
        data = {
            'files[]': [
                (io.BytesIO(b'first'), 'dup.txt'),
                (io.BytesIO(b'second'), 'dup.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 409
        upload = _records_for(audit_records, 'upload')
        # duplicate_targets is a sorted set: 1 entry for the one collision key.
        assert len(upload) == 1
        assert upload[0].status_code == 409
        assert upload[0].result == 'error'
        assert upload[0].key == 'dup.txt'

    def test_disallowed_extension_emits_per_violation(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        app = _make_app(
            s3_bucket, tmp_path,
            allowed_extensions={'txt'},
        )
        data = {
            'files[]': [
                (io.BytesIO(b'bin'), 'a.exe'),
                (io.BytesIO(b'bin'), 'b.dll'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 403
        upload = _records_for(audit_records, 'upload')
        # Both violations emit, even though the response is one abort(403).
        assert len(upload) == 2
        for r in upload:
            assert r.status_code == 403
            assert r.result == 'error'
        keys = {r.key for r in upload}
        assert keys == {'a.exe', 'b.dll'}

    def test_overwrite_conflict_emits_per_conflict(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='exists1.txt', Body=b'a')
        s3_client.put_object(Bucket=bucket, Key='exists2.txt', Body=b'b')
        app = _make_app(s3_bucket, tmp_path)
        data = {
            'files[]': [
                (io.BytesIO(b'new1'), 'exists1.txt'),
                (io.BytesIO(b'new2'), 'exists2.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 409
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 2
        for r in upload:
            assert r.status_code == 409
            assert r.result == 'error'
        keys = {r.key for r in upload}
        assert keys == {'exists1.txt', 'exists2.txt'}

    def test_partial_failure_emits_success_then_error(
        self, s3_bucket, tmp_path, audit_records, monkeypatch,
    ) -> None:
        """When add_one raises mid-loop, already-uploaded files keep their
        ok rows, the failing file gets an error row, and remaining files
        are NOT emitted (atomic 'where did we stop' trace)."""
        app = _make_app(s3_bucket, tmp_path)
        # Flask's TESTING=True implies PROPAGATE_EXCEPTIONS=True, which
        # re-raises unexpected exceptions out of the test client. Disable
        # propagation explicitly so we see the 500 response while still
        # capturing the per-file audit rows the view function emitted.
        app.config['PROPAGATE_EXCEPTIONS'] = False

        viewer = app.extensions['flask_s3_viewer']['fsv-audit']
        original_add_one = viewer.add_one
        call_count = {'n': 0}

        def flaky_add_one(file_storage, *args, **kwargs):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise RuntimeError('boom')
            return original_add_one(file_storage, *args, **kwargs)

        monkeypatch.setattr(viewer, 'add_one', flaky_add_one)

        data = {
            'files[]': [
                (io.BytesIO(b'one'), 'p1.txt'),
                (io.BytesIO(b'two'), 'p2.txt'),
                (io.BytesIO(b'three'), 'p3.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 500
        upload = _records_for(audit_records, 'upload')
        # 1 ok + 1 error = 2 rows. Third file is never reached → no row.
        assert len(upload) == 2
        assert upload[0].result == 'ok'
        assert upload[0].status_code == 201
        assert upload[0].key == 'p1.txt'
        assert upload[1].result == 'error'
        assert upload[1].status_code == 500
        assert upload[1].key == 'p2.txt'
        assert 'RuntimeError' in getattr(upload[1], 'error', '')

    def test_presign_mixed_five_files_emits_five_records(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        s3_client, bucket = s3_bucket
        # Pre-create one object so it triggers a 409 conflict in presign.
        s3_client.put_object(Bucket=bucket, Key='clash.txt', Body=b'x')
        app = _make_app(
            s3_bucket, tmp_path,
            allowed_extensions={'txt'},
        )
        # 3 ok + 1 conflict + 1 forbidden (extension)
        resp = app.test_client().post(
            _ns_path('/files/presign'),
            data={
                'prefix': '',
                'file_list': 'a.txt,b.txt,c.txt,clash.txt,bad.exe',
            },
        )
        assert resp.status_code == 200
        presigns = _records_for(audit_records, 'presign')
        assert len(presigns) == 5
        by_key = {r.key: r for r in presigns}
        assert by_key['a.txt'].status_code == 200
        assert by_key['a.txt'].result == 'ok'
        assert by_key['b.txt'].status_code == 200
        assert by_key['c.txt'].status_code == 200
        assert by_key['clash.txt'].status_code == 409
        assert by_key['clash.txt'].result == 'error'
        assert by_key['bad.exe'].status_code == 403
        assert by_key['bad.exe'].result == 'error'

    def test_denied_short_circuits_per_file_loop(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """When auth denies an upload, exactly 1 denied row is emitted and
        the per-file loop never runs (no duplicate or zero rows)."""
        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: 'noaccess@example.com',
            permission_callback=lambda *a, **kw: False,
        )
        data = {
            'files[]': [
                (io.BytesIO(b'x'), 'a.txt'),
                (io.BytesIO(b'y'), 'b.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 403
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 1
        assert upload[0].result == 'denied'
        assert upload[0].status_code == 403
        assert upload[0].user == 'noaccess@example.com'

    def test_anonymous_user_field_on_multi_file_upload(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """Per-file emits inherit the request-scoped user; with no auth
        callback every row records 'anonymous'."""
        app = _make_app(s3_bucket, tmp_path)
        data = {
            'files[]': [
                (io.BytesIO(b'1'), 'anon1.txt'),
                (io.BytesIO(b'2'), 'anon2.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 201
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 2
        for r in upload:
            assert r.user == 'anonymous'

    def test_presign_empty_file_list_falls_back_to_single_row(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """No files iterated → finally fallback emits a single prefix row."""
        app = _make_app(s3_bucket, tmp_path)
        resp = app.test_client().post(
            _ns_path('/files/presign'),
            data={'prefix': 'empty/', 'file_list': ''},
        )
        assert resp.status_code == 200
        presigns = _records_for(audit_records, 'presign')
        assert len(presigns) == 1
        assert presigns[0].key == 'empty/'
        assert presigns[0].status_code == 200
        assert presigns[0].result == 'ok'


# ---------------------------------------------------------------------------
# request_id — shared per Flask request, fresh per emit outside request scope.
# ---------------------------------------------------------------------------

class TestRequestId:
    def test_same_request_shares_one_request_id(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """Multi-file upload (N rows in one request) → all rows share one id."""
        app = _make_app(s3_bucket, tmp_path)
        data = {
            'files[]': [
                (io.BytesIO(b'1'), 'r1.txt'),
                (io.BytesIO(b'2'), 'r2.txt'),
                (io.BytesIO(b'3'), 'r3.txt'),
            ],
        }
        resp = app.test_client().post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert resp.status_code == 201
        upload = _records_for(audit_records, 'upload')
        assert len(upload) == 3
        ids = {r.request_id for r in upload}
        assert len(ids) == 1, f'expected one shared request_id, got {ids}'

    def test_different_requests_get_different_request_ids(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """Two separate test_client requests → two distinct request_ids."""
        app = _make_app(s3_bucket, tmp_path)
        client = app.test_client()
        client.get(_ns_path('/files'))
        client.get(_ns_path('/files'))
        listing = _records_for(audit_records, 'list')
        assert len(listing) == 2
        assert listing[0].request_id != listing[1].request_id

    def test_emit_without_request_context_generates_fresh_each_call(
        self, audit_records,
    ) -> None:
        """Calling emit() outside any request context → fresh id every call."""
        from flask_s3_viewer.audit import emit

        emit(
            action='list', namespace='ns', key='', user='a@b.com',
            result='ok', status_code=200,
        )
        emit(
            action='list', namespace='ns', key='', user='a@b.com',
            result='ok', status_code=200,
        )
        assert len(audit_records) >= 2
        r1, r2 = audit_records[-2], audit_records[-1]
        assert r1.request_id != r2.request_id

    def test_request_id_is_eight_hex_chars(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        import re

        app = _make_app(s3_bucket, tmp_path)
        app.test_client().get(_ns_path('/files'))
        listing = _records_for(audit_records, 'list')
        assert listing, 'expected one listing record'
        rid = listing[0].request_id
        assert re.fullmatch(r'[0-9a-f]{8}', rid), (
            f'request_id must be 8 lowercase hex chars, got {rid!r}'
        )

    def test_request_id_appears_in_message_body(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """The human-readable message carries `req=<id>` so plaintext grep groups a request."""
        app = _make_app(s3_bucket, tmp_path)
        app.test_client().get(_ns_path('/files'))
        listing = _records_for(audit_records, 'list')
        r = listing[0]
        assert f'req={r.request_id}' in r.getMessage()

    def test_denied_row_carries_request_id(
        self, s3_bucket, tmp_path, audit_records,
    ) -> None:
        """A 401 denied row must still surface request_id (record + message)."""
        import re

        app = _make_app(
            s3_bucket, tmp_path,
            auth_callback=lambda _req: None,
            permission_callback=lambda *a, **kw: True,
        )
        resp = app.test_client().get(_ns_path('/files'))
        assert resp.status_code == 401
        listing = _records_for(audit_records, 'list')
        assert len(listing) == 1
        r = listing[0]
        assert re.fullmatch(r'[0-9a-f]{8}', r.request_id)
        assert f'req={r.request_id}' in r.getMessage()
