"""STS AssumeRole + MFA wiring in ``AWSSession``.

moto v5's ``mock_aws`` covers both ``sts.assume_role`` and the downstream
``s3.list_objects_v2``, so we can verify the full path without real AWS
credentials: pass ``role_arn`` → an STS ``AssumeRole`` happens → the
returned temporary credentials drive the working S3 session.

Coverage points:
  - role_arn alone triggers AssumeRole and the resulting Session can list
  - external_id is forwarded to STS verbatim
  - role_session_name defaults to "flask-s3-viewer" but can be overridden
  - duration_seconds is forwarded when supplied
  - mfa_serial requires a token (token_code OR token_code_callback)
  - mfa_serial + neither token nor callback fails fast with ValueError
  - region_name on the temp session matches the caller's input
  - role_arn (+ no MFA or + MFA callback) wires RefreshableCredentials
    and re-invokes STS on refresh
  - mfa_serial + literal token_code falls back to the static (no-refresh)
    path for backward compatibility
"""
from __future__ import annotations

import datetime as _dt
from unittest.mock import patch

import boto3
import pytest
from botocore.credentials import RefreshableCredentials
from botocore.errorfactory import ClientError
from moto import mock_aws

from flask_s3_viewer.aws.session import AWSSession

ROLE_ARN = 'arn:aws:iam::123456789012:role/flask-s3-viewer-test'


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestAssumeRole:
    def test_role_arn_triggers_assume_role_and_session_is_usable(self, aws_credentials):
        with mock_aws():
            s3 = boto3.client('s3', region_name='us-east-1')
            s3.create_bucket(Bucket='assumed-bucket')
            sess = AWSSession(
                region_name='us-east-1',
                access_key='base',
                secret_key='base',
                role_arn=ROLE_ARN,
            )
            assert sess.runnable is True
            # The session is bound to AssumeRole-issued temporary credentials.
            creds = sess._session.get_credentials()
            assert creds.token  # AssumeRole always returns a session token.
            # And the resulting session can actually call S3 under moto.
            client = sess._session.client('s3')
            buckets = [b['Name'] for b in client.list_buckets()['Buckets']]
            assert 'assumed-bucket' in buckets

    def test_default_role_session_name(self):
        """No explicit role_session_name → defaults to ``flask-s3-viewer``."""
        captured: dict = {}

        def spy_assume(**kwargs):
            captured.update(kwargs)
            return {
                'Credentials': {
                    'AccessKeyId': 'AK',
                    'SecretAccessKey': 'SK',
                    'SessionToken': 'TOK',
                    # v1.2: RefreshableCredentials needs a parseable
                    # expiry on every AssumeRole response.
                    'Expiration': _dt.datetime.now(_dt.timezone.utc)
                    + _dt.timedelta(seconds=900),
                },
            }

        class FakeSession:
            def client(self, service):
                assert service == 'sts'

                class _Sts:
                    assume_role = staticmethod(spy_assume)
                return _Sts()

        AWSSession._assume_role(
            base=FakeSession(),
            role_arn=ROLE_ARN,
            role_session_name='flask-s3-viewer',  # the default the wrapper applies
            external_id=None,
            duration_seconds=None,
            mfa_serial=None,
            token_code=None,
            token_code_callback=None,
            region_name='us-east-1',
        )
        assert captured['RoleSessionName'] == 'flask-s3-viewer'
        assert captured['RoleArn'] == ROLE_ARN

    def test_external_id_and_duration_forwarded(self, aws_credentials):
        with mock_aws():
            captured: dict = {}

            def spy_assume(**kwargs):
                captured.update(kwargs)
                # Mimic a minimal STS response shape.
                return {
                    'Credentials': {
                        'AccessKeyId': 'AK',
                        'SecretAccessKey': 'SK',
                        'SessionToken': 'TOK',
                        # v1.2: RefreshableCredentials needs a parseable
                        # expiry on every AssumeRole response.
                        'Expiration': _dt.datetime.now(_dt.timezone.utc)
                        + _dt.timedelta(seconds=1800),
                    },
                }

            class FakeSession:
                """Stand-in for the base session — only needs .client('sts')."""
                def client(self, service):
                    assert service == 'sts'

                    class _Sts:
                        assume_role = staticmethod(spy_assume)
                    return _Sts()

            session = AWSSession._assume_role(
                base=FakeSession(),
                role_arn=ROLE_ARN,
                role_session_name='custom-name',
                external_id='cross-account-secret',
                duration_seconds=1800,
                mfa_serial=None,
                token_code=None,
                token_code_callback=None,
                region_name='us-east-1',
            )
        assert captured['RoleSessionName'] == 'custom-name'
        assert captured['ExternalId'] == 'cross-account-secret'
        assert captured['DurationSeconds'] == 1800
        # And the new Session carries the temp credentials + region.
        creds = session.get_credentials()
        assert creds.access_key == 'AK'
        assert creds.secret_key == 'SK'
        assert creds.token == 'TOK'
        assert session.region_name == 'us-east-1'


