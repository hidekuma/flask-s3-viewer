import boto3
from botocore.errorfactory import ClientError
import logging

class AWSSession():
    """
    AWSSession (Boto3.Session) = Create AWS Session
    Document:
        https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
    Usage:
        AWSSession(profile_name=PROFILE_NAME, region_name=REGION_NAME)
    """

    def __init__(self, *, profile_name=None, region_name=None, secret_key=None, access_key=None):
        """
        :param profile_name: AWS profile, default: ~/.aws/credentials > {profile_name}
        :parma region_name: AWS region, default: ~/.aws/credentials/config > {profile_name}
        """
        self.runnable = False
        self.profile_name = profile_name
        self.region_name = region_name
        try:
            if not access_key or not secret_key:
                self._session = boto3.Session(
                    profile_name=profile_name,
                    region_name=region_name
                )
            else:
                self._session = boto3.Session(
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key,
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

    @property
    def session(self):
        return self._session
