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
  - **Automatic refresh of AssumeRole temporary credentials** via
    botocore ``RefreshableCredentials`` — long-running viewers no
    longer hit ``ExpiredToken`` once ``DurationSeconds`` elapses.
    Activated whenever ``role_arn`` is set *and* either MFA is not
    used or a ``token_code_callback`` is supplied. The static
    ``mfa_serial`` + literal ``token_code`` combination keeps the
    legacy single-shot behavior for backward compatibility.

.. note::
    The refresh path depends on the botocore private attribute
    ``BotocoreSession._credentials`` because ``set_credentials`` only
    accepts a static 3-tuple and rejects ``RefreshableCredentials``
    instances. This is the pattern recommended by AWS-internal
    boto3 examples; if botocore changes the surface, the import or
    assignment will fail loudly at construction time rather than
    silently degrade.
"""
import logging
from collections.abc import Callable

import boto3
from boto3.session import Session
from botocore.credentials import RefreshableCredentials
from botocore.errorfactory import ClientError
from botocore.session import Session as BotocoreSession

logger = logging.getLogger(__name__)


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
            logger.error(e)
        except Exception as e:
            logger.error('Unexpected error: %s', e)
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

        Two branches share a single entry point:

        - **Refresh-eligible** (``role_arn`` + MFA absent OR
          ``token_code_callback`` present): delegate to
          ``_assume_role_refreshable`` — boto3 will auto-refresh
          credentials via botocore ``RefreshableCredentials``.
        - **Static** (``mfa_serial`` + literal ``token_code`` and no
          callback): keep the legacy single-shot behavior so existing
          short-lived MFA workflows continue to function identically.
          ``ExpiredToken`` after ``DurationSeconds`` is the same
          surface as before.
        """
        # MFA with a literal token_code (and no callback) cannot refresh
        # — once the OTP is consumed there is no way to obtain the next
        # one without prompting the user again. Preserve the legacy
        # single-shot path for backward compatibility.
        refresh_eligible = not (mfa_serial and token_code and token_code_callback is None)
        if refresh_eligible:
            return AWSSession._assume_role_refreshable(
                base=base,
                role_arn=role_arn,
                role_session_name=role_session_name,
                external_id=external_id,
                duration_seconds=duration_seconds,
                mfa_serial=mfa_serial,
                token_code=token_code,
                token_code_callback=token_code_callback,
                region_name=region_name,
            )
        return AWSSession._assume_role_static(
            base=base,
            role_arn=role_arn,
            role_session_name=role_session_name,
            external_id=external_id,
            duration_seconds=duration_seconds,
            mfa_serial=mfa_serial,
            token_code=token_code,
            token_code_callback=token_code_callback,
            region_name=region_name,
        )

    @staticmethod
    def _assume_role_static(
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
        """Legacy single-shot AssumeRole path — no refresh.

        Used only when ``mfa_serial`` + literal ``token_code`` is
        supplied without a callback, since the consumed OTP cannot be
        replayed for refresh.
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

    @staticmethod
    def _assume_role_refreshable(
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
        """AssumeRole with automatic refresh via ``RefreshableCredentials``.

        The closure ``_refresh`` is invoked once synchronously here (to
        seed initial credentials) and then re-invoked by botocore each
        time the cached credentials approach expiry. botocore's
        ``RefreshableCredentials`` defaults are:

          - advisory window: **15 minutes** (``_advisory_refresh_timeout
            = 900``) — best-effort background refresh.
          - mandatory window: **10 minutes** (``_mandatory_refresh_timeout
            = 600``) — synchronous refresh, the API call blocks until
            credentials are renewed.

        On the MFA + callback path, the callback runs again on every
        refresh — supplying a fresh OTP transparently to boto3.
        """
        # Reuse a single STS client across refreshes — the parent
        # ``base`` session's credentials are assumed to be long-lived
        # (IAM user, IRSA web-identity, IMDS role, …) and outlive any
        # individual AssumeRole result.
        sts = base.client('sts')
        base_kwargs: dict = {
            'RoleArn': role_arn,
            'RoleSessionName': role_session_name,
        }
        if external_id:
            base_kwargs['ExternalId'] = external_id
        if duration_seconds:
            base_kwargs['DurationSeconds'] = duration_seconds

        def _refresh() -> dict:
            kwargs = dict(base_kwargs)
            if mfa_serial:
                code = token_code or (
                    token_code_callback() if token_code_callback else None
                )
                if not code:
                    raise ValueError(
                        'mfa_serial requires either token_code or token_code_callback.'
                    )
                kwargs['SerialNumber'] = mfa_serial
                kwargs['TokenCode'] = code
            try:
                resp = sts.assume_role(**kwargs)
            except ClientError as e:
                # Re-raise so boto3 surfaces the failure on the next
                # AWS API call; logging here gives operators a single
                # breadcrumb tying the failure to the refresh path.
                logger.error('AssumeRole refresh failed: %s', e)
                raise
            creds = resp['Credentials']
            return {
                'access_key': creds['AccessKeyId'],
                'secret_key': creds['SecretAccessKey'],
                'token': creds['SessionToken'],
                # ``Expiration`` is a timezone-aware datetime from boto3
                # / moto; ``isoformat()`` yields the RFC 3339-compatible
                # string ``RefreshableCredentials`` expects.
                'expiry_time': creds['Expiration'].isoformat(),
            }

        rc = RefreshableCredentials.create_from_metadata(
            metadata=_refresh(),
            refresh_using=_refresh,
            method='sts-assume-role',
        )
        bsess = BotocoreSession()
        # ``set_credentials`` on the botocore session only accepts a
        # static (access_key, secret_key, token) triple and would
        # collapse the ``RefreshableCredentials`` instance to a plain
        # ``Credentials`` snapshot. Direct assignment to the private
        # ``_credentials`` slot is the pattern AWS-published boto3
        # examples use to keep the refresh wiring intact.
        bsess._credentials = rc
        if region_name:
            # ``boto3.Session(botocore_session=..., region_name=...)``
            # configures the region on the wrapper, but the underlying
            # botocore session also needs the variable set so any
            # client that defers to the botocore session sees the
            # same region.
            bsess.set_config_variable('region', region_name)
        return boto3.Session(botocore_session=bsess, region_name=region_name)

    def __repr__(self) -> str:
        return (
            f'{self.__class__.__name__}('
            f'runnable={self.runnable}, '
            f'profile_name={self.profile_name}, '
            f'boto3.Session={self._session!r})'
        )
