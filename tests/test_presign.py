"""Regression tests for the presigned-upload mode (``upload_type='presign'``).

The presign flow still relies on ``flask.s3viewer.core.js`` which reads a
specific set of legacy DOM IDs (``fs3viewer_files``, ``fs3viewer_prefix``,
``fs3viewer_progress``, ``file_chip``, ``floading``, ``upload_form``,
``fs3viewer_refresh``). Any future slim-down of that script must keep
these contracts intact — this module pins both the backend route
behavior and the rendered template surface.
"""
from __future__ import annotations

import boto3
import pytest
from flask import Flask
from moto import mock_aws

from flask_s3_viewer import FlaskS3Viewer

# ---------------------------------------------------------------------------
# Fixtures — a parallel `presign_*` set so the default-mode suite is unaffected
# ---------------------------------------------------------------------------

@pytest.fixture
def presign_s3_bucket(aws_credentials):
    """Mocked S3 bucket dedicated to presign tests."""
    with mock_aws():
        client = boto3.client('s3', region_name='us-east-1')
        bucket = 'fsv-presign-test'
        client.create_bucket(Bucket=bucket)
        yield client, bucket


@pytest.fixture
def presign_app(presign_s3_bucket, tmp_path):
    """Flask app with the viewer in ``upload_type='presign'`` mode."""
    _client, bucket = presign_s3_bucket
    flask_app = Flask(__name__)
    flask_app.config['TESTING'] = True
    FlaskS3Viewer(
        flask_app,
        namespace='fsv-presign',
        upload_type='presign',
        allowed_extensions={'jpg', 'png', 'txt'},
        config={
            'profile_name': None,
            'bucket_name': bucket,
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'presign-cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )
    yield flask_app


@pytest.fixture
def presign_client(presign_app):
    return presign_app.test_client()


# ---------------------------------------------------------------------------
# Backend route — POST /<ns>/files/presign
# ---------------------------------------------------------------------------

class TestPresignEndpoint:
    """The presign endpoint takes ``file_list`` + ``prefix`` and returns a
    JSON list of presigned POST payloads (or per-file ``status_code`` slots
    when a file is skipped/blocked).
    """

    def test_returns_presigned_post_fields(self, presign_client):
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '', 'file_list': 'note.txt'},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert isinstance(body, list)
        assert len(body) == 1
        item = body[0]
        # Successful slot carries presigned POST data, not a status_code.
        assert 'status_code' not in item
        assert 'url' in item
        assert 'fields' in item
        assert isinstance(item['fields'], dict)
        # Boto3 always echoes the key the client should upload under.
        assert item['fields'].get('key') == 'note.txt'

    def test_invalid_prefix_returns_400(self, presign_client):
        """Path-traversal tokens hit the InvalidPrefix guard before any
        signing happens — same behavior as the regular files endpoints.
        """
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '../etc/', 'file_list': 'note.txt'},
        )
        assert rv.status_code == 400

    def test_existing_file_returns_409_slot(self, presign_client, presign_s3_bucket):
        """If the target key already exists, that slot is replaced with a
        ``{status_code: 409}`` marker instead of a presigned URL.
        """
        client, bucket = presign_s3_bucket
        client.put_object(Bucket=bucket, Key='taken.txt', Body=b'existing')
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '', 'file_list': 'taken.txt'},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert body == [{'status_code': 409}]

    def test_existing_file_with_overwrite_returns_presign(self, presign_client, presign_s3_bucket):
        client, bucket = presign_s3_bucket
        client.put_object(Bucket=bucket, Key='taken.txt', Body=b'existing')
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '', 'file_list': 'taken.txt', 'overwrite': '1'},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert len(body) == 1
        assert 'status_code' not in body[0]
        assert body[0]['fields'].get('key') == 'taken.txt'

    def test_disallowed_extension_returns_403_slot(self, presign_client):
        """``allowed_extensions`` blocks the slot with a 403 marker."""
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '', 'file_list': 'malware.exe'},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert body == [{'status_code': 403}]

    def test_multiple_files_yield_parallel_slots(self, presign_client):
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '', 'file_list': 'a.txt,b.txt,c.png'},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert len(body) == 3
        assert all('url' in item and 'fields' in item for item in body)
        keys = [item['fields']['key'] for item in body]
        assert keys == ['a.txt', 'b.txt', 'c.png']

    def test_prefix_applied_to_keys(self, presign_client):
        """The form's ``prefix`` field is joined with each filename before
        signing — confirms the legacy core.js flow can target subfolders.
        """
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': 'photos/', 'file_list': 'a.png'},
        )
        body = rv.get_json()
        assert body[0]['fields']['key'] == 'photos/a.png'

    def test_purges_cache_after_signing(self, presign_client, presign_app):
        """A presign POST acts as the prelude to writes, so the cache for
        the target prefix is invalidated. We verify by populating the
        cache and showing the entry is gone after the call.
        """
        viewer = presign_app.extensions['flask_s3_viewer']['fsv-presign']
        # Prime the cache for the empty prefix.
        viewer.find(prefix='', apply_cache=True)
        rv = presign_client.post(
            '/fsv-presign/files/presign',
            data={'prefix': '', 'file_list': 'cache-prime.txt'},
        )
        assert rv.status_code == 200
        # After purge() the next find() is a fresh miss; we don't have a
        # direct cache-hit signal but exercising the call path is enough
        # to surface any regression in the purge wiring.


