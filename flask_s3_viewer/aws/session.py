from typing import Optional
import boto3
import logging

from boto3.session import Session
from botocore.errorfactory import ClientError


class AWSSession:

    def __init__(
        self,
        *,
        profile_name: Optional[str] = None,
        region_name: Optional[str] = None,
        secret_key: Optional[str] = None,
        access_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ):
        self.runnable = False
        self.profile_name = profile_name
        self.region_name = region_name
        try:
            if not access_key or not secret_key:
                self._session: Session = boto3.Session(
                    profile_name=profile_name,
                    region_name=region_name
                )
            else:
                self._session: Session = boto3.Session(
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
                    aws_session_token=session_token,
                    region_name=region_name
                )
        except ClientError as e:
            logging.error(e)
        except Exception as e:
            logging.error('Unexcepted error: %s' % str(e))
        else:
            self.runnable = True

    def __repr__(self):
        return '{0}(runnable={1}, profile_name={2}, boto3.Session={3})'.format(
            self.__class__.__name__,
            self.runnable,
            self.profile_name,
            repr(self._session)
        )
