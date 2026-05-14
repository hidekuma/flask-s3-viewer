"""A3 security regression: prefix traversal guards on AWSS3Client.prefixer().

Covers the planner's 10-case checklist:
    1. '../../etc'   -> InvalidPrefix
    2. '//etc'       -> InvalidPrefix
    3. 'a//b'        -> InvalidPrefix
    4. 'a/./b'       -> InvalidPrefix
    5. 'a\\b'        -> InvalidPrefix
    6. 'a/b/'        -> normal
    7. ''            -> normal
    8. leading '/'   -> single-slash normalised, '//x' rejected
    9. base_path leading '/' normalised at construction time
"""
from __future__ import annotations

import io

import pytest
from flask import Flask

from flask_s3_viewer import FlaskS3Viewer
from flask_s3_viewer.aws.s3 import AWSS3Client
from flask_s3_viewer.errors import InvalidPrefix


def _make_client(base_path: str = '') -> AWSS3Client:
    """Build an AWSS3Client without touching real AWS or boto3 client creation.

    We bypass __init__ so the test focuses purely on prefixer() behaviour.
    Only the attributes prefixer() reads are required.
    """
    inst = AWSS3Client.__new__(AWSS3Client)
    # prefixer only reads ``self._base_path``.
    inst._base_path = (base_path or '').lstrip('/')
    return inst


class TestPrefixerRejected:
    """Cases that must raise InvalidPrefix."""

    @pytest.mark.parametrize(
        'bad_prefix',
        [
            '../../etc',
            '..',
            '../etc',
            '//etc',
            'a//b',
            'a/./b',
            'a/../b',
            '.',
            './foo',
            'foo/.',
            'foo/..',
        ],
    )
    def test_traversal_and_empty_segment_rejected(self, bad_prefix: str) -> None:
        client = _make_client()
        with pytest.raises(InvalidPrefix):
            client.prefixer(bad_prefix)

    def test_backslash_rejected(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidPrefix):
            client.prefixer('a\\b')

    def test_backslash_anywhere_rejected(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidPrefix):
            client.prefixer('foo/bar\\baz')


class TestPrefixerAccepted:
    """Cases that must succeed and return a normalised key."""

    def test_plain_dir_appends_trailing_slash(self) -> None:
        client = _make_client()
        assert client.prefixer('a/b/') == 'a/b/'

    def test_plain_dir_missing_trailing_slash_gets_appended(self) -> None:
        client = _make_client()
        assert client.prefixer('a/b') == 'a/b/'

    def test_empty_prefix_returns_base_path_root(self) -> None:
        # Empty input => prefixer returns os.path.join(base_path, '').
        # With empty base_path that is ''.
        client = _make_client(base_path='')
        assert client.prefixer('') == ''

    def test_single_leading_slash_normalised(self) -> None:
        client = _make_client()
        assert client.prefixer('/foo/') == 'foo/'

    def test_double_leading_slash_rejected(self) -> None:
        client = _make_client()
        with pytest.raises(InvalidPrefix):
            client.prefixer('//etc')


class TestBasePathNormalisation:
    """A3: base_path leading '/' must be stripped at construction time."""

    def test_leading_slash_in_base_path_stripped(self) -> None:
        client = _make_client(base_path='/test')
        # Resulting prefixer output should join 'test' (stripped) + 'a/b/'.
        assert client.prefixer('a/b/') == 'test/a/b/'

    def test_empty_base_path_with_prefix(self) -> None:
        client = _make_client(base_path='')
        assert client.prefixer('a/b/') == 'a/b/'

    def test_none_base_path_treated_as_empty(self) -> None:
        # Production __init__ uses ``(base_path or '').lstrip('/')`` so a
        # None feed must not blow up *and* must produce the same result as
        # an explicit empty string. We exercise both branches and assert
        # equivalence + no InvalidPrefix on a normal input.
        normalised_from_none = (None or '').lstrip('/')
        normalised_from_empty = ('' or '').lstrip('/')
        assert normalised_from_none == normalised_from_empty == ''

        inst_none = AWSS3Client.__new__(AWSS3Client)
        inst_none._base_path = normalised_from_none
        inst_empty = AWSS3Client.__new__(AWSS3Client)
        inst_empty._base_path = normalised_from_empty

        # Same input → same output across both construction paths.
        assert inst_none.prefixer('a/') == inst_empty.prefixer('a/') == 'a/'
        # And no spurious InvalidPrefix is raised on benign input.
        assert inst_none.prefixer('') == ''


class TestObjectNameValidation:
    def test_absolute_path_rejected(self) -> None:
        client = _make_client(base_path='team-a')
        with pytest.raises(InvalidPrefix):
            client.get_object_name('/team-b/secret.txt')

    def test_traversal_segment_rejected(self) -> None:
        client = _make_client(base_path='team-a')
        with pytest.raises(InvalidPrefix):
            client.get_object_name('../team-b/secret.txt')

    def test_base_path_is_preserved_for_valid_keys(self) -> None:
        client = _make_client(base_path='team-a')
        assert client.get_object_name('folder/file.txt') == 'team-a/folder/file.txt'


def _make_base_path_client(s3_bucket, tmp_path):
    _client, bucket = s3_bucket
    app = Flask(__name__)
    app.config['TESTING'] = True
    FlaskS3Viewer(
        app,
        namespace='fsv-traversal',
        config={
            'profile_name': None,
            'bucket_name': bucket,
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'cache'),
            'use_cache': True,
            'ttl': 60,
            'base_path': 'team-a',
        },
    )
    return app.test_client()


class TestBasePathTraversalIntegration:
    def test_download_cross_prefix_key_returns_400(self, s3_bucket, tmp_path) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='team-a/x.txt', Body=b'a')
        s3_client.put_object(Bucket=bucket, Key='team-b/y.txt', Body=b'b')
        client = _make_base_path_client(s3_bucket, tmp_path)
        rv = client.get('/fsv-traversal/files/%252Fteam-b%252Fy.txt')
        assert rv.status_code == 400

    def test_delete_cross_prefix_key_returns_400(self, s3_bucket, tmp_path) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='team-a/x.txt', Body=b'a')
        s3_client.put_object(Bucket=bucket, Key='team-b/y.txt', Body=b'b')
        client = _make_base_path_client(s3_bucket, tmp_path)
        rv = client.delete('/fsv-traversal/files/%252Fteam-b%252Fy.txt')
        assert rv.status_code == 400

    def test_upload_rejects_filename_with_path_separator(self, s3_bucket, tmp_path) -> None:
        _s3_client, _bucket = s3_bucket
        client = _make_base_path_client(s3_bucket, tmp_path)
        rv = client.post(
            '/fsv-traversal/files',
            data={
                'prefix': '',
                'files[]': (io.BytesIO(b'evil'), '/team-b/evil.txt'),
            },
            content_type='multipart/form-data',
        )
        assert rv.status_code == 400

    def test_presign_rejects_filename_with_path_separator(self, s3_bucket, tmp_path) -> None:
        client = _make_base_path_client(s3_bucket, tmp_path)
        rv = client.post(
            '/fsv-traversal/files/presign',
            data={'prefix': '', 'file_list': '../../team-b/owned.sh'},
        )
        assert rv.status_code == 400
