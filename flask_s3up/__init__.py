import logging

# from weakref import WeakValueDictionary
from collections import namedtuple

from .aws.s3 import AWSS3Client
from .errors import (
    NotConfiguredCacheDir,
    NotSupportUploadType
)
from .config import (
    NAMESPACE,
    FIXED_TEMPLATE_FOLDER,
    UPLOAD_TYPES
)

APP_TEMPLATE_FOLDER = FIXED_TEMPLATE_FOLDER

__version__ = "0.0.15"


class Singleton(type):

    # _instances = WeakValueDictionary({})
    _instances = {}

    def __call__(cls, *args, **kwargs):
        key = kwargs["namespace"]

        if not cls._instances.get(key):
            i = super(Singleton, cls).__call__(*args, **kwargs)
            cls._instances[key] = i
            logging.info(f"*** {i} Initialized ! ***")
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
    template_namespace = NAMESPACE

    def __init__(
        self,
        app,
        namespace=None,
        object_hostname=None,
        allowed_extensions=None,
        template_namespace='base',
        upload_type='default',
        config=None
    ):
        """
        :param Flask.app app: Required
        :param str namespace: Unique namespace of Flask S3Up
        :param url object_hostname: Hostname, e.g. Cloudfront endpoint
        :param set allowed_extensions: e.g. {'jpg', 'png'}
        :param str template_namespace: Template name
        :param str upload_type: Upload type
        :param dict config: Bucket configs
        """
        self.app = app
        if object_hostname and object_hostname.endswith('/'):
            object_hostname = object_hostname[:-1]
        self.object_hostname = object_hostname
        self.allowed_extensions =  allowed_extensions
        self.template_namespace = template_namespace
        if upload_type not in UPLOAD_TYPES:
            raise NotSupportUploadType
        self.upload_type = upload_type
        self.__max_pages = 10
        self.__max_items = 100

        if config:
            # bucket_name, profile_name is required
            config.setdefault('region_name', None)
            config.setdefault('endpoint_url', None)
            config.setdefault('secret_key', None)
            config.setdefault('access_key', None)
            if config.get('use_cache'):
                if not config.get('cache_dir'):
                    raise NotConfiguredCacheDir
            config.setdefault('cache_dir', None)
            config.setdefault('ttl', 300)
            config.setdefault('use_cache', None)
            super().__init__(**config)

        self.FLASK_S3UP_BUCKET_CONFIGS[namespace] = self.FLASK_S3UP_BUCKET(
            **config
        )

    @property
    def max_pages(self):
        return self.__max_pages

    @property
    def max_items(self):
        return self.__max_items

    @classmethod
    def get_instance(cls, namespace=None):
        """
        Return a Flask S3Up instance.

        :param str namespace: namespace

        Return:
            :class:`FlaskS3Up`
        """
        # print(cls._instances.data, namespace)
        return cls._instances[namespace]

    @classmethod
    def get_boto_client(cls, namespace=None):
        """
        Return a Boto3's S3 client.

        :param str namespace: namespace

        Return:
            boto3's S3 client.
        """
        return cls._instances[namespace]._s3

    @classmethod
    def get_boto_session(cls, namespace=None):
        """
        Return a Boto3's Sesson.

        :param str namespace: namespace

        Return:
            boto3's Session.
        """
        return cls._instances[namespace]._session

    def add_new_one(
        self,
        namespace=None,
        object_hostname=None,
        allowed_extensions=None,
        template_namespace='base',
        upload_type='default',
        config=None
    ):
        """
        Initialize another bucket

        :param str namespace: Unique namespace of Flask S3Up
        :param url object_hostname: Hostname, e.g. Cloudfront endpoint
        :param set allowed_extensions: e.g. {'jpg', 'png'}
        :param str template_namespace: Template name
        :param str upload_type: Upload type
        :param dict config: Bucket configs

        Return:
            :class:`FlaskS3Up`
        """
        return FlaskS3Up(
            self.app,
            namespace=namespace,
            object_hostname=object_hostname,
            allowed_extensions=allowed_extensions,
            template_namespace=template_namespace,
            upload_type=upload_type,
            config=config
        )

    def register(self, template_folder=None):
        """
        Register FlaskS3Up to Flask's blueprint.

        :param path template_folder: FIXME

        .. warning::

            `template_folder` is Not ready yet. DON'T USE THIS PARAM.
        """
        if template_folder:
            # FIXME: 하나에만 적용불가..
            raise ValueError('not ready')
            global APP_TEMPLATE_FOLDER
            APP_TEMPLATE_FOLDER = template_folder
        # Dynamic import (have to)
        from .routers import FlaskS3UpViewRouter
        self.app.register_blueprint(FlaskS3UpViewRouter)
        logging.info(f"*** registerd FlaskS3Up blueprint! ***")
        logging.info(self.app.url_map)
