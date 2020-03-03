import logging

from flask import current_app, Blueprint
from weakref import WeakValueDictionary

from .aws.ref import Region
from .aws.s3 import AWSS3Client

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s: %(message)s')

__version__ = "0.0.1"

__all__ = ['FlaskS3up']

class Singleton(type):

    _instances = WeakValueDictionary({})

    def __call__(cls, *args, **kwargs):
        if 'region_name' not in kwargs:
            kwargs['region_name'] = Region.SEOUL.value

        key = f'{kwargs["profile_name"]}/{kwargs["region_name"]}'

        if not cls._instances.get(key):
            i = super(Singleton, cls).__call__(*args, **kwargs)
            cls._instances[key] = i
            print('-'*150)
            logging.info(f"*** {i} Initialized ! ***")
            logging.info(f"*** Clients info ***")
            # logging.info(f"{cls._instances.data}")
            logging.info(f"{cls._instances}")
            print('-'*150)
        return cls._instances[key]

class FlaskS3Up():
    def __init__(self, app=None, config=None):
        if app:
            self.init_app(app, config)

    def __call__(self):
        print('called')

    def init_app(self, app, config=None):
        self.__app = app
        if config:
            app.config.update(config)
        app.config.setdefault('S3UP_SERVICE_POINT', None)
        app.config.setdefault('S3UP_IS_COMPATIBLE', False)
        app.config.setdefault('S3UP_OBJECT_HOSTNAME', '/')
        app.config.setdefault('S3UP_USE_CACHING', False)
        app.config.setdefault('S3UP_CACHE_DIR', None)
        app.config.setdefault('S3UP_TTL', 300)

        object_hostname = app.config['S3UP_OBJECT_HOSTNAME']

        if object_hostname:
            if object_hostname.endswith('/'):
                app.config['S3UP_OBJECT_HOSTNAME'] = object_hostname[:-1]

        if app.config['S3UP_USE_CACHING'] and not app.config['S3UP_CACHE_DIR']:
            raise ValueError('have to set "S3UP_CACHE_DIR".')

        if app.config['S3UP_IS_COMPATIBLE'] and not app.config['S3UP_SERVICE_POINT']:
            raise ValueError('have to set "S3UP_SERVICE_POINT".')


    # def init_blueprint(self):
        # self.__app.register_blueprint(blueprint, url_prefix='/flask-s3up')

def get_s3_client():
    return AWSS3Client(
        profile_name=current_app.config['S3UP_PROFILE'],
        endpoint_url=current_app.config['S3UP_SERVICE_POINT'],
        use_cache=current_app.config['S3UP_USE_CACHING'],
        bucket_name=current_app.config['S3UP_BUCKET'],
        cache_dir=current_app.config['S3UP_CACHE_DIR'],
        ttl=current_app.config['S3UP_TTL'],
    )

FLASK_S3UP_BUCKET_PATH_CONFIGS = {
    'flask_s3up': 'hwjeongtest'
}

NAMESPACE = 'flask_s3up'
blueprint = Blueprint(
    NAMESPACE,
    __name__,
    template_folder=f'./blueprints/{NAMESPACE}/templates/{NAMESPACE}',
    static_folder='static',
)
