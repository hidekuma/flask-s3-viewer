"""Coverage-gap fillers: constructor edge cases, extension lifecycle,
boto3 wrapper utilities, and exception raisers that the focused suites
didn't touch.

Each ``Test*`` class is grouped by source module so future contributors can
trace coverage deltas back to the file under test.
"""
from __future__ import annotations

import warnings
from io import BytesIO

import boto3
import pytest
from flask import Flask
from moto import mock_aws

from flask_s3_viewer import FlaskS3Viewer, _resolve_logo
from flask_s3_viewer.errors import (
    InvalidPrefix,
    NotConfiguredCacheDir,
    NotSupportUploadType,
)

# ---------------------------------------------------------------------------
# flask_s3_viewer/__init__.py
# ---------------------------------------------------------------------------

class TestConstructorValidation:
    """Constructor-time guards that error out *before* boto3 touches the wire."""

    def test_unknown_upload_type_raises(self, aws_credentials):
        with pytest.raises(NotSupportUploadType):
            FlaskS3Viewer(
                Flask(__name__),
                namespace='bad-type',
                upload_type='ftp',
                config={'bucket_name': 'x', 'region_name': 'us-east-1',
                        'access_key': 't', 'secret_key': 't'},
            )

    def test_use_cache_without_cache_dir_raises(self, aws_credentials):
        with pytest.raises(NotConfiguredCacheDir):
            FlaskS3Viewer(
                Flask(__name__),
                namespace='cache-missing',
                config={
                    'bucket_name': 'x', 'region_name': 'us-east-1',
                    'access_key': 't', 'secret_key': 't',
                    'use_cache': True,
                    # cache_dir intentionally omitted
                },
            )

    def test_template_namespace_emits_deprecation_warning(self, aws_credentials, tmp_path):
        with mock_aws():
            boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-extras')
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter('always')
                FlaskS3Viewer(
                    Flask(__name__),
                    namespace='legacy-tns',
                    template_namespace='mdl',
                    config={
                        'profile_name': None,
                        'bucket_name': 'fsv-extras', 'region_name': 'us-east-1',
                        'access_key': 't', 'secret_key': 't',
                        'cache_dir': str(tmp_path), 'use_cache': True, 'ttl': 60,
                    },
                )
            assert any(
                issubclass(w.category, DeprecationWarning)
                and 'template_namespace' in str(w.message)
                for w in captured
            )

    def test_object_hostname_trailing_slash_stripped(self, aws_credentials, tmp_path):
        with mock_aws():
            boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-extras')
            v = FlaskS3Viewer(
                Flask(__name__),
                namespace='obj-host',
                object_hostname='https://cdn.example.com/',
                config={
                    'profile_name': None,
                    'bucket_name': 'fsv-extras', 'region_name': 'us-east-1',
                    'access_key': 't', 'secret_key': 't',
                    'cache_dir': str(tmp_path), 'use_cache': True, 'ttl': 60,
                },
            )
            assert v.object_hostname == 'https://cdn.example.com'


class TestDeferredInitApp:
    """``app=None`` constructor + later ``init_app(app)`` is the Flask
    extension factory-pattern flow.
    """

    def test_init_app_registers_and_binds_namespace(self, aws_credentials, tmp_path):
        with mock_aws():
            boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-extras')
            v = FlaskS3Viewer(
                namespace='deferred',
                config={
                    'profile_name': None,
                    'bucket_name': 'fsv-extras', 'region_name': 'us-east-1',
                    'access_key': 't', 'secret_key': 't',
                    'cache_dir': str(tmp_path), 'use_cache': True, 'ttl': 60,
                },
            )
            assert v.app is None
            app = Flask(__name__)
            v.init_app(app)
            assert app.extensions['flask_s3_viewer']['deferred'] is v
            assert v.app is app

    def test_init_app_without_namespace_raises(self, aws_credentials, tmp_path):
        with mock_aws():
            boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-extras')
            v = FlaskS3Viewer(
                # namespace omitted on purpose
                config={
                    'profile_name': None,
                    'bucket_name': 'fsv-extras', 'region_name': 'us-east-1',
                    'access_key': 't', 'secret_key': 't',
                    'cache_dir': str(tmp_path), 'use_cache': True, 'ttl': 60,
                },
            )
            with pytest.raises(ValueError, match='namespace'):
                v.init_app(Flask(__name__))


