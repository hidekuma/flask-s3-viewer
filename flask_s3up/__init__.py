import logging

# from weakref import WeakValueDictionary
from collections import namedtuple

# from .aws.ref import Region
from .aws.s3 import AWSS3Client


__version__ = "0.0.1"

__all__ = ['FlaskS3up']


FLASK_S3UP_NAMESPACE = 'flask_s3up'

class Singleton(type):

    # _instances = WeakValueDictionary({})
    _instances = {}

    def __call__(cls, *args, **kwargs):
        key = kwargs["namespace"]

        if not cls._instances.get(key):
            i = super(Singleton, cls).__call__(*args, **kwargs)
            cls._instances[key] = i
            print('-'*150)
            logging.info(f"*** {i} Initialized ! ***")
            # logging.info(f"*** Clients info ***")
            # logging.info(f"{cls._instances.data}")
            # logging.info(f"{cls._instances}")
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
        '''
    )
    def __init__(self, app, namespace=None, object_hostname=None, config=None):
        if not self.app:
            self.app = app
        if object_hostname and object_hostname.endswith('/'):
            object_hostname = object_hostname[:-1]
        self.object_hostname = object_hostname
        self.__max_pages = 10
        self.__max_items = 100

        if config:
            # TODO: validation (type check)
            config.setdefault('secret_key', None)
            config.setdefault('access_key', None)
            super().__init__(**config)

        self.FLASK_S3UP_BUCKET_CONFIGS[namespace] = self.FLASK_S3UP_BUCKET(**config)

    @property
    def max_pages(self):
        return self.__max_pages

    @property
    def max_items(self):
        return self.__max_items

    @classmethod
    def get_instance(cls, path=None):
        # print(cls._instances.data, path)
        return cls._instances[path]

    def add_new_one(self, namespace=None, object_hostname=None, config=None):
        return FlaskS3Up(
            self.app,
            namespace=namespace,
            object_hostname=object_hostname,
            config=config
        )

    def register(self):
        # dynamic import
        from .routers import FlaskS3UpViewRouter
        self.app.register_blueprint(FlaskS3UpViewRouter)