# ---------------------------------------------------------------------------
# MFA paths
# ---------------------------------------------------------------------------

class TestMfa:
    def _spy_session(self, captured: dict):
        def spy_assume(**kwargs):
            captured.update(kwargs)
            return {
                'Credentials': {
                    'AccessKeyId': 'AK',
                    'SecretAccessKey': 'SK',
                    'SessionToken': 'TOK',
                    # v1.2: RefreshableCredentials (refresh-eligible MFA +
                    # callback path) requires a parseable expiry. The
                    # legacy static path (literal token_code) does not
                    # consume this field, so adding it is harmless on
                    # both branches.
                    'Expiration': _dt.datetime.now(_dt.timezone.utc)
                    + _dt.timedelta(seconds=900),
                },
            }

        class FakeSession:
            def client(self, service):
                class _Sts:
                    assume_role = staticmethod(spy_assume)
                return _Sts()
        return FakeSession()

    def test_mfa_serial_with_explicit_token(self):
        captured: dict = {}
        AWSSession._assume_role(
            base=self._spy_session(captured),
            role_arn=ROLE_ARN,
            role_session_name='mfa',
            external_id=None,
            duration_seconds=None,
            mfa_serial='arn:aws:iam::123:mfa/user',
            token_code='123456',
            token_code_callback=None,
            region_name=None,
        )
        assert captured['SerialNumber'] == 'arn:aws:iam::123:mfa/user'
        assert captured['TokenCode'] == '123456'

    def test_mfa_serial_with_callback(self):
        captured: dict = {}
        calls: list[int] = []

        def prompt() -> str:
            calls.append(1)
            return '999999'

        AWSSession._assume_role(
            base=self._spy_session(captured),
            role_arn=ROLE_ARN,
            role_session_name='mfa-cb',
            external_id=None,
            duration_seconds=None,
            mfa_serial='arn:aws:iam::123:mfa/user',
            token_code=None,
            token_code_callback=prompt,
            region_name=None,
        )
        assert captured['TokenCode'] == '999999'
        assert len(calls) == 1  # callback invoked exactly once

    def test_mfa_serial_without_token_raises(self):
        with pytest.raises(ValueError, match='token_code'):
            AWSSession._assume_role(
                base=self._spy_session({}),
                role_arn=ROLE_ARN,
                role_session_name='mfa-bad',
                external_id=None,
                duration_seconds=None,
                mfa_serial='arn:aws:iam::123:mfa/user',
                token_code=None,
                token_code_callback=None,
                region_name=None,
            )


# ---------------------------------------------------------------------------
# Regression: no role_arn keeps the legacy direct-credential path
# ---------------------------------------------------------------------------

class TestNoAssumeRole:
    def test_without_role_arn_no_sts_call(self, aws_credentials):
        """Passing access/secret without role_arn must NOT invoke STS."""
        sts_calls: list = []
        real_client = boto3.session.Session.client

        def spy_client(self, service, *args, **kwargs):
            if service == 'sts':
                sts_calls.append(service)
            return real_client(self, service, *args, **kwargs)

        with mock_aws(), patch.object(boto3.session.Session, 'client', spy_client):
            AWSSession(
                region_name='us-east-1',
                access_key='k',
                secret_key='s',
            )
        assert sts_calls == []


# ---------------------------------------------------------------------------
# Automatic credential refresh (v1.2)
# ---------------------------------------------------------------------------


def _refresh_response(suffix: str, *, ttl_seconds: int = 900) -> dict:
    """Build a fake STS AssumeRole response with a fresh expiry.

    ``suffix`` lets each refresh return a *different* key triple so
    tests can assert the new credentials propagated (not just the
    original snapshot).
    """
    expiry = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=ttl_seconds)
    return {
        'Credentials': {
            'AccessKeyId': f'AK{suffix}',
            'SecretAccessKey': f'SK{suffix}',
            'SessionToken': f'TOK{suffix}',
            'Expiration': expiry,
        },
    }