class TestAddNewOne:
    """``add_new_one`` lets a single deployment manage multiple S3 namespaces
    under the same Flask app.
    """

    def test_add_new_one_registers_second_namespace(self, app, tmp_path):
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        # Re-using the same mocked S3 client; create a second bucket so the
        # add_new_one call has a real target.
        boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='second')
        viewer.add_new_one(
            namespace='second',
            config={
                'profile_name': None,
                'bucket_name': 'second', 'region_name': 'us-east-1',
                'access_key': 't', 'secret_key': 't',
                'cache_dir': str(tmp_path / 'second'), 'use_cache': True, 'ttl': 60,
            },
        )
        assert 'second' in app.extensions['flask_s3_viewer']
        # The two namespaces hold independent FlaskS3Viewer instances.
        assert app.extensions['flask_s3_viewer']['second'] is not viewer

    def test_add_new_one_without_bound_app_raises(self, aws_credentials, tmp_path):
        with mock_aws():
            boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-extras')
            v = FlaskS3Viewer(
                namespace='lonely',
                config={
                    'profile_name': None,
                    'bucket_name': 'fsv-extras', 'region_name': 'us-east-1',
                    'access_key': 't', 'secret_key': 't',
                    'cache_dir': str(tmp_path), 'use_cache': True, 'ttl': 60,
                },
            )
            with pytest.raises(RuntimeError, match='Flask app'):
                v.add_new_one(namespace='nope', config={})


class TestStaticAccessors:
    """``get_boto_client`` / ``get_boto_session`` staticmethods."""

    def test_get_boto_client(self, app):
        client = FlaskS3Viewer.get_boto_client(app, 'fsv-test')
        # boto3 S3 client carries .meta.service_model.service_name
        assert client.meta.service_model.service_name == 's3'

    def test_get_boto_session(self, app):
        sess = FlaskS3Viewer.get_boto_session(app, 'fsv-test')
        assert isinstance(sess, boto3.session.Session)


class TestResolveLogo:
    """Branch coverage for ``_resolve_logo``."""

    def test_logo_path_inlines_as_data_uri(self, tmp_path):
        path = tmp_path / 'logo.png'
        path.write_bytes(b'fake-png-bytes')
        url = _resolve_logo(None, str(path))
        assert url is not None
        assert url.startswith('data:image/png;base64,')

    def test_logo_path_unknown_mime_falls_back_to_octet_stream(self, tmp_path):
        path = tmp_path / 'logo.weirdext'
        path.write_bytes(b'\x00')
        url = _resolve_logo(None, str(path))
        assert url is not None
        assert url.startswith('data:application/octet-stream;base64,')

    def test_logo_url_passthrough(self):
        assert _resolve_logo('https://cdn/x.svg', None) == 'https://cdn/x.svg'

    def test_no_logo(self):
        assert _resolve_logo(None, None) is None

    def test_logo_path_takes_precedence_over_logo_url(self, tmp_path):
        path = tmp_path / 'pref.png'
        path.write_bytes(b'pref')
        url = _resolve_logo('https://cdn/ignored.svg', str(path))
        assert url is not None and url.startswith('data:image/png;base64,')


# ---------------------------------------------------------------------------
# flask_s3_viewer/errors.py
# ---------------------------------------------------------------------------

class TestErrorMessages:
    def test_invalid_prefix_repr_includes_prefix(self):
        e = InvalidPrefix('../etc')
        msg = str(e)
        assert "'../etc'" in msg
        assert 'invalid prefix' in msg.lower()

    def test_not_configured_cache_dir_msg(self):
        msg = str(NotConfiguredCacheDir())
        assert 'cache_dir' in msg

    def test_not_support_upload_type_msg(self):
        msg = str(NotSupportUploadType())
        assert 'upload' in msg.lower()


# ---------------------------------------------------------------------------
# flask_s3_viewer/aws/s3.py — wrapper utility methods
# ---------------------------------------------------------------------------