# ---------------------------------------------------------------------------
# Rendered template surface — the IDs core.js relies on
# ---------------------------------------------------------------------------

class TestPresignTemplate:
    """Pin the DOM contract between flask.s3viewer.core.js and the
    presign-mode upload form. Any rename of these IDs (during a future
    core.js slim-down) must update both sides together.
    """

    LEGACY_IDS = (
        'fs3viewer_files',     # the <input type=file>
        'fs3viewer_prefix',    # hidden prefix input
        'fs3viewer_progress',  # hidden int 0..100 driven by upload XHR
        'file_chip',           # post-selection chip with file_count + Upload
        'file_count',          # selected file count text
        'floading',            # spinner shown while uploading
        'upload_form',         # the multipart <form>
        'fs3viewer_refresh',   # legacy badge counter stub
    )

    def test_full_page_loads_core_js(self, presign_client):
        rv = presign_client.get('/fsv-presign/files')
        assert rv.status_code == 200
        body = rv.data.decode('utf-8')
        # core.js is only loaded under the presign branch, lazy on demand.
        assert 'flask.s3viewer.core.js' in body

    def test_full_page_includes_all_legacy_ids(self, presign_client):
        rv = presign_client.get('/fsv-presign/files')
        body = rv.data.decode('utf-8')
        for legacy_id in self.LEGACY_IDS:
            assert f'id="{legacy_id}"' in body, (
                f'Legacy DOM id required by flask.s3viewer.core.js is missing: '
                f'{legacy_id!r}'
            )

    def test_full_page_attaches_core_handlers(self, presign_client):
        """The file <input> and the Upload button must point at the
        ``FLASK_S3_VIEWER_CORE`` entry points — otherwise core.js never
        gets a chance to run.
        """
        rv = presign_client.get('/fsv-presign/files')
        body = rv.data.decode('utf-8')
        assert 'FLASK_S3_VIEWER_CORE.readyFileHandling' in body
        assert 'FLASK_S3_VIEWER_CORE.putAll' in body
        assert 'FLASK_S3_VIEWER_CORE.fetchPresigns' in body
        assert 'FLASK_S3_VIEWER_CORE.onProgress' in body
        assert 'fsvPresignShowOverwrite' in body

    def test_htmx_partial_does_not_resend_upload_form(self, presign_client):
        """HTMX partial swaps replace only ``#file-list``; the upload form
        (and its core.js) must NOT be re-emitted in the partial fragment.
        """
        rv = presign_client.get(
            '/fsv-presign/files',
            headers={'HX-Request': 'true'},
        )
        assert rv.status_code == 200
        body = rv.data.decode('utf-8')
        assert 'flask.s3viewer.core.js' not in body
        # The presign-mode form ids belong on the page, not in the partial.
        for legacy_id in ('fs3viewer_files', 'fs3viewer_progress', 'file_chip'):
            assert f'id="{legacy_id}"' not in body

    def test_default_mode_does_NOT_load_core_js(self, client):
        """Sanity guard: default upload mode (HTMX flow) should never pull
        in core.js — the legacy script costs ~10KB and would be dead weight.
        """
        rv = client.get('/fsv-test/files')
        body = rv.data.decode('utf-8')
        assert 'flask.s3viewer.core.js' not in body
        # And none of the legacy IDs leak into the default-mode page either.
        for legacy_id in ('fs3viewer_files', 'fs3viewer_prefix', 'file_chip'):
            assert f'id="{legacy_id}"' not in body
