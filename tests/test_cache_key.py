"""A3 security regression: AWSCache.__make_key + realpath containment.

Covers:
    - Normalisation of traversal/illegal tokens (mirrors prefixer rules).
    - realpath containment: any computed cache path must live under
      ``cache_dir`` (defense-in-depth against symlinks).
    - set/get round-trip within timeout.
    - TTL expiry path (entry expired => returns None, file purged).
"""
from __future__ import annotations

import os
import time

import pytest

from flask_s3_viewer.aws.cache import AWSCache
from flask_s3_viewer.errors import InvalidPrefix


@pytest.fixture
def cache(tmp_path):
    return AWSCache(cache_dir=str(tmp_path / 'cache'), timeout=60)


class TestMakeKeyNormal:
    def test_plain_key_produces_path_under_cache_dir(self, cache, tmp_path) -> None:
        # __make_key is name-mangled, access via the public set/get round-trip.
        cache.set('foo', {'x': 1})
        # The dir layout: <cache_dir>/foo/default
        root = str(tmp_path / 'cache')
        candidate = os.path.join(root, 'foo', 'default')
        assert os.path.isfile(candidate)


class TestMakeKeyRejected:
    @pytest.mark.parametrize(
        'bad_key',
        [
            '../etc',
            '../../etc',
            'a//b',
            'a/./b',
            'a/../b',
            '.',
            '..',
            'foo/..',
            'foo/.',
        ],
    )
    def test_traversal_tokens_rejected(self, cache, bad_key: str) -> None:
        with pytest.raises(InvalidPrefix):
            cache.set(bad_key, 'value')

    def test_backslash_rejected(self, cache) -> None:
        with pytest.raises(InvalidPrefix):
            cache.set('a\\b', 'value')

    def test_double_leading_slash_rejected(self, cache) -> None:
        with pytest.raises(InvalidPrefix):
            cache.set('//etc', 'value')


class TestRealpathContainment:
    """If a symlink (or any other escape) would land outside cache_dir, reject."""

    def test_symlink_division_cannot_escape_cache_dir(self, tmp_path) -> None:
        outside = tmp_path / 'outside'
        outside.mkdir()
        cache_dir = tmp_path / 'cache'
        cache_dir.mkdir()

        # Plant a symlink inside cache_dir that points outside.
        link = cache_dir / 'escape'
        os.symlink(str(outside), str(link))

        cache = AWSCache(cache_dir=str(cache_dir), timeout=60)
        # Using a ``division`` that resolves through the symlink should be
        # blocked. The realpath of <cache_dir>/escape/foo is <outside>/foo,
        # which is NOT under realpath(cache_dir) => InvalidPrefix.
        with pytest.raises(InvalidPrefix):
            cache.set('foo', 'value', division='escape')


class TestSetGetRoundTrip:
    def test_set_then_get_returns_value(self, cache) -> None:
        cache.set('foo/bar', {'hello': 'world'})
        assert cache.get('foo/bar') == {'hello': 'world'}

    def test_get_missing_returns_none(self, cache) -> None:
        assert cache.get('not-set') is None

    def test_get_after_ttl_returns_none(self, tmp_path) -> None:
        """Entry written with a tiny per-call timeout expires immediately."""
        cache = AWSCache(cache_dir=str(tmp_path / 'cache'), timeout=60)
        cache.set('foo', 'v', timeout=1)
        # Force expiry by sleeping past the timeout boundary.
        time.sleep(1.1)
        assert cache.get('foo') is None
        # And the expired file should have been removed on the miss path.
        assert not os.path.exists(
            os.path.join(str(tmp_path / 'cache'), 'foo', 'default')
        )

    def test_division_isolation(self, cache) -> None:
        cache.set('foo', 'a', division='bucket-1')
        cache.set('foo', 'b', division='bucket-2')
        assert cache.get('foo', division='bucket-1') == 'a'
        assert cache.get('foo', division='bucket-2') == 'b'

    def test_remove_clears_entry(self, cache) -> None:
        cache.set('foo', 'v')
        cache.remove('foo')
        assert cache.get('foo') is None

    def test_invalid_json_cache_entry_is_ignored_and_deleted(self, cache, tmp_path) -> None:
        target = tmp_path / 'cache' / 'foo'
        target.mkdir(parents=True, exist_ok=True)
        path = target / 'default'
        path.write_bytes(b'not-json')
        assert cache.get('foo') is None
        assert not path.exists()

    def test_cache_file_permissions_hardened(self, cache, tmp_path) -> None:
        cache.set('secure', {'x': 1})
        path = tmp_path / 'cache' / 'secure' / 'default'
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600


class TestTrailingSlashRstrip:
    """Trailing '/' is rstrip'd so 'foo' and 'foo/' map to the same key."""

    def test_trailing_slash_collapses(self, cache) -> None:
        cache.set('foo', 'v')
        assert cache.get('foo/') == 'v'