class TestS3Wrapper:
    def test_find_all_yields_all_keys_under_prefix(self, app, s3_bucket):
        client, bucket = s3_bucket
        # Lay down a small tree under "tree/"
        for key in ('tree/a.txt', 'tree/b.txt', 'tree/sub/c.txt'):
            client.put_object(Bucket=bucket, Key=key, Body=b'.')
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        keys = list(viewer.find_all('tree/'))
        # find_all yields raw S3 keys; ordering is paginator-dependent but
        # set membership is stable.
        assert 'tree/a.txt' in keys
        assert 'tree/b.txt' in keys
        assert 'tree/sub/c.txt' in keys

    def test_remove_polymorphism_string_calls_remove_one(self, app, s3_bucket):
        client, bucket = s3_bucket
        client.put_object(Bucket=bucket, Key='single.txt', Body=b'.')
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        viewer.remove('single.txt')
        # Object should no longer be listable.
        rest = list(viewer.find_all(''))
        assert 'single.txt' not in rest

    def test_remove_polymorphism_list_calls_remove_all(self, app, s3_bucket):
        client, bucket = s3_bucket
        for k in ('m1.txt', 'm2.txt', 'm3.txt'):
            client.put_object(Bucket=bucket, Key=k, Body=b'.')
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        viewer.remove(['m1.txt', 'm2.txt'])
        rest = list(viewer.find_all(''))
        assert 'm1.txt' not in rest
        assert 'm2.txt' not in rest
        assert 'm3.txt' in rest

    def test_remove_root_raises(self, app):
        """``remove('/')`` is a footgun guard — would otherwise wipe the
        whole bucket.
        """
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        with pytest.raises(ValueError):
            viewer.remove('/')

    def test_download_one_writes_file(self, app, s3_bucket, tmp_path):
        client, bucket = s3_bucket
        body = b'download me'
        client.put_object(Bucket=bucket, Key='dl.txt', Body=body)
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        out = tmp_path / 'out.bin'
        viewer.download_one(str(out), 'dl.txt')
        assert out.read_bytes() == body


# ---------------------------------------------------------------------------
# flask_s3_viewer/blueprints/view.py — request handler branches
# ---------------------------------------------------------------------------

class TestViewBranches:
    def test_unknown_namespace_returns_404(self, app):
        c = app.test_client()
        rv = c.get('/no-such-ns/files')
        assert rv.status_code == 404

    def test_post_mkdir_creates_folder(self, client, s3_bucket):
        rv = client.post('/fsv-test/files', data={'prefix': 'newdir/'})
        # 201 (legacy) for non-HTMX callers, 200 partial for HTMX.
        assert rv.status_code in (200, 201)
        bucket = s3_bucket[1]
        listed = boto3.client('s3', region_name='us-east-1').list_objects_v2(
            Bucket=bucket, Prefix='newdir/'
        )
        assert listed.get('KeyCount', 0) >= 1

    def test_post_mkdir_conflict_409(self, client, s3_bucket):
        client_s3, bucket = s3_bucket
        client_s3.put_object(Bucket=bucket, Key='taken/', Body=b'')
        rv = client.post('/fsv-test/files', data={'prefix': 'taken/'})
        assert rv.status_code == 409

    def test_post_upload_succeeds(self, client):
        rv = client.post(
            '/fsv-test/files',
            data={'prefix': '', 'files[]': (BytesIO(b'hello'), 'h.txt')},
            content_type='multipart/form-data',
        )
        assert rv.status_code in (200, 201)

    def test_post_upload_conflict_returns_json_409(self, client, s3_bucket):
        client_s3, bucket = s3_bucket
        client_s3.put_object(Bucket=bucket, Key='dup.txt', Body=b'old')
        rv = client.post(
            '/fsv-test/files',
            data={'prefix': '', 'files[]': (BytesIO(b'new'), 'dup.txt')},
            content_type='multipart/form-data',
        )
        assert rv.status_code == 409
        body = rv.get_json()
        assert 'conflicts' in body
        assert 'dup.txt' in body['conflicts']

    def test_post_upload_with_overwrite_flag_succeeds(self, client, s3_bucket):
        client_s3, bucket = s3_bucket
        client_s3.put_object(Bucket=bucket, Key='dup2.txt', Body=b'old')
        rv = client.post(
            '/fsv-test/files',
            data={
                'prefix': '',
                'overwrite': '1',
                'files[]': (BytesIO(b'new'), 'dup2.txt'),
            },
            content_type='multipart/form-data',
        )
        assert rv.status_code in (200, 201)
        # Object body should be the new payload.
        got = client_s3.get_object(Bucket=bucket, Key='dup2.txt')['Body'].read()
        assert got == b'new'

    def test_delete_missing_key_still_returns_204(self, client):
        """boto3 delete_object is idempotent — deleting an absent key is OK."""
        rv = client.delete('/fsv-test/files/' + 'ghost.txt')
        assert rv.status_code == 204

    def test_delete_with_traversal_returns_400(self, client):
        rv = client.delete('/fsv-test/files/' + '..%2Fetc%2F')
        assert rv.status_code == 400
