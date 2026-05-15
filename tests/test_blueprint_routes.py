"""Blueprint integration tests with moto-mocked S3.

Exercises every public route plus the A3 security boundary
(400 on path-traversal prefix).

Route layout (see flask_s3_viewer/blueprints/view.py):
    GET    /<ns>/files                  -> HTML listing
    POST   /<ns>/files                  -> mkdir (no files) or upload
    GET    /<ns>/files/<path:key>       -> download
    DELETE /<ns>/files/<path:key>       -> remove
    POST   /<ns>/files/presign          -> presigned POST JSON

The ``client`` and ``s3_bucket`` fixtures come from conftest.py.
"""
from __future__ import annotations

import io
import urllib.parse


def _ns_path(suffix: str) -> str:
    """Build a path under the registered FlaskS3Viewer namespace ('fsv-test')."""
    return f'/fsv-test{suffix}'


class TestListing:
    def test_get_files_empty_bucket(self, client) -> None:
        rv = client.get(_ns_path('/files'))
        assert rv.status_code == 200
        # Page rendered; nothing to assert on body shape beyond a 200.

    def test_get_files_invalid_prefix_rejected(self, client) -> None:
        # A3: traversal in the query string must surface as 400.
        rv = client.get(_ns_path('/files?prefix=../etc'))
        assert rv.status_code == 400

    def test_listing_sets_security_headers(self, client) -> None:
        rv = client.get(_ns_path('/files'))
        assert rv.headers['X-Content-Type-Options'] == 'nosniff'
        assert rv.headers['X-Frame-Options'] == 'DENY'
        assert 'Content-Security-Policy' in rv.headers
        assert "connect-src 'self' https:" in rv.headers['Content-Security-Policy']

    def test_listing_does_not_emit_htmx_js_eval_attrs(self, client) -> None:
        rv = client.get(_ns_path('/files'))
        assert b"hx-vals='js:" not in rv.data
        assert b'hx-vals="js:' not in rv.data

    def test_listing_paginates_after_max_items(self, app, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        max_items = app.extensions['flask_s3_viewer']['fsv-test'].max_items
        for i in range(max_items + 1):
            s3_client.put_object(Bucket=bucket, Key=f'page-{i}.txt', Body=b'x')
        rv = client.get(_ns_path('/files'))
        assert rv.status_code == 200
        assert b'>1<' in rv.data
        assert b'>2<' in rv.data
        assert b'page=2' in rv.data
        assert rv.data.count(b'data-fsv-type="file"') == max_items

    def test_listing_formats_modified_with_configured_timezone(self, s3_bucket, tmp_path) -> None:
        from flask import Flask

        from flask_s3_viewer import FlaskS3Viewer

        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='time.txt', Body=b'x')

        app = Flask(__name__)
        app.config['TESTING'] = True
        FlaskS3Viewer(
            app,
            namespace='tz',
            config={
                'profile_name': None,
                'bucket_name': bucket,
                'region_name': 'us-east-1',
                'access_key': 'testing',
                'secret_key': 'testing',
                'cache_dir': str(tmp_path / 'tz-cache'),
                'use_cache': True,
                'ttl': 60,
                'timezone': 'Asia/Seoul',
            },
        )

        rv = app.test_client().get('/tz/files')

        assert rv.status_code == 200
        assert b'time.txt' in rv.data
        assert b'KST' in rv.data
        assert b'+00:00' not in rv.data