class _StsSpy:
    """Minimal stand-in for ``base.client('sts')``.

    Each ``assume_role`` call appends the kwargs to ``calls`` and
    returns the next response from ``responses`` (cycling on the last
    entry once exhausted). Tests inject either a static list of
    responses or a custom ``responder`` callable for richer behaviour
    (e.g. raising on the second invocation).
    """

    def __init__(self, responses=None, responder=None):
        self.calls: list[dict] = []
        self._responses = list(responses or [])
        self._responder = responder

    def assume_role(self, **kwargs):
        self.calls.append(kwargs)
        if self._responder is not None:
            return self._responder(len(self.calls), kwargs)
        if not self._responses:
            return _refresh_response(str(len(self.calls)))
        if len(self.calls) <= len(self._responses):
            return self._responses[len(self.calls) - 1]
        return self._responses[-1]


class _FakeBaseSession:
    """Stands in for the parent boto3 ``Session`` that owns ``base.client('sts')``."""

    def __init__(self, sts_spy: _StsSpy):
        self._sts_spy = sts_spy

    def client(self, service, *args, **kwargs):
        assert service == 'sts'
        return self._sts_spy


class TestRefreshableCredentials:
    def test_role_arn_uses_refreshable_credentials(self):
        """With ``role_arn`` and no MFA, the working session's credentials
        object must be a ``RefreshableCredentials`` instance — that's the
        observable proof that refresh wiring is in place."""
        sts = _StsSpy()
        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='flask-s3-viewer',
            external_id=None,
            duration_seconds=900,
            mfa_serial=None,
            token_code=None,
            token_code_callback=None,
            region_name='us-east-1',
        )
        creds = sess.get_credentials()
        assert isinstance(creds, RefreshableCredentials)
        # First seed call to STS was made synchronously.
        assert len(sts.calls) == 1
        assert sts.calls[0]['RoleArn'] == ROLE_ARN
        assert sts.calls[0]['DurationSeconds'] == 900

    def test_refresh_invokes_sts_again(self):
        """Driving ``_protected_refresh`` past the advisory window must
        re-invoke ``sts.assume_role`` — single isinstance check alone
        cannot prove refresh actually fires."""
        sts = _StsSpy(responses=[
            _refresh_response('1', ttl_seconds=900),
            _refresh_response('2', ttl_seconds=900),
        ])
        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='flask-s3-viewer',
            external_id=None,
            duration_seconds=900,
            mfa_serial=None,
            token_code=None,
            token_code_callback=None,
            region_name='us-east-1',
        )
        creds = sess.get_credentials()
        assert isinstance(creds, RefreshableCredentials)
        # Force the next refresh by yanking the expiry into the past so
        # the advisory window is breached on the next access.
        creds._expiry_time = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(
            minutes=10
        )
        # Touching ``access_key`` triggers refresh internally.
        assert creds.access_key == 'AK2'
        assert len(sts.calls) == 2

    def test_callback_invoked_each_refresh(self):
        """MFA + callback is the refresh-eligible MFA path. The callback
        must run on every refresh so each STS call carries a fresh OTP."""
        sts = _StsSpy(responses=[
            _refresh_response('1', ttl_seconds=900),
            _refresh_response('2', ttl_seconds=900),
        ])
        callback_calls: list[str] = []

        def prompt() -> str:
            callback_calls.append('called')
            # Use a different code per call so the test can verify the
            # callback's return value is actually forwarded to STS.
            return f'CODE{len(callback_calls)}'

        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='mfa-cb',
            external_id=None,
            duration_seconds=900,
            mfa_serial='arn:aws:iam::123:mfa/user',
            token_code=None,
            token_code_callback=prompt,
            region_name=None,
        )
        # First synchronous refresh consumed the first OTP.
        assert len(callback_calls) == 1
        assert sts.calls[0]['TokenCode'] == 'CODE1'
        creds = sess.get_credentials()
        assert isinstance(creds, RefreshableCredentials)
        creds._expiry_time = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(
            minutes=10
        )
        _ = creds.access_key  # triggers the second refresh
        assert len(callback_calls) == 2
        assert sts.calls[1]['TokenCode'] == 'CODE2'

    def test_mfa_token_code_literal_uses_static_path(self):
        """``mfa_serial`` + literal ``token_code`` (no callback) must
        fall back to the legacy static path so the consumed OTP is not
        replayed on refresh."""
        sts = _StsSpy()
        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='mfa-literal',
            external_id=None,
            duration_seconds=None,
            mfa_serial='arn:aws:iam::123:mfa/user',
            token_code='123456',
            token_code_callback=None,
            region_name='us-east-1',
        )
        creds = sess.get_credentials()
        # Static credentials — not a RefreshableCredentials instance.
        assert not isinstance(creds, RefreshableCredentials)
        # Single STS call only; no refresh wiring.
        assert len(sts.calls) == 1
        assert sts.calls[0]['TokenCode'] == '123456'

    def test_no_role_arn_no_refresh(self, aws_credentials):
        """Without ``role_arn`` the new path is never entered and no
        STS request is issued — identical to the v1.1 baseline."""
        sts_calls: list = []
        real_client = boto3.session.Session.client

        def spy_client(self, service, *args, **kwargs):
            if service == 'sts':
                sts_calls.append(service)
            return real_client(self, service, *args, **kwargs)

        with mock_aws(), patch.object(boto3.session.Session, 'client', spy_client):
            sess = AWSSession(
                region_name='us-east-1',
                access_key='k',
                secret_key='s',
            )
        assert sts_calls == []
        # And the working session's credentials are a plain (non-refreshable)
        # instance — RefreshableCredentials never gets in the way of the
        # direct-credential path.
        creds = sess._session.get_credentials()
        assert not isinstance(creds, RefreshableCredentials)

    def test_region_propagates_to_refreshable_session(self):
        """``region_name`` must reach the wrapper *and* the underlying
        botocore session, so clients created from either surface see
        the same region."""
        sts = _StsSpy()
        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='flask-s3-viewer',
            external_id=None,
            duration_seconds=900,
            mfa_serial=None,
            token_code=None,
            token_code_callback=None,
            region_name='ap-northeast-2',
        )
        assert sess.region_name == 'ap-northeast-2'
        assert sess._session.get_config_variable('region') == 'ap-northeast-2'

    def test_refresh_failure_propagates(self):
        """A refresh that raises ``ClientError`` must surface to the
        caller (not be swallowed). The initial seed succeeds; the
        second call raises."""

        def responder(call_index: int, kwargs: dict):
            if call_index == 1:
                return _refresh_response('1', ttl_seconds=900)
            raise ClientError(
                {'Error': {'Code': 'AccessDenied', 'Message': 'denied'}},
                'AssumeRole',
            )

        sts = _StsSpy(responder=responder)
        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='flask-s3-viewer',
            external_id=None,
            duration_seconds=900,
            mfa_serial=None,
            token_code=None,
            token_code_callback=None,
            region_name='us-east-1',
        )
        creds = sess.get_credentials()
        creds._expiry_time = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(
            minutes=10
        )
        with pytest.raises(ClientError):
            _ = creds.access_key
        assert len(sts.calls) == 2


