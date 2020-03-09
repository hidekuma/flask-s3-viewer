import logging

# from weakref import WeakValueDictionary
from collections import namedtuple

# from .aws.ref import Region
from .aws.s3 import AWSS3Client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s: %(message)s')

__version__ = "0.0.1"

__all__ = ['FlaskS3up']

FLASK_S3UP_BUCKET_CONFIGS = {}
FLASK_S3UP_BUCKET = namedtuple(
    'FlaskS3UpBucket',
    'bucket profile is_compatible service_point object_hostname use_cache region ttl cache_dir'
)

FLASK_S3UP_NAMESPACE = 'flask_s3up'

# class Singleton(type):

    # _instances = WeakValueDictionary({})

    # def __call__(cls, *args, **kwargs):
        # if 'region_name' not in kwargs:
            # kwargs['region_name'] = Region.SEOUL.value

        # key = f'{kwargs["profile_name"]}/{kwargs["region_name"]}'

        # if not cls._instances.get(key):
            # i = super(Singleton, cls).__call__(*args, **kwargs)
            # cls._instances[key] = i
            # print('-'*150)
            # logging.info(f"*** {i} Initialized ! ***")
            # logging.info(f"*** Clients info ***")
            # # logging.info(f"{cls._instances.data}")
            # logging.info(f"{cls._instances}")
            # print('-'*150)
            # return cls._instances[key]

class FlaskS3Up():
    def __init__(self, app=None, config=None):
        if app:
            self.init_app(app, config)

    def init_app(self, app, config=None):
        self.__app = app
        if config:
            app.config.update(config)
        app.config.setdefault('S3UP_USE_CACHING', False)
        app.config.setdefault('S3UP_CACHE_DIR', None)
        app.config.setdefault('S3UP_TTL', 300)

        bucket_configs = config.get('S3UP_BUCKET_CONFIGS', None)

        if bucket_configs:
            for k, v in bucket_configs.items():
                object_hostname = bucket_configs[k].get('object_hostname', None)
                if object_hostname:
                    if object_hostname.endswith('/'):
                        bucket_configs[k]['object_hostname'] = object_hostname[:-1]
                FLASK_S3UP_BUCKET_CONFIGS[k] = FLASK_S3UP_BUCKET(**v)

        if app.config['S3UP_USE_CACHING'] and not app.config['S3UP_CACHE_DIR']:
            raise ValueError('have to set "S3UP_CACHE_DIR".')

    @staticmethod
    def get_s3_client(path=None):
        #TODO: configs default and customs
        config = FLASK_S3UP_BUCKET_CONFIGS[path]

        return AWSS3Client(
            profile_name=getattr(config, 'profile'),
            endpoint_url=getattr(config, 'service_point'),
            use_cache=getattr(config, 'use_cache'),
            bucket_name=getattr(config, 'bucket'),
            cache_dir=getattr(config, 'cache_dir'),
            ttl=getattr(config, 'ttl')
        )
