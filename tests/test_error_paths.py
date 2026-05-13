"""boto3 error-path coverage for the AWS S3 wrapper.

These tests monkey-patch the moto-backed ``_s3`` client to raise
``ClientError`` (or a transient ``Exception``) from individual operations,
then verify each wrapper method's recovery / propagation contract:

  - ``find_one``    → returns ``None`` on ClientError (no propagation)
  - ``is_exists``   → returns ``False`` on ClientError
  - ``mkdir``       → returns ``False`` on ClientError (no propagation)
  - ``add_one``     → re-raises ClientError to the caller
  - ``remove_one``  → re-raises ClientError
  - ``post_presign``→ re-raises ClientError
  - ``find_all``    → generator surfaces wrapped iteration intact

Plus one session-construction failure scenario for ``AWSSession``.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from flask_s3_viewer.aws.session import AWSSession


def _make_client_error(code: str = 'NoSuchKey', op: str = 'GetObject') -> ClientError:
    """Build a realistic-looking ClientError for a given S3 operation."""
    return ClientError(
        {'Error': {'Code': code, 'Message': 'simulated by test'}},
        op,
    )


@pytest.fixture
def viewer(app):
    """The FlaskS3Viewer extension wired by ``app`` (default upload mode)."""
    return app.extensions['flask_s3_viewer']['fsv-test']


# ---------------------------------------------------------------------------
# Methods that swallow ClientError and degrade gracefully
# ---------------------------------------------------------------------------

class TestGracefulErrorRecovery:
    def test_find_one_returns_none_on_client_error(self, viewer):
        with patch.object(viewer._s3, 'get_object', side_effect=_make_client_error()):
            assert viewer.find_one('does-not-matter.txt') is None

    def test_is_exists_returns_false_on_client_error(self, viewer):
        with patch.object(viewer._s3, 'head_object', side_effect=_make_client_error('404', 'HeadObject')):
            assert viewer.is_exists('absent.txt') is False

    def test_mkdir_returns_false_on_client_error(self, viewer):
        with patch.object(viewer._s3, 'put_object', side_effect=_make_client_error('AccessDenied', 'PutObject')):
            assert viewer.mkdir('locked/') is False


# ---------------------------------------------------------------------------
# Methods that re-raise — caller decides how to handle
# ---------------------------------------------------------------------------

class TestPropagatedErrors:
    def test_add_one_reraises(self, viewer):
        # Fake werkzeug FileStorage-ish object with a .headers.get.
        class FakeFile:
            headers = {'Content-Type': 'application/octet-stream'}
        fake = FakeFile()
        fake.headers = {'Content-Type': 'application/octet-stream'}
        # The wrapper reads f.headers.get(...) so wrap a dict.
        fake.headers = type('H', (), {'get': lambda self, k: 'application/octet-stream'})()
        with patch.object(viewer._s3, 'upload_fileobj', side_effect=_make_client_error('AccessDenied', 'PutObject')):
            with pytest.raises(ClientError):
                viewer.add_one(fake, 'denied.txt')

    def test_remove_one_reraises(self, viewer):
        with patch.object(viewer._s3, 'delete_object', side_effect=_make_client_error('AccessDenied', 'DeleteObject')):
            with pytest.raises(ClientError):
                viewer.remove_one('denied.txt')

    def test_post_presign_reraises(self, viewer):
        with patch.object(viewer._s3, 'generate_presigned_post', side_effect=_make_client_error('Throttling', 'GeneratePresignedPost')):
            with pytest.raises(ClientError):
                viewer.post_presign('throttled.txt')


# ---------------------------------------------------------------------------
# AWSSession construction
# ---------------------------------------------------------------------------

class TestSessionInit:
    def test_unexpected_error_marks_session_not_runnable(self, monkeypatch):
        """If boto3.Session() raises a non-ClientError, ``runnable`` stays False
        so downstream construction fails fast with ValueError.
        """
        import flask_s3_viewer.aws.session as sess_mod

        class BoomError(RuntimeError):
            pass

        def boom_session(*args, **kwargs):
            raise BoomError('simulated boto3.Session failure')

        monkeypatch.setattr(sess_mod.boto3, 'Session', boom_session)
        os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
        s = AWSSession(access_key='x', secret_key='y')
        assert s.runnable is False