class TestMkdir:
    def test_post_mkdir_creates_empty_object(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        rv = client.post(
            _ns_path('/files'),
            data={'prefix': 'newdir/'},
            content_type='application/x-www-form-urlencoded',
        )
        assert rv.status_code == 201
        # S3 should now have a placeholder object at 'newdir/'.
        resp = s3_client.list_objects_v2(Bucket=bucket, Prefix='newdir/')
        keys = [obj['Key'] for obj in resp.get('Contents', [])]
        assert 'newdir/' in keys

    def test_post_mkdir_invalid_prefix_rejected(self, client) -> None:
        rv = client.post(_ns_path('/files'), data={'prefix': '../etc'})
        assert rv.status_code == 400


class TestUpload:
    def test_post_upload_file_creates_object(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        data = {
            'prefix': 'uploads/',
            'files[]': (io.BytesIO(b'hello world'), 'hello.txt'),
        }
        rv = client.post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
        )
        assert rv.status_code == 201
        resp = s3_client.list_objects_v2(Bucket=bucket, Prefix='uploads/')
        keys = [obj['Key'] for obj in resp.get('Contents', [])]
        assert 'uploads/hello.txt' in keys


class TestDownload:
    def test_get_download_returns_object(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='dl/hello.txt', Body=b'hi!')
        rv = client.get(_ns_path('/files/dl/hello.txt'))
        assert rv.status_code == 200
        assert b'hi!' in rv.data
        assert 'attachment' in rv.headers.get('Content-Disposition', '')

    def test_get_download_missing_returns_404(self, client) -> None:
        rv = client.get(_ns_path('/files/missing/never.txt'))
        # The handler renders the error template with HTTP 404.
        assert rv.status_code == 404


class TestDelete:
    def test_delete_object_returns_204(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='del/bye.txt', Body=b'bye')
        rv = client.delete(_ns_path('/files/del/bye.txt'))
        assert rv.status_code == 204
        resp = s3_client.list_objects_v2(Bucket=bucket, Prefix='del/')
        keys = [o['Key'] for o in resp.get('Contents', [])]
        assert 'del/bye.txt' not in keys

    def test_delete_folder_removes_marker_and_children(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='folder/', Body=b'')
        s3_client.put_object(Bucket=bucket, Key='folder/a.txt', Body=b'a')
        s3_client.put_object(Bucket=bucket, Key='folder/empty-child/', Body=b'')
        s3_client.put_object(Bucket=bucket, Key='folder/nested/b.txt', Body=b'b')

        rv = client.delete(_ns_path('/files/folder/'))

        assert rv.status_code == 204
        resp = s3_client.list_objects_v2(Bucket=bucket, Prefix='folder/')
        assert resp.get('Contents') is None

    def test_delete_folder_invalidates_parent_listing_cache(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='cached-folder/', Body=b'')
        s3_client.put_object(Bucket=bucket, Key='cached-folder/a.txt', Body=b'a')

        first = client.get(_ns_path('/files'), headers={'HX-Request': 'true'})
        assert first.status_code == 200
        assert b'cached-folder/' in first.data

        rv = client.delete(_ns_path('/files/cached-folder/'))
        assert rv.status_code == 204

        second = client.get(_ns_path('/files'), headers={'HX-Request': 'true'})
        assert second.status_code == 200
        assert b'cached-folder/' not in second.data

    def test_delete_invalid_prefix_returns_400(self, client) -> None:
        # A3: ``..%2Fetc/`` decodes to '../etc/' which triggers the trailing-/
        # branch in AWSS3Client.remove() -> find_all() -> prefixer() which
        # raises InvalidPrefix. files_delete catches it and returns 400
        # (not 500).
        escaped = urllib.parse.quote('../etc/', safe='')
        rv = client.delete(_ns_path(f'/files/{escaped}'))
        assert rv.status_code == 400


class TestPresign:
    def test_post_presign_returns_json(self, client) -> None:
        rv = client.post(
            _ns_path('/files/presign'),
            data={'prefix': 'uploads/', 'file_list': 'a.txt,b.txt'},
        )
        assert rv.status_code == 200
        body = rv.get_json()
        assert isinstance(body, list)
        assert len(body) == 2

    def test_post_presign_invalid_prefix_returns_400(self, client) -> None:
        rv = client.post(
            _ns_path('/files/presign'),
            data={'prefix': '../etc', 'file_list': 'a.txt'},
        )
        assert rv.status_code == 400


class TestHTMXPartials:
    """B3: ``HX-Request`` header switches /files GET to the partial."""

    def test_files_get_full_page_includes_layout(self, client) -> None:
        rv = client.get(_ns_path('/files'))
        assert rv.status_code == 200
        # Full page renders the <html> shell from layout.html.
        assert b'<html' in rv.data

    def test_files_get_htmx_returns_partial(self, client) -> None:
        rv = client.get(
            _ns_path('/files'),
            headers={'HX-Request': 'true'},
        )
        assert rv.status_code == 200
        # Partial response is the inner fragment — no layout shell.
        assert b'<html' not in rv.data

    def test_files_delete_htmx_returns_200(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='hx/bye.txt', Body=b'bye')
        rv = client.delete(
            _ns_path('/files/hx/bye.txt'),
            headers={'HX-Request': 'true'},
        )
        # HTMX flow swaps the row on 200; non-HTMX callers still get 204.
        assert rv.status_code == 200


class TestObjectHostname:
    """B4: ``object_hostname`` switches file name anchors to external links.

    The default ``client`` fixture leaves ``object_hostname`` unset so the
    file name links to the in-process download route. To assert the external
    prefix path we build a dedicated app + client without reusing the cached
    fixture chain (different ``object_hostname`` value).
    """

    def _make_client(self, s3_bucket, tmp_path, hostname):
        from flask import Flask

        from flask_s3_viewer import FlaskS3Viewer

        _client, bucket = s3_bucket
        flask_app = Flask(__name__)
        flask_app.config['TESTING'] = True
        FlaskS3Viewer(
            flask_app,
            namespace='fsv-test',
            object_hostname=hostname,
            config={
                'profile_name': None,
                'bucket_name': bucket,
                'region_name': 'us-east-1',
                'access_key': 'testing',
                'secret_key': 'testing',
                'cache_dir': str(tmp_path / 'cache'),
                'use_cache': True,
                'ttl': 60,
            },
        )
        return flask_app.test_client()

    def test_listing_uses_object_hostname_for_download_link(self, s3_bucket, tmp_path) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='media/cat.jpg', Body=b'jpg')
        client = self._make_client(
            s3_bucket, tmp_path, hostname='https://cdn.example.com',
        )
        # Root listing only surfaces the 'media/' prefix; navigate into it to
        # exercise the file row anchor.
        rv = client.get(_ns_path('/files?prefix=media/'))
        assert rv.status_code == 200
        # External link prefix wins when object_hostname is configured.
        assert b'https://cdn.example.com/media/cat.jpg' in rv.data
        # Anchor should target a new tab (rel/target attributes present).
        assert b'rel="noopener noreferrer"' in rv.data

    def test_listing_uses_object_hostname_with_base_path(self, s3_bucket, tmp_path) -> None:
        from flask import Flask

        from flask_s3_viewer import FlaskS3Viewer

        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='scoped/media/cat.jpg', Body=b'jpg')
        app = Flask(__name__)
        FlaskS3Viewer(
            app,
            namespace='bp-host',
            object_hostname='https://cdn.example.com',
            config={
                'profile_name': None,
                'bucket_name': bucket,
                'region_name': 'ap-northeast-2',
                'access_key': 'testing',
                'secret_key': 'testing',
                'cache_dir': str(tmp_path / 'cache-host'),
                'use_cache': True,
                'ttl': 60,
                'base_path': 'scoped',
            },
        )
        rv = app.test_client().get('/bp-host/files?prefix=media/')
        assert rv.status_code == 200
        assert b'https://cdn.example.com/scoped/media/cat.jpg' in rv.data

    def test_listing_falls_back_to_download_route_without_hostname(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='media/dog.jpg', Body=b'jpg')
        rv = client.get(_ns_path('/files?prefix=media/'))
        assert rv.status_code == 200
        # In-process download route is used when object_hostname is not set.
        assert b'/files/media/dog.jpg' in rv.data
        assert b'https://cdn.example.com' not in rv.data


