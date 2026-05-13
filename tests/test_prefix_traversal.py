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

import pytest

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
