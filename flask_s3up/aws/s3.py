import os
import re
import urllib
import collections
import mimetypes
import logging

from botocore.errorfactory import ClientError
from weakref import WeakValueDictionary
from functools import wraps

from .ref import Region
from .session import AWSSession
from .cache import AWSCache

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s: %(message)s')


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


class AWSS3Client(AWSSession, metaclass=Singleton):
    """
    Inheritance of AWSSession
    """

    def __init__(
        self,
        *,
        profile_name=None,
        region_name=None,
        endpoint_url=None,
        bucket_name=None,
        secret_key=None,
        access_key=None,
        cache_dir=None,
        ttl=None,
        use_cache=False
    ):
        super().__init__(
            profile_name=profile_name,
            region_name=region_name,
            secret_key=secret_key,
            access_key=access_key
        )

        if not self.runnable:
            raise ValueError('AWSSession is not available. check your credentials!')
        # self.location = {'LocationConstraint': self.region_name}
        self.region_name = region_name
        self.use_cache = use_cache
        self._bucket_name = bucket_name
        self._s3 = self.session.client(
            's3',
            region_name=self.region_name,
            endpoint_url=endpoint_url
        )
        if use_cache:
            self._cache = AWSCache(
                cache_dir=cache_dir,
                timeout=ttl
            )

    def __getattr__(self, name):
        if name == 'resource':
            value = self.session.resource('s3')
            setattr(self, name, value)
            return value

    # @property
    # def s3(self):
        # """
        # s3 getter
        # """
        # return self._s3

    def apply_bucket(define=None):
        def __wrapper(func):
            @wraps(func)
            def __decorartor(self, *args, **kwargs):
                bucket_name = kwargs.get('bucket_name', None)
                if define:
                    kwargs['bucket_name'] = define
                else:
                    if self._bucket_name or not bucket_name:
                        kwargs['bucket_name'] = self._bucket_name
                rtn = func(self, *args, **kwargs)
                return rtn
            return __decorartor
        return __wrapper



    def prefixer(self, prefix):
        if prefix:
            if prefix.startswith('/'):
                prefix = prefix[1:]
            if not prefix.endswith('/') and prefix != '':
                prefix += '/'
        return prefix

    def __trim(self, string):
        pattern = re.compile(r'\s+')
        return re.sub(pattern, '', string)

    def __get_bucket_name(self, bucket_name):
        if self._bucket_name or not bucket_name:
            return self._bucket_name
        return bucket_name

    def get_object(self, object_name, bucket_name=None):
        try:
            r = self._s3.get_object(
                Bucket=self.__get_bucket_name(bucket_name),
                Key=object_name
            )
        except ClientError as e:
            logging.info(e)
            return None
        else:
            return r


    def put_object(self, object_name, bucket_name=None, src_data=None, mkdir=False):
        bucket_name = self.__get_bucket_name(bucket_name)
        if isinstance(src_data, bytes):
            object_data = src_data
        elif isinstance(src_data, str):
            try:
                object_data = open(src_data, 'rb')
                # possible FileNotFoundError/IOError exception
            except Exception as e:
                logging.error(e)
                return False
        elif not src_data and mkdir:
            object_data = ''
        else:
            logging.error('Type of ' + str(type(src_data)) +
                          ' for the argument \'src_data\' is not supported.')
            return False

        # Put the object
        print('PUT_OBJECT:', object_name)
        try:
            put_source = {
                'Bucket': bucket_name,
                'Key': object_name,
                'Body': object_data
            }
            if not mkdir:
                try:
                    put_source['ContentType'] = object_data.headers.get('Content-Type')
                except AttributeError:
                    content_type = mimetypes.guess_type(object_name, True)[0]
                    put_source['ContentType'] = content_type

            self._s3.put_object(**put_source)
            if self.use_cache and mkdir:
                self._cache.remove(os.path.dirname(object_name[:-1]), division=bucket_name)
        except ClientError as e:
            # AllAccessDisabled error == bucket not found
            # NoSuchKey or InvalidRequest error == (dest bucket/obj == src bucket/obj)
            logging.error(e)
            return False
        finally:
            if isinstance(src_data, str):
                object_data.close()
        return True

    def upload_object(self, f, object_name, bucket_name=None, tagging=None):
        bucket_name = self.__get_bucket_name(bucket_name)
        if self.is_exists(object_name):
            raise Exception('Already exists')
        put_source = {
            'Bucket': bucket_name,
            'Key': object_name,
            'Body': f,
            'ContentType': f.headers.get('Content-Type')
        }
        if tagging:
            if isinstance(tagging, dict):
                tagging = urllib.parse.urlencode(tagging, quote_via=urllib.parse.quote_plus)
            put_source['Tagging'] = tagging
        print('UP_OBJECT:', object_name)
        try:
            self._s3.put_object(**put_source)
            if self.use_cache:
                self._cache.remove(os.path.dirname(object_name), division=bucket_name)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def copy_fileobj(self, copy_source, object_name, bucket_name=None):
        try:
            self._s3.copy_object(
                CopySource=copy_source,
                Bucket=self.__get_bucket_name(bucket_name),
                Key=object_name
            )
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_fileobj(self, object_name, bucket_name=None):
        try:
            bucket_name = self.__get_bucket_name(bucket_name)
            self._s3.delete_object(
                Bucket=bucket_name,
                Key=object_name
            )
        except ClientError as e:
            logging.error(e)
            return False
        else:
            if self.use_cache:
                self._cache.remove(
                    os.path.dirname(object_name),
                    division=bucket_name
                )
        return True

    def delete_fileobjs(self, object_names, bucket_name=None):
        try:
            bucket_name = self.__get_bucket_name(bucket_name)
            if object_names:
                prefixes = set()
                objects = []
                for obj in object_names:
                    if obj:
                        objects.append({'Key': obj})
                        if self.use_cache:
                            prefixes.add(os.path.dirname(obj))
                if objects:
                    self._s3.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': objects}
                    )
                if prefixes:
                    for prefix in prefixes:
                        self._cache.remove(prefix, division=bucket_name)
                # print('2-DELETE', bucket_name, prefixes)

        except ClientError as e:
            logging.error(e)
            return False
        return True

    @apply_bucket()
    def list_objects(
        self,
        prefix='',
        delimiter='/',
        max_items=1000,
        page_size=1000,
        bucket_name=None,
        starting_token=None,
        search=None,
        apply_cache=True
    ):
        prefix = self.prefixer(prefix)
        def run(wrap=False):
            nonlocal bucket_name, prefix, delimiter, max_items, page_size, starting_token, search
            paginator = self._s3.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=bucket_name,
                Prefix=prefix,
                Delimiter=delimiter,
                PaginationConfig={
                    'MaxItems': max_items,
                    'PageSize': page_size,
                    'StartingToken': starting_token
                }
            )
            next_token = page_iterator.build_full_result().get('NextToken', None)
            if search:
                # generator
                contents = page_iterator.search(
                    f'Contents[?Size > `0` && contains(Key, `"{search}"`)]'
                )
                prefixes = page_iterator.search(
                    f'CommonPrefixes[?contains(Prefix, `"{search}"`)]'
                )
            else:
                # TODO: search
                # generator
                if delimiter == '':
                    contents = page_iterator.search('Contents')
                else:
                    contents = page_iterator.search('Contents[?Size > `0`]')
                prefixes = page_iterator.search('CommonPrefixes')
            return list(prefixes), list(contents), next_token

        if self.use_cache and apply_cache:
            salt = self._cache.make_hash(
                f"{delimiter}|{starting_token}|{search}|{max_items}|{page_size}"
            )
            data = self._cache.get(
                prefix,
                salt=salt,
                division=bucket_name
            )
            if not data:
                logging.info('NOT CACHED.')
                data = run(True)
                self._cache.set(
                    prefix,
                    data,
                    salt=salt,
                    division=bucket_name
                )
        else:
            data = run()

        return data

    def delete_objects(self, object_names, bucket_name=None):
        bucket_name = self.__get_bucket_name(bucket_name)
        if isinstance(object_names, str):
            if object_names.endswith('/'):
                if object_names != '/':
                    # if == '' will deleted all
                    self.delete_fileobjs(
                        self.get_all_of_objects(
                            object_names
                        )
                    )
                    if self.use_cache:
                        self._cache.remove(
                            os.path.dirname(object_names[:-1]),
                            division=bucket_name
                        )
                else:
                    raise ValueError('object_names can\'t be ""')
            else:
                self.delete_fileobj(
                    object_names
                )
        elif isinstance(object_names, collections.Iterable):
            self.delete_fileobjs(
                object_names
            )

    def get_all_of_objects(self, prefix, bucket_name=None):
        next_token=None
        bucket_name = self.__get_bucket_name(bucket_name)
        while True:
            prefixes, contents, next_token = self.list_objects(
                prefix=prefix,
                delimiter='',
                starting_token=next_token,
                apply_cache=False
            )
            for p in prefixes:
                if p:
                    yield p

            for item in contents:
                if item:
                    yield item['Key']
            if not next_token:
                break

    def download_fileobj(self, file_name, object_name, bucket_name=None):
        try:
            bucket_name = self.__get_bucket_name(bucket_name)
            with open(file_name, 'wb') as f:
                self._s3.download_fileobj(bucket_name, object_name, f)
        except ClientError as e:
            logging.info(e)
            return False
        else:
            return True

    def is_exists(self, object_name=None, bucket_name=None):
        try:
            bucket_name = self.__get_bucket_name(bucket_name)
            if object_name:
                self._s3.head_object(
                    Bucket=bucket_name,
                    Key=object_name
                )
            else:
                self._s3.head_object(
                    Bucket=bucket_name
                )
        except ClientError as e:
            logging.info(e)
            return False
        else:
            return True