class TestSearch:
    """Listing search runs as a Python substring filter (case-insensitive,
    Unicode-safe). Earlier versions used a JMESPath f-string and could
    only match ASCII reliably.
    """

    def test_search_matches_korean_keys(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='보고서.txt', Body=b'kr')
        s3_client.put_object(Bucket=bucket, Key='report.txt', Body=b'en')
        rv = client.get(_ns_path('/files?search=보고서'))
        assert rv.status_code == 200
        assert '보고서.txt'.encode() in rv.data
        assert b'report.txt' not in rv.data

    def test_search_is_case_insensitive(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='README.MD', Body=b'a')
        rv = client.get(_ns_path('/files?search=readme'))
        assert rv.status_code == 200
        assert b'README.MD' in rv.data

    def test_search_does_not_recurse_into_subfolders(self, client, s3_bucket) -> None:
        """Search stays scoped to the current folder and does not pull
        matches from nested descendants.
        """
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='reports/2026/한글.pdf', Body=b'x')
        s3_client.put_object(Bucket=bucket, Key='reports/2025/other.pdf', Body=b'x')
        rv = client.get(_ns_path('/files?search=한글'))
        assert rv.status_code == 200
        assert '한글.pdf'.encode() not in rv.data
        assert b'other.pdf' not in rv.data

    def test_search_within_prefix_finds_direct_children_only(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='reports/한글.pdf', Body=b'x')
        s3_client.put_object(Bucket=bucket, Key='reports/2026/한글-깊음.pdf', Body=b'x')
        rv = client.get(_ns_path('/files?prefix=reports/&search=한글'))
        assert rv.status_code == 200
        assert '한글.pdf'.encode() in rv.data
        assert '한글-깊음.pdf'.encode() not in rv.data

    def test_search_within_prefix_does_not_match_current_folder_name(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='root/aaaa/photo.png', Body=b'x')
        s3_client.put_object(Bucket=bucket, Key='root/aaaa/report.pdf', Body=b'x')
        s3_client.put_object(Bucket=bucket, Key='root/aaaa/alpha.txt', Body=b'x')

        rv = client.get(_ns_path('/files?prefix=root/aaaa/&search=a'))

        assert rv.status_code == 200
        assert b'alpha.txt' in rv.data
        assert b'photo.png' not in rv.data
        assert b'report.pdf' not in rv.data

    def test_search_matches_nfd_keys_with_nfc_query(self, s3_bucket) -> None:
        """macOS-style uploads land in S3 as NFD (decomposed Hangul);
        the browser IME sends NFC. Without explicit normalisation the
        two byte sequences never compare equal even though they render
        identically — partial-typed '스' silently returns nothing.
        """
        import unicodedata
        s3_client, bucket = s3_bucket
        nfc = '스크린샷.png'
        nfd = unicodedata.normalize('NFD', nfc)
        assert nfc != nfd  # paranoia: the two forms ARE different bytes
        s3_client.put_object(Bucket=bucket, Key=nfd, Body=b'x')
        # Search with the NFC partial that the browser IME emits.
        rv = self._search(bucket, 'fsv-test', '스')
        # The match itself: we should see exactly one hit. The rendered
        # HTML keeps the original NFD key, so we look for that form.
        body = rv.get_data(as_text=True)
        assert rv.status_code == 200
        assert nfd in body  # NFD because the listing renders the raw S3 key

    def _search(self, bucket, namespace, q):
        import tempfile
        import urllib.parse

        from flask import Flask

        from flask_s3_viewer import FlaskS3Viewer
        app = Flask(__name__)
        app.config['TESTING'] = True
        with tempfile.TemporaryDirectory() as cache:
            FlaskS3Viewer(
                app, namespace='nfd',
                config={
                    'profile_name': None, 'bucket_name': bucket,
                    'region_name': 'us-east-1',
                    'access_key': 'x', 'secret_key': 'x',
                    'cache_dir': cache,
                    'use_cache': True, 'ttl': 60,
                },
            )
            return app.test_client().get(
                '/nfd/files?search=' + urllib.parse.quote(q)
            )

    def test_search_finds_folders_whose_name_matches(self, client, s3_bucket) -> None:
        """A folder whose name contains the query shows up as a folder
        row in the search result, alongside any matching files.
        """
        s3_client, bucket = s3_bucket
        # Folder 'reports/' has a child file; the folder name itself
        # contains the query 'rep'.
        s3_client.put_object(Bucket=bucket, Key='reports/Q1.pdf', Body=b'x')
        # An unrelated file at root to confirm it isn't included.
        s3_client.put_object(Bucket=bucket, Key='untouched.txt', Body=b'x')
        rv = client.get(_ns_path('/files?search=rep'))
        assert rv.status_code == 200
        # Folder row links into the matching folder.
        assert b'href="/fsv-test/files?prefix=reports/&amp;search=rep"' in rv.data
        # Files outside the match are absent.
        assert b'untouched.txt' not in rv.data

    def test_search_does_not_match_base_path_segment(self, s3_bucket, tmp_path) -> None:
        """Regression: when ``base_path='/test'``, typing 'test' used to
        match every object in the bucket because the comparison ran
        against the full S3 key. Match against the user-visible key.
        """
        import boto3
        from flask import Flask

        from flask_s3_viewer import FlaskS3Viewer

        _, bucket = s3_bucket
        c = boto3.client('s3', region_name='us-east-1')
        c.put_object(Bucket=bucket, Key='test/photo.png', Body=b'x')
        c.put_object(Bucket=bucket, Key='test/report.pdf', Body=b'x')

        app = Flask(__name__)
        app.config['TESTING'] = True
        FlaskS3Viewer(
            app, namespace='bp',
            config={
                'profile_name': None, 'bucket_name': bucket,
                'region_name': 'us-east-1',
                'access_key': 'x', 'secret_key': 'x',
                'cache_dir': str(tmp_path / 'cache'),
                'use_cache': True, 'ttl': 60,
                'base_path': '/test',
            },
        )
        # 'test' should match NOTHING — it's the base_path segment, not
        # part of any user-visible key.
        rv = app.test_client().get('/bp/files?search=test')
        assert rv.status_code == 200
        assert b'photo.png' not in rv.data
        assert b'report.pdf' not in rv.data
        # 'report' still matches its file as before.
        rv2 = app.test_client().get('/bp/files?search=report')
        assert rv2.status_code == 200
        assert b'report.pdf' in rv2.data

    def test_search_within_base_path_prefix_does_not_match_current_folder_name(self, s3_bucket, tmp_path) -> None:
        import boto3
        from flask import Flask

        from flask_s3_viewer import FlaskS3Viewer

        _, bucket = s3_bucket
        c = boto3.client('s3', region_name='us-east-1')
        c.put_object(Bucket=bucket, Key='root/aaaa/1.png', Body=b'x')
        c.put_object(Bucket=bucket, Key='root/aaaa/10.png', Body=b'x')
        c.put_object(Bucket=bucket, Key='root/aaaa/alpha.png', Body=b'x')

        app = Flask(__name__)
        app.config['TESTING'] = True
        FlaskS3Viewer(
            app, namespace='rooted',
            config={
                'profile_name': None, 'bucket_name': bucket,
                'region_name': 'us-east-1',
                'access_key': 'x', 'secret_key': 'x',
                'cache_dir': str(tmp_path / 'rooted-cache'),
                'use_cache': True, 'ttl': 60,
                'base_path': 'root',
            },
        )

        rv = app.test_client().get('/rooted/files?prefix=aaaa/&search=aaa')

        assert rv.status_code == 200
        assert b'1.png' not in rv.data
        assert b'10.png' not in rv.data
        assert b'alpha.png' not in rv.data

    def test_search_folder_navigation_preserves_query(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='reports/Q1.pdf', Body=b'x')
        rv = client.get(_ns_path('/files?search=rep'))
        assert rv.status_code == 200
        assert b'/fsv-test/files?prefix=reports/&amp;search=rep' in rv.data

    def test_htmx_upload_refresh_keeps_search_filter(self, client, s3_bucket) -> None:
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='report-old.txt', Body=b'old')
        data = {
            'prefix': '',
            'search': 'report',
            'files[]': (io.BytesIO(b'new'), 'report-new.txt'),
        }
        rv = client.post(
            _ns_path('/files'),
            data=data,
            content_type='multipart/form-data',
            headers={'HX-Request': 'true'},
        )
        assert rv.status_code == 200
        assert b'name="search" value="report"' in rv.data
        assert b'report-old.txt' in rv.data
        assert b'report-new.txt' in rv.data

    def test_search_with_special_characters_does_not_crash(self, client, s3_bucket) -> None:
        """A query containing JMESPath metacharacters (backtick, quote,
        backslash) used to break the listing — now it's a plain Python
        ``in`` check and just returns whatever matches.
        """
        s3_client, bucket = s3_bucket
        s3_client.put_object(Bucket=bucket, Key='weird`key.txt', Body=b'x')
        rv = client.get(_ns_path('/files?search=' + urllib.parse.quote('`')))
        assert rv.status_code == 200
        assert b'weird`key.txt' in rv.data


