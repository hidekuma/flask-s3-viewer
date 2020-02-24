import re
import urllib
import mimetypes
import logging

from botocore.errorfactory import ClientError

from .ref import Region
from .session import AWSSession
from .cache import AWSCache

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s: %(message)s')


class Singleton(type):
    """
    Singleton Design: Create regional instances

    Flow:
        1) Check region_name
        2) Create WeakValueDictionary
            - To solve a memory leak
    Return:
        Singleton Regional instance, Default region = Seoul(ap-northeast-2)
    """
    _instances = {}

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
    """AWSS3Client
    Inheritance of AWSSession
    """

    def __init__(
        self,
        *,
        profile_name=None,
        region_name=None,
        endpoint_url=None,
        secret_key=None,
        access_key=None,
        cache_dir=None,
        use_cache=False
    ):
        """
        :param profile_name:
        :param region_name:
        :param endpoint_url: for s3 compatible storage (Ceph)
        :param _s3: **protected
        """
        super().__init__(profile_name=profile_name, region_name=region_name, secret_key=secret_key, access_key=access_key)
        if not self.runnable:
            logging.error(
                'AWSSession is not available. check your credentials!')
            raise ValueError(
                'AWSSession is not available. check your credentials!')
        self.region_name = region_name
        self.location = {'LocationConstraint': self.region_name}
        self._ACL = 'private'
        self._s3 = self.session.client(
            's3',
            region_name=self.region_name,
            endpoint_url=endpoint_url
        )
        if use_cache:
            self.cache = AWSCache(temp_dir=cache_dir)

    def __getattr__(self, name):
        if name == 'resource':
            value = self.session.resource('s3')
            setattr(self, name, value)
            return value

    @property
    def s3(self):
        """
        s3 getter
        """
        return self._s3

    """ UTILS """
    def __prefixer(self, prefix):
        """
        for list_objects_v2
        :param prefix:
        """
        if prefix.startswith('/'):
            prefix = prefix[1:]
        if not prefix.endswith('/') and prefix != '':
            prefix += '/'
        return prefix

    def __trim(self, string):
        pattern = re.compile(r'\s+')
        return re.sub(pattern, '', string)

    # def __allowed_file(self, file_name):
        # return '.' in file_name and \
        # file_name.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    """ FUNCTIONS """
    def get_object(self, bucket_name, object_name):
        try:
            r = self._s3.get_object(
                Bucket=bucket_name,
                Key=object_name
            )
        except ClientError as e:
            logging.info(e)
            return False, None
        else:
            return True, r


    def put_object(self, bucket_name, object_name, src_data=None, mkdir=False):
        """
        Add an object to an Amazon S3 bucket
        The src_data argument must be of type bytes or a string that references
        a file specification.

        :param bucket_name:
        :param object_name:
        :param src_data:
        :param mkdir:

        Return:
            Bool()
        """

        # Construct Body= parameter
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
        try:
            put_source = {
                'Bucket': bucket_name,
                # 'ACL': self._ACL,
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
            # print('-'*100)
            # from pprint import pprint
            # tagging = self._s3.get_object_tagging(Bucket=bucket_name, Key=object_name)
            # pprint(tagging)
            # print('-'*100)
        except ClientError as e:
            # AllAccessDisabled error == bucket not found
            # NoSuchKey or InvalidRequest error == (dest bucket/obj == src bucket/obj)
            logging.error(e)
            return False
        finally:
            if isinstance(src_data, str):
                object_data.close()
        return True

    def upload_fileobj(self, bucket_name, f, object_name, tagging=None):
        put_source = {
            'Bucket': bucket_name,
            'Key': object_name,
            'Body': f,
            # 'ACL': self._ACL,
            'ContentType': f.headers.get('Content-Type')
        }
        if tagging:
            if isinstance(tagging, dict):
                tagging = urllib.parse.urlencode(tagging, quote_via=urllib.parse.quote_plus)
            put_source['Tagging'] = tagging
        try:
            self._s3.put_object(**put_source)
            # print('-'*100)
            # from pprint import pprint
            # tagging = self._s3.get_object_tagging(Bucket=bucket_name, Key=object_name)
            # pprint(tagging)
            # print('-'*100)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def copy_fileobj(self, bucket_name, copy_source, object_name):
        try:
            self._s3.copy_object(
                # ACL=self._ACL,
                CopySource=copy_source,
                Bucket=bucket_name,
                Key=object_name
            )
            # print('-'*100)
            # from pprint import pprint
            # tagging = self._s3.get_object_tagging(Bucket=bucket_name, Key=object_name)
            # pprint(tagging)
            # print('-'*100)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_fileobj(self, bucket_name, object_name):
        try:
            self._s3.delete_object(Bucket=bucket_name, Key=object_name)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_fileobjs(self, bucket_name, object_names):
        try:
            if object_names:
                objlist = [{'Key': obj} for obj in object_names]
                # objlist = [{'Key': urllib.parse.unquote_plus(obj)} for obj in object_names]
                self._s3.delete_objects(
                    Bucket=bucket_name, Delete={'Objects': objlist}
                )
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def list_bucket_objects_with_pager(
        self,
        bucket_name,
        prefix='',
        delimiter='/',
        max_items=1000,
        page_size=1000,
        starting_token=None,
        search=None,
    ):
        prefix = self.__prefixer(prefix)
        salt = self.cache.make_hash(f"{bucket_name}.{delimiter}.{starting_token}.{search}.{max_items}.{page_size}")
        data = self.cache.get(prefix, salt=salt)
        if not data:
            paginator = self._s3.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=bucket_name,
                Prefix=prefix,
                Delimiter=delimiter,
                EncodingType='url',
                PaginationConfig={
                    'MaxItems': max_items,
                    'PageSize': page_size,
                    'StartingToken': starting_token
                }
            )

            next_token = page_iterator.build_full_result().get('NextToken', None)
            if search:
                contents = page_iterator.search(f'Contents[?Size > `0` && contains(Key, `"{search}"`)]') # generator
                prefixes = page_iterator.search(f'CommonPrefixes[?contains(Prefix, `"{search}"`)]') # generator
            else:
                contents = page_iterator.search('Contents[?Size > `0`]') # generator
                prefixes = page_iterator.search('CommonPrefixes') # generator

            data = (
                list(prefixes),
                list(contents),
                next_token
            )
            self.cache.set(prefix, data, salt=salt)

        return data

    def download_fileobj(self, bucket_name, file_name, object_name):
        try:
            with open(file_name, 'wb') as f:
                self._s3.download_fileobj(bucket_name, object_name, f)
        except ClientError as e:
            logging.info(e)
            return False
        else:
            return True

    def is_exists(self, bucket_name, object_name=None):
        try:
            if object_name:
                self._s3.head_object(Bucket=bucket_name, Key=object_name)
            else:
                self._s3.head_object(Bucket=bucket_name)
        except ClientError as e:
            logging.info(e)
            return False
        else:
            return True
