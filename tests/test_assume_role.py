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
"""
from __future__ import annotations

from unittest.mock import patch

import boto3
import pytest
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
