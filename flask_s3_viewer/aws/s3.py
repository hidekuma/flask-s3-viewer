import os
import re
import urllib
import collections
import mimetypes
import logging

from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.errorfactory import ClientError
from functools import wraps

from .session import AWSSession
from .cache import AWSCache

class AWSS3Client(AWSSession):
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
            raise ValueError('AWSSession is not available. check your credentials.')
        # self.location = {'LocationConstraint': self.region_name}
        self.region_name = region_name
        self.use_cache = use_cache
        self._bucket_name = bucket_name
        self._s3 = self._session.client(
            's3',
            region_name=self.region_name,
            endpoint_url=endpoint_url,
            config=Config(signature_version='s3v4')
        )
        if use_cache:
            self._cache = AWSCache(
                cache_dir=cache_dir,
                timeout=ttl
            )

    def bucket(bucket_name=None):
        def __wrapper(func):
            @wraps(func)
            def __decorartor(self, *args, **kwargs):
                kwargs_bucket_name = kwargs.get('bucket_name', None)
                if bucket_name:
                    kwargs['bucket_name'] = bucket_name
                else:
                    if self._bucket_name or not kwargs_bucket_name:
                        kwargs['bucket_name'] = self._bucket_name
                return func(self, *args, **kwargs)
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

    @bucket()
    def find_one(self, object_name, bucket_name=None):
        try:
            r = self._s3.get_object(
                Bucket=bucket_name,
                Key=object_name
            )
        except ClientError as e:
            logging.error(e)
            return None
        else:
            return r

    @bucket()
    def purge(self, object_name, bucket_name=None):
        if self.use_cache:
            logging.debug('PURGE:', object_name)
            self._cache.remove(os.path.dirname(object_name[:-1]), division=bucket_name)

    @bucket()
    def put_one(self, object_name, bucket_name=None, src_data=None, mkdir=False):
        if isinstance(src_data, bytes):
            object_data = src_data
        elif isinstance(src_data, str):
            try:
                object_data = open(src_data, 'rb')
            except Exception as e:
                logging.error(e)
                return False
        elif not src_data and mkdir:
            object_data = ''
        else:
            logging.error('Type of ' + str(type(src_data)) +
                          ' for the argument \'src_data\' is not supported.')
            return False

        logging.debug('PUT_OBJECT:', object_name)
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

    @bucket()
    def post_presign(self, object_name, bucket_name=None, tagging=None):
        try:
            content_type = mimetypes.guess_type(object_name)
            r = self._s3.generate_presigned_post(
                bucket_name,
                object_name,
                Fields={
                    "Content-Type": content_type[0]
                },
                Conditions=[
                    {"Content-Type": content_type[0]}
                ],
                ExpiresIn=600
            )
            return r
        except ClientError as e:
            logging.error(e)
            raise

    @bucket()
    def add_one(self, f, object_name, bucket_name=None, tagging=None):
        logging.debug('UP_OBJECT:', object_name)
        try:
            GB = 1024 ** 3
            config = TransferConfig(
                multipart_threshold=5 * GB
            )

            self._s3.upload_fileobj(
                f,
                bucket_name,
                object_name,
                ExtraArgs={
                    'ContentType': f.headers.get('Content-Type')
                },
                Config=config
            )

            if tagging:
                if isinstance(tagging, dict):
                    tagging = urllib.parse.urlencode(tagging, quote_via=urllib.parse.quote_plus)
                self._s3.put_object_tagging(
                    Bucket=bucket_name,
                    Key=object_name,
                    Tagging=tagging
                )
            if self.use_cache:
                self._cache.remove(os.path.dirname(object_name), division=bucket_name)
        except ClientError as e:
            logging.error(e)
            raise

    @bucket()
    def remove_one(self, object_name, bucket_name=None):
        try:
            self._s3.delete_object(
                Bucket=bucket_name,
                Key=object_name
            )
        except ClientError as e:
            logging.error(e)
            raise
        else:
            if self.use_cache:
                self._cache.remove(
                    os.path.dirname(object_name),
                    division=bucket_name
                )

    @bucket()
    def remove_all(self, object_names, bucket_name=None):
        try:
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

        except ClientError as e:
            logging.error(e)
            raise

    @bucket()
    def find(
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
                logging.debug('NOT CACHED.')
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

    @bucket()
    def remove(self, object_names, bucket_name=None):
        if isinstance(object_names, str):
            if object_names.endswith('/'):
                if object_names != '/':
                    # if == '' will deleted all
                    self.remove_all(
                        self.find_all(
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
                self.remove_one(
                    object_names
                )
        elif isinstance(object_names, collections.Iterable):
            self.remove_all(
                object_names
            )

    @bucket()
    def find_all(self, prefix, bucket_name=None):
        next_token=None
        while True:
            prefixes, contents, next_token = self.find(
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

    @bucket()
    def download_one(self, file_name, object_name, bucket_name=None):
        try:
            with open(file_name, 'wb') as f:
                self._s3.download_fileobj(bucket_name, object_name, f)
        except ClientError as e:
            logging.info(e)
            raise

    @bucket()
    def is_exists(self, object_name=None, bucket_name=None):
        try:
            if object_name:
                self._s3.head_object(
                    Bucket=bucket_name,
                    Key=object_name
                )
            else:
                self._s3.head_object(
                    Bucket=bucket_name
                )
        except ClientError:
            return False
        else:
            return True
