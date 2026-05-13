"""Download endpoint coverage — Content-Disposition encoding branches
and the boto3 ``StreamingBody`` → ``Response(direct_passthrough)`` path.
"""
from __future__ import annotations

import urllib.parse


def _put(s3_bucket, key: str, body: bytes, content_type: str = 'text/plain') -> None:
    client, bucket = s3_bucket
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


class TestDownload:
    def test_missing_object_renders_404(self, client):
        rv = client.get('/fsv-test/files/' + urllib.parse.quote('ghost.txt'))
        assert rv.status_code == 404

    def test_ascii_filename_in_content_disposition(self, client, s3_bucket):
        _put(s3_bucket, 'note.txt', b'hello, ascii\n')
        rv = client.get('/fsv-test/files/' + urllib.parse.quote('note.txt'))
        assert rv.status_code == 200
        cd = rv.headers.get('Content-Disposition', '')
        # The wrapper sends `filename=note.txt` (no UTF-8 form needed).
        assert 'attachment' in cd
        assert 'note.txt' in cd
        assert 'filename*' not in cd

    def test_non_latin1_filename_uses_rfc5987_utf8(self, client, s3_bucket):
        """Korean characters can't fit in latin-1; the fallback path emits
        ``filename*=UTF-8''...`` per RFC 5987.
        """
        name = '한글.txt'
        _put(s3_bucket, name, '한글 본문'.encode())
        rv = client.get('/fsv-test/files/' + urllib.parse.quote(name))
        assert rv.status_code == 200
        cd = rv.headers.get('Content-Disposition', '')
        assert 'filename*' in cd
        assert "UTF-8''" in cd

    def test_response_carries_mimetype_from_boto3(self, client, s3_bucket):
        _put(s3_bucket, 'photo.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')
        rv = client.get('/fsv-test/files/' + urllib.parse.quote('photo.png'))
        assert rv.status_code == 200
        assert rv.mimetype == 'image/png'

    def test_cache_headers_prevent_revalidation(self, client, s3_bucket):
        _put(s3_bucket, 'fresh.txt', b'always fresh')
        rv = client.get('/fsv-test/files/' + urllib.parse.quote('fresh.txt'))
        assert rv.status_code == 200
        assert 'no-cache' in rv.headers.get('Cache-Control', '')
        assert rv.headers.get('Pragma') == 'no-cache'
        assert rv.headers.get('Expires') == '0'

    def test_streamingbody_passes_through_for_large_payloads(self, client, s3_bucket):
        """The download path uses ``Response(direct_passthrough=True)`` so it
        does not buffer the entire object. We can't easily verify streaming
        in a test (moto fits everything in memory), but we can sanity-check
        that a 1 MiB body comes back intact.
        """
        payload = b'\x42' * (1024 * 1024)
        _put(s3_bucket, 'big.bin', payload, content_type='application/octet-stream')
        rv = client.get('/fsv-test/files/' + urllib.parse.quote('big.bin'))
        assert rv.status_code == 200
        assert rv.data == payload