class TestBranding:
    """Title / logo come from the FlaskS3Viewer instance and have to
    survive every render path — the GET listing handler had been
    silently dropping them, which is what made ``title='...'`` look
    like a no-op in earlier builds.
    """

    def test_title_renders_in_full_page(self, app, client) -> None:
        # The default fixture uses title=None → 'Flask S3 Viewer'.
        # Mutate the running viewer so we don't need a second fixture.
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        viewer.title = 'My Files'
        rv = client.get(_ns_path('/files'))
        assert rv.status_code == 200
        assert b'<h1' in rv.data
        assert b'My Files' in rv.data


class TestParentNavigation:
    """Parent-folder (".." row) appears only inside a sub-prefix and links
    one segment up, mirroring familiar file-browser semantics.
    """

    def test_no_parent_row_at_root(self, client) -> None:
        rv = client.get(_ns_path('/files'))
        assert rv.status_code == 200
        assert b'Go up to' not in rv.data

    def test_parent_row_links_to_root_from_one_level_deep(self, client) -> None:
        rv = client.get(_ns_path('/files?prefix=foo/'))
        assert rv.status_code == 200
        # Title attribute reports the (empty) parent as "(root)" for clarity.
        assert b'Go up to (root)' in rv.data

    def test_parent_row_links_to_one_level_up_from_nested(self, client) -> None:
        rv = client.get(_ns_path('/files?prefix=foo/bar/'))
        assert rv.status_code == 200
        assert b'Go up to foo/' in rv.data
        # Flask url_for keeps the slash literal in query strings, so the
        # parent link reads ``?prefix=foo/`` rather than the percent-encoded
        # form.
        assert b'prefix=foo/' in rv.data
