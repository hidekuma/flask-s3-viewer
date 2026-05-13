import logging

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
    ) -> None:
        self.runnable: bool = False
        self.profile_name: str | None = profile_name
        self.region_name: str | None = region_name
        try:
            if not access_key or not secret_key:
                self._session = boto3.Session(
                    profile_name=profile_name,
                    region_name=region_name,
                )
            else:
                self._session = boto3.Session(
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    aws_session_token=session_token,
                    region_name=region_name,
                )
        except ClientError as e:
            logging.error(e)
        except Exception as e:
            logging.error('Unexpected error: %s', e)
        else:
            self.runnable = True

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(runnable={self.runnable}, profile_name={self.profile_name}, boto3.Session={repr(self._session)})'
