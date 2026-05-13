"""Thin wrapper around ``boto3.Session`` that adds explicit AssumeRole
(STS) and MFA support.

What works out-of-the-box via boto3's default credential chain (no code
change needed):

  - Static access_key / secret_key / session_token
  - Named profile (including profiles that already declare role_arn +
    source_profile in ``~/.aws/config`` — boto3 handles AssumeRole)
  - AWS_* environment variables
  - EC2 IMDS / ECS task role / AWS SSO cache / EKS IRSA (Web Identity
    OIDC) — all resolved by boto3 automatically when nothing else is set.

What this class adds:

  - **Explicit AssumeRole**: passing ``role_arn`` triggers an STS
    AssumeRole call against a base session (built from the same
    profile/keys options), and the returned temporary credentials are
    used to construct the working session.
  - **Cross-account** ``external_id`` (required by some target accounts).
  - **MFA**: pass ``mfa_serial`` together with a ``token_code`` (or a
    ``token_code_callback`` callable that returns one on demand).
  - **Tunable** ``role_session_name`` and ``duration_seconds``.
"""
import logging
from collections.abc import Callable

import boto3
from boto3.session import Session
from botocore.errorfactory import ClientError


class AWSSession:

    _session: Session

    def __init__(
        self,
        *,
        profile_name: str | None = None,
        region_name: str | None = None,
        secret_key: str | None = None,
        access_key: str | None = None,
        session_token: str | None = None,
        role_arn: str | None = None,
        role_session_name: str | None = None,
        external_id: str | None = None,
        duration_seconds: int | None = None,
        mfa_serial: str | None = None,
        token_code: str | None = None,
        token_code_callback: Callable[[], str] | None = None,
    ) -> None:
        self.runnable: bool = False
        self.profile_name: str | None = profile_name
        self.region_name: str | None = region_name
        try:
            base = self._build_base_session(
                profile_name=profile_name,
                region_name=region_name,
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
            )
            if role_arn:
                self._session = self._assume_role(
                    base=base,
                    role_arn=role_arn,
                    role_session_name=role_session_name or 'flask-s3-viewer',
                    external_id=external_id,
                    duration_seconds=duration_seconds,
                    mfa_serial=mfa_serial,
                    token_code=token_code,
                    token_code_callback=token_code_callback,
                    region_name=region_name,
                )
            else:
                self._session = base
        except ClientError as e:
            logging.error(e)
        except Exception as e:
            logging.error('Unexpected error: %s', e)
        else:
            self.runnable = True

    @staticmethod
    def _build_base_session(
        *,
        profile_name: str | None,
        region_name: str | None,
        access_key: str | None,
        secret_key: str | None,
        session_token: str | None,
    ) -> Session:
        """The session boto3 uses *before* any explicit STS AssumeRole.

        If access/secret are not provided we fall through to the default
        credential chain (env vars, profile, IMDS, IRSA, SSO cache, …),
        so the deployer can mix-and-match: e.g. EKS pod IRSA → assume a
        cross-account role declared via ``role_arn``.
        """
        if not access_key or not secret_key:
            return boto3.Session(
                profile_name=profile_name,
                region_name=region_name,
            )
        return boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            region_name=region_name,
        )

    @staticmethod
    def _assume_role(
        *,
        base: Session,
        role_arn: str,
        role_session_name: str,
        external_id: str | None,
        duration_seconds: int | None,
        mfa_serial: str | None,
        token_code: str | None,
        token_code_callback: Callable[[], str] | None,
        region_name: str | None,
    ) -> Session:
        """Run STS AssumeRole on top of ``base`` and return a fresh
        ``boto3.Session`` bound to the temporary credentials.
        """
        sts = base.client('sts')
        kwargs: dict = {
            'RoleArn': role_arn,
            'RoleSessionName': role_session_name,
        }
        if external_id:
            kwargs['ExternalId'] = external_id
        if duration_seconds:
            kwargs['DurationSeconds'] = duration_seconds
        if mfa_serial:
            kwargs['SerialNumber'] = mfa_serial
            code = token_code or (token_code_callback() if token_code_callback else None)
            if not code:
                raise ValueError(
                    'mfa_serial requires either token_code or token_code_callback.'
                )
            kwargs['TokenCode'] = code
        resp = sts.assume_role(**kwargs)
        creds = resp['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=region_name,
        )

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}('
            f'runnable={self.runnable}, '
            f'profile_name={self.profile_name}, '
            f'boto3.Session={self._session!r})'
        )