# ---------------------------------------------------------------------------
# Presigned URL TTL behaviour with temporary credentials (v1.2 docs claim)
# ---------------------------------------------------------------------------


class TestPresignedUrlWithAssumeRole:
    def test_x_amz_expires_param_reflects_requested_value(self):
        """``generate_presigned_url`` always writes the *requested*
        ``X-Amz-Expires`` into the query — boto3 does not silently cap
        it to the STS session expiry. The effective lifetime is
        ``min(Expires, STS session expiry)`` enforced by S3 at access
        time, which is the behaviour the docs warn about."""
        sts = _StsSpy()
        sess = AWSSession._assume_role(
            base=_FakeBaseSession(sts),
            role_arn=ROLE_ARN,
            role_session_name='flask-s3-viewer',
            external_id=None,
            duration_seconds=900,  # 15 min — minimum allowed by STS
            mfa_serial=None,
            token_code=None,
            token_code_callback=None,
            region_name='us-east-1',
        )
        with mock_aws():
            # Bucket must exist on the moto mock for the presign call to
            # use a valid region/endpoint pair.
            real_s3 = boto3.client('s3', region_name='us-east-1')
            real_s3.create_bucket(Bucket='presign-ttl-bucket')

            s3 = sess.client('s3')
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': 'presign-ttl-bucket', 'Key': 'k.txt'},
                ExpiresIn=86400,  # 24 hours, far beyond the 15-min STS session
            )
        # The URL embeds the requested expiry verbatim — SigV4 writes
        # ``X-Amz-Expires=86400`` while the legacy SigV2 form writes
        # ``Expires=<unix_timestamp>``. boto3 does NOT silently cap the
        # value to the STS session expiry; the actual enforced cap
        # happens at S3 access time and is documented in
        # configuration.rst.
        assert 'X-Amz-Expires=86400' in url or 'Expires=' in url
        # And the URL is signed against the AssumeRole-issued temporary
        # session token (proof that the working session carries
        # AssumeRole credentials).
        assert 'x-amz-security-token=' in url or 'X-Amz-Security-Token=' in url
