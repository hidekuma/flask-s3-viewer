import logging

from weakref import WeakValueDictionary
from collections import namedtuple

# from .aws.ref import Region
from .aws.s3 import AWSS3Client

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(asctime)s: %(message)s'
)

__version__ = "0.0.1"

__all__ = ['FlaskS3up']


FLASK_S3UP_NAMESPACE = 'flask_s3up'

class Singleton(type):

    _instances = WeakValueDictionary({})

    def __call__(cls, *args, **kwargs):
        # if 'region_name' not in kwargs:
            # kwargs['region_name'] = Region.SEOUL.value

        key = f'{kwargs["url_prefix"]}'

        if not cls._instances.get(key):
            i = super(Singleton, cls).__call__(*args, **kwargs)
            cls._instances[key] = i
            print('-'*150)
            logging.info(f"*** {i} Initialized ! ***")
            logging.info(f"*** Clients info ***")
            logging.info(f"{cls._instances.data}")
            logging.info(f"{cls._instances}")
            print('-'*150)
            return cls._instances[key]

class FlaskS3Up(AWSS3Client, metaclass=Singleton):
    FLASK_S3UP_BUCKET_CONFIGS = {}
    FLASK_S3UP_BUCKET = namedtuple(
        'FlaskS3UpBucketConfig',
        '''
        profile_name
        region_name
        endpoint_url
        bucket_name
        secret_key
        access_key
        cache_dir
        ttl
        use_cache
        object_hostname
        '''
    )
    def __init__(self, app, url_prefix=None, object_hostname=None, config=None):
        if config:
            self.init_app(app, url_prefix, object_hostname, config)

    def init_app(self, app, url_prefix=None, object_hostname=None, config=None):
        if object_hostname and object_hostname.endswith('/'):
            object_hostname = object_hostname[:-1]
        self.__object_hostname = object_hostname
        self.__url_prefix = url_prefix

        if config:
            # TODO: validation (type check)
            config.setdefault('secret_key', None)
            config.setdefault('access_key', None)
            super().__init__(**config)

        config['object_hostname'] = object_hostname
        self.FLASK_S3UP_BUCKET_CONFIGS[url_prefix] = self.FLASK_S3UP_BUCKET(**config)

    @property
    def object_hostname(self):
        return self.__object_hostname

    @property
    def url_prefix(self):
        return self.__url_prefix

    @classmethod
    def get_instance(cls, path=None):
        # print(cls._instances.data)
        return cls._instances[path]
