"""RFC 7233 Range / 206 Partial Content support for ``GET /<ns>/files/<key>``.

Confirms the download endpoint:
  - forwards a ``Range: bytes=...`` header to S3 via boto3,
  - emits ``206 Partial Content`` + ``Content-Range`` + ``Content-Length``,
  - sets ``Accept-Ranges: bytes`` (so range-aware clients see the affordance),
  - returns ``416`` on a malformed / unsatisfiable Range,
  - keeps the legacy ``200 OK`` behavior when no Range header is sent.
"""
from __future__ import annotations

import urllib.parse

import pytest
from botocore.exceptions import ClientError

from flask_s3_viewer.errors import InvalidRangeError


def _put(s3_bucket, key: str, body: bytes, content_type: str = 'application/octet-stream') -> None:
    client, bucket = s3_bucket
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


class TestRangeRequest:
    PAYLOAD = bytes(range(256))  # deterministic 256-byte body
    KEY = 'ranged.bin'

    @pytest.fixture(autouse=True)
    def _put_object(self, s3_bucket):
        _put(s3_bucket, self.KEY, self.PAYLOAD)

    # ---- happy path: well-formed Range ---------------------------------

    def test_returns_206_with_content_range_and_length(self, client):
        rv = client.get(
            f'/fsv-test/files/{urllib.parse.quote(self.KEY)}',
            headers={'Range': 'bytes=0-9'},
        )
        assert rv.status_code == 206
        # boto3 returns ContentRange exactly as S3 reports it.
        assert rv.headers.get('Content-Range') == 'bytes 0-9/256'
        assert rv.headers.get('Content-Length') == '10'
        assert rv.headers.get('Accept-Ranges') == 'bytes'
        assert rv.data == self.PAYLOAD[:10]

    def test_returns_206_for_suffix_range(self, client):
        """``bytes=-N`` requests the LAST N bytes."""
        rv = client.get(
            f'/fsv-test/files/{urllib.parse.quote(self.KEY)}',
            headers={'Range': 'bytes=-32'},
        )
        assert rv.status_code == 206
        assert rv.headers.get('Content-Range') == 'bytes 224-255/256'
        assert rv.data == self.PAYLOAD[-32:]

    def test_returns_206_for_open_ended_range(self, client):
        """``bytes=N-`` requests from N to EOF."""
        rv = client.get(
            f'/fsv-test/files/{urllib.parse.quote(self.KEY)}',
            headers={'Range': 'bytes=128-'},
        )
        assert rv.status_code == 206
        assert rv.headers.get('Content-Range') == 'bytes 128-255/256'
        assert rv.data == self.PAYLOAD[128:]

    # ---- error path: malformed / unsatisfiable Range -------------------

    def test_unsatisfiable_range_returns_416(self, app, client):
        """Range start beyond object length → boto3 raises InvalidRange,
        the view layer maps it to 416 Range Not Satisfiable.

        moto v5 doesn't always emit ``InvalidRange`` for this case, so we
        also assert via the underlying wrapper to keep the pin meaningful
        even when the in-process mock disagrees with real S3.
        """
        viewer = app.extensions['flask_s3_viewer']['fsv-test']
        # First, exercise the wrapper directly with a forged ClientError
        # so the InvalidRangeError → 416 path is unambiguously covered.
        from unittest.mock import patch
        err = ClientError(
            {'Error': {'Code': 'InvalidRange', 'Message': 'forced'}},
            'GetObject',
        )
        with patch.object(viewer._s3, 'get_object', side_effect=err):
            with pytest.raises(InvalidRangeError):
                viewer.find_one(self.KEY, range='bytes=99999-')
        # And the HTTP layer maps the wrapper exception to 416.
        with patch.object(viewer._s3, 'get_object', side_effect=err):
            rv = client.get(
                f'/fsv-test/files/{urllib.parse.quote(self.KEY)}',
                headers={'Range': 'bytes=99999-'},
            )
        assert rv.status_code == 416

    # ---- regression: no Range still works (legacy 200 path) -----------

    def test_no_range_keeps_200_response(self, client):
        rv = client.get(f'/fsv-test/files/{urllib.parse.quote(self.KEY)}')
        assert rv.status_code == 200
        assert rv.headers.get('Accept-Ranges') == 'bytes'
        # The full payload is streamed back; no Content-Range header.
        assert 'Content-Range' not in rv.headers
        assert rv.data == self.PAYLOAD

    def test_accept_ranges_advertised_on_every_response(self, client):
        """Both 200 and 206 responses must advertise ``Accept-Ranges:
        bytes`` so range-aware clients know they can resume.
        """
        rv = client.get(f'/fsv-test/files/{urllib.parse.quote(self.KEY)}')
        assert rv.headers.get('Accept-Ranges') == 'bytes'
        rv2 = client.get(
            f'/fsv-test/files/{urllib.parse.quote(self.KEY)}',
            headers={'Range': 'bytes=0-9'},
        )
        assert rv2.headers.get('Accept-Ranges') == 'bytes'
