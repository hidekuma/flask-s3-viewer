import logging
import mimetypes
import os
import unicodedata
from collections.abc import Iterable, Iterator
from typing import Any

from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.errorfactory import ClientError

from ..errors import InvalidPrefix, InvalidRangeError
from .cache import AWSCache
from .session import AWSSession

logger = logging.getLogger(__name__)


class AWSS3Client(AWSSession):
    """
    Inheritance of AWSSession
    """

    _bucket_name: str | None
    _base_path: str
    _cache: AWSCache

    @property
    def bucket_name(self) -> str | None:
        """Read-only public accessor for the configured S3 bucket name.

        Host code that needs to read the bucket should prefer this over the
        legacy ``_bucket_name`` private attribute. The private attribute is
        retained so any pre-existing direct accessors stay working.
        """
        return self._bucket_name

    def __init__(
        self,
        *,
        profile_name: str | None = None,
        region_name: str | None = None,
        endpoint_url: str | None = None,
        bucket_name: str | None = None,
        secret_key: str | None = None,
        access_key: str | None = None,
        session_token: str | None = None,
        cache_dir: str | None = None,
        ttl: int = 300,
        use_cache: bool = False,
        timezone: str | None = None,
        verify: bool | str | None = False,
        base_path: str = '',
        role_arn: str | None = None,
        role_session_name: str | None = None,
        external_id: str | None = None,
        duration_seconds: int | None = None,
        mfa_serial: str | None = None,
        token_code: str | None = None,
        token_code_callback: Any = None,
    ) -> None:
        super().__init__(
            profile_name=profile_name,
            region_name=region_name,
            secret_key=secret_key,
            access_key=access_key,
            session_token=session_token,
            role_arn=role_arn,
            role_session_name=role_session_name,
            external_id=external_id,
            duration_seconds=duration_seconds,
            mfa_serial=mfa_serial,
            token_code=token_code,
            token_code_callback=token_code_callback,
        )

        if not self.runnable:
            raise ValueError(
                'AWSSession is not available. check your credentials.')
        # self.location = {'LocationConstraint': self.region_name}
        self.region_name = region_name
        self.use_cache: bool = use_cache
        self._bucket_name = bucket_name
        # base_path가 leading '/'로 시작하면 prefixer 결과가 절대경로가 되어
        # cache key의 os.path.join이 root로 reset되는 장애가 발생한다. S3 키도
        # 동일하게 깨지므로 입력 시점에 한 번 정규화한다.
        # 시그니처가 str이지만 None이 흘러들어와도 안전하도록 `or ''`로 합성한다.
        self._base_path = (base_path or '').lstrip('/')
        self._s3: Any = self._session.client(
            's3',
            region_name=self.region_name,
            endpoint_url=endpoint_url,
            config=Config(signature_version='s3v4'),
            verify=verify,
        )
        if use_cache:
            self._cache = AWSCache(
                cache_dir=cache_dir,
                timeout=ttl,
            )

    def prefixer(self, prefix: str) -> str:
        if prefix:
            # 백슬래시는 Windows 경로/escape로 오해될 수 있으므로 거부한다.
            if '\\' in prefix:
                raise InvalidPrefix(prefix)
            # 단일 leading slash까지는 호환을 위해 정규화로 허용하지만, 그
            # 이상('//etc' 등)은 빈 segment 검증으로 거부되어야 한다. 따라서
            # lstrip을 쓰지 않고 1글자만 떼어낸다.
            if prefix.startswith('/'):
                prefix = prefix[1:]
            if not prefix.endswith('/') and prefix != '':
                prefix += '/'
            # path-traversal 토큰('..'), 현재 디렉터리 토큰('.'),
            # 빈 segment('//'에 의한 '')는 모두 거부한다.
            # 단, trailing '/'로 인해 split의 마지막 element가 ''인 경우는 정상.
            segments = prefix.split('/')
            if segments and segments[-1] == '':
                segments = segments[:-1]
            for seg in segments:
                if seg in ('', '.', '..'):
                    raise InvalidPrefix(prefix)
        result = os.path.join(self._base_path, prefix)
        return result

    def _validate_object_name(self, object_name: str) -> str:
        if not object_name or '\\' in object_name or '\x00' in object_name:
            raise InvalidPrefix(object_name)
        if object_name.startswith('/'):
            raise InvalidPrefix(object_name)
        segments = object_name.split('/')
        if segments and segments[-1] == '':
            segments = segments[:-1]
        for seg in segments:
            if seg in ('', '.', '..'):
                raise InvalidPrefix(object_name)
        return object_name

    def get_object_name(self, object_name: str) -> str:
        object_name = self._validate_object_name(object_name)
        if self._base_path:
            return f'{self._base_path}/{object_name}'
        return object_name

    def find_one(self, object_name: str, range: str | None = None) -> dict | None:
        """Fetch one object (optionally a byte range).

        ``range`` forwards an HTTP ``Range: bytes=...`` header to S3 so the
        caller can serve RFC 7233 ``206 Partial Content`` responses. A
        malformed/unsatisfiable range raises :class:`InvalidRangeError`
        (mapped to HTTP 416 by the view layer); any other ``ClientError``
        is logged and ``None`` is returned (object missing / access denied).
        """
        object_name = self.get_object_name(object_name)
        kwargs: dict = {'Bucket': self._bucket_name, 'Key': object_name}
        if range:
            kwargs['Range'] = range
        try:
            return self._s3.get_object(**kwargs)
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', '')
            if range and code in ('InvalidRange', 'InvalidArgument'):
                raise InvalidRangeError(range) from e
            logger.error(e)
            return None

    def purge(self, object_name: str) -> None:
        if self.use_cache:
            # Previously called with a comma-separated extra arg which stdlib
            # logging silently dropped — now uses %-formatting so the key is
            # actually visible at DEBUG level.
            logger.debug('PURGE: %s', object_name)
            self._cache.remove(
                os.path.dirname(object_name[:-1]),
                division=self._bucket_name,
            )

    def mkdir(self, object_name: str) -> bool:
        logger.debug('MKDIR: %s', object_name)
        try:
            put_source = {
                'Bucket': self._bucket_name,
                'Key': object_name,
                'Body': '',
            }

            self._s3.put_object(**put_source)

            if self.use_cache:
                self._cache.remove(
                    os.path.dirname(object_name[:-1]),
                    division=self._bucket_name,
                )
        except ClientError as e:
            # AllAccessDisabled error == bucket not found
            # NoSuchKey or InvalidRequest error == (dest bucket/obj == src bucket/obj)
            logger.error(e)
            return False

        return True

    def post_presign(self, object_name: str) -> dict:
        try:
            content_type = mimetypes.guess_type(object_name)
            key_prefix = f'{self._base_path}/' if self._base_path else ''
            r = self._s3.generate_presigned_post(
                self._bucket_name,
                object_name,
                Fields={
                    "Content-Type": content_type[0],
                },
                Conditions=[
                    {"Content-Type": content_type[0]},
                    ["starts-with", "$key", key_prefix],
                ],
                ExpiresIn=600,
            )
            return r
        except ClientError as e:
            logger.error(e)
            raise

    def add_one(self, f: Any, object_name: str) -> None:
        logger.debug('UP_OBJECT: %s', object_name)
        try:
            GB = 1024 ** 3
            config = TransferConfig(
                multipart_threshold=5 * GB,
            )

            self._s3.upload_fileobj(
                f,
                self._bucket_name,
                object_name,
                ExtraArgs={
                    'ContentType': f.headers.get('Content-Type'),
                },
                Config=config,
            )

            if self.use_cache:
                self._cache.remove(
                    os.path.dirname(object_name),
                    division=self._bucket_name,
                )
        except ClientError as e:
            logger.error(e)
            raise

    def remove_one(self, object_name: str) -> None:
        object_name = self.get_object_name(object_name)
        try:
            self._s3.delete_object(
                Bucket=self._bucket_name,
                Key=object_name,
            )
        except ClientError as e:
            logger.error(e)
            raise
        else:
            if self.use_cache:
                self._cache.remove(
                    os.path.dirname(object_name),
                    division=self._bucket_name,
                )

    def remove_all(self, object_names: Iterable[str]) -> None:
        try:
            if object_names:
                prefixes: set[str] = set()
                objects: list[dict] = []
                for obj in object_names:
                    object_name = self.get_object_name(obj)
                    if obj:
                        objects.append({'Key': object_name})
                        if self.use_cache:
                            prefixes.add(os.path.dirname(object_name))
                if objects:
                    self._s3.delete_objects(
                        Bucket=self._bucket_name,
                        Delete={'Objects': objects},
                    )
                if prefixes:
                    for prefix in prefixes:
                        self._cache.remove(prefix, division=self._bucket_name)

        except ClientError as e:
            logger.error(e)
            raise

    def find(
        self,
        prefix: str = '',
        delimiter: str = '/',
        max_items: int = 1000,
        page_size: int = 1000,
        starting_token: str | None = None,
        search: str | None = None,
        apply_cache: bool = True,
        cache_identity: str | None = None,
    ) -> tuple[list, list, str | None]:
        prefix = self.prefixer(prefix)

        def run() -> tuple[list, list, str | None]:
            nonlocal prefix, delimiter, max_items, page_size, starting_token, search
            paginator = self._s3.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=self._bucket_name,
                Prefix=prefix,
                Delimiter=delimiter,
                PaginationConfig={
                    'MaxItems': max_items,
                    'PageSize': page_size,
                    'StartingToken': starting_token,
                },
            )
            # ``build_full_result`` aggregates every page into one dict
            # already (Contents + CommonPrefixes + NextToken), so we use
            # that directly and apply size / search filtering in Python.
            # This keeps search Unicode-safe (Korean, Japanese, etc.) and
            # sidesteps the JMESPath f-string interpolation that earlier
            # versions used.
            result = page_iterator.build_full_result()
            next_token = result.get('NextToken')
            raw_contents = result.get('Contents') or []
            raw_prefixes = result.get('CommonPrefixes') or []
            # Drop empty "folder placeholder" objects from visible listings,
            # but keep them in flat recursive listings so folder deletion can
            # remove nested empty directory markers too.
            if delimiter:
                raw_contents = [c for c in raw_contents if c.get('Size', 0) > 0]
            if search:
                # NFC normalisation matters: macOS Finder uploads
                # decomposed Hangul (NFD: ㅅ+ㅡ+...), while the browser
                # IME emits precomposed Hangul (NFC: 스+...). Without
                # this step the bytes never match even though both
                # render identically. Same risk for accented Latin
                # (café NFC vs NFD).
                needle = unicodedata.normalize('NFC', search).lower()
                # Strip ``base_path`` BEFORE matching so the user sees
                # search behave on the key they actually see in the UI.
                # Otherwise the namespace's mount point itself leaks
                # into every comparison — e.g. base_path='/test' would
                # make 'test' match every object in the bucket.
                base_strip = (
                    self._base_path + '/' if self._base_path else ''
                )
                visible_prefix = (
                    prefix[len(base_strip):]
                    if base_strip and prefix.startswith(base_strip)
                    else prefix
                )

                def _visible_key(k: str) -> str:
                    if base_strip and k.startswith(base_strip):
                        return k[len(base_strip):]
                    return k

                def _relative_key(k: str) -> str:
                    key = _visible_key(k)
                    if visible_prefix and key.startswith(visible_prefix):
                        return key[len(visible_prefix):]
                    return key

                def _norm(s: str) -> str:
                    return unicodedata.normalize('NFC', s).lower()

                # Search is scoped to the current listing level only.
                # ``Delimiter='/'`` means ``raw_contents`` already holds
                # only the current folder's direct files.
                contents = [
                    c for c in raw_contents
                    if (c.get('Key') or '')
                    and needle in _norm(_relative_key(c['Key']))
                ]
                # Folder hits come from the current listing's direct
                # child prefixes only; match against the visible folder
                # name instead of recursing into descendants.
                prefixes = [
                    p for p in raw_prefixes
                    if (p.get('Prefix') or '')
                    and needle in _norm(
                        _visible_key(p['Prefix']).rstrip('/').rsplit('/', 1)[-1]
                    )
                ]
            else:
                contents = raw_contents
                prefixes = raw_prefixes
            return prefixes, contents, next_token

        data: tuple[list, list, str | None]
        # Search results bypass the disk cache entirely. The cache is
        # keyed by ``search`` so different queries can't collide, but
        # caching stale results across deployments turned out to be a
        # foot-gun (old JMESPath-filtered listings being served by new
        # Python-filtered code, etc.), and the value of caching a
        # one-shot query is low anyway.
        if self.use_cache and apply_cache and not search:
            salt = self._cache.make_hash(
                f"""{delimiter}|{starting_token}|{
                    search}|{max_items}|{page_size}|{cache_identity or ''}"""
            )
            cached = self._cache.get(
                prefix,
                salt=salt,
                division=self._bucket_name,
            )
            if not cached:
                logger.debug('NOT CACHED.')
                data = run()
                self._cache.set(
                    prefix,
                    data,
                    salt=salt,
                    division=self._bucket_name,
                )
            else:
                data = cached
        else:
            data = run()

        if self._base_path:
            for idx, d in enumerate(data[0]):
                if d:
                    data[0][idx]['Prefix'] = d['Prefix'].replace(
                        self._base_path + '/', '', 1)

            for idx, d in enumerate(data[1]):
                if d:
                    data[1][idx]['Key'] = d['Key'].replace(
                        self._base_path + '/', '', 1)
        return data

    def remove(self, object_names: list[str] | str) -> None:
        if isinstance(object_names, str):
            if object_names.endswith('/'):
                if object_names != '/':
                    # if == '' will deleted all
                    self.remove_all(
                        self.find_all(
                            object_names,
                        )
                    )
                    # Also delete the empty placeholder object created by
                    # mkdir() — find_all() filters Size>0 so the folder marker
                    # would otherwise be left behind, making the folder appear
                    # to survive deletion in the listing.
                    try:
                        folder_key = self.get_object_name(object_names)
                        self._s3.delete_object(
                            Bucket=self._bucket_name,
                            Key=folder_key,
                        )
                    except ClientError as e:
                        logger.error(e)

                    if self.use_cache:
                        self._cache.remove(
                            os.path.dirname(object_names[:-1]),
                            division=self._bucket_name,
                        )
                else:
                    raise ValueError('object_names can\'t be ""')
            else:
                self.remove_one(
                    object_names,
                )
        elif isinstance(object_names, list):
            self.remove_all(
                object_names,
            )

    def find_all(self, prefix: str) -> Iterator[str]:
        next_token: str | None = None
        while True:
            prefixes, contents, next_token = self.find(
                prefix=prefix,
                delimiter='',
                starting_token=next_token,
                apply_cache=False,
            )
            for p in prefixes:
                if p:
                    yield p

            for item in contents:
                if item:
                    yield item['Key']
            if not next_token:
                break

    def download_one(self, file_name: str, object_name: str) -> None:
        try:
            object_name = self.get_object_name(object_name)
            with open(file_name, 'wb') as f:
                self._s3.download_fileobj(self._bucket_name, object_name, f)
        except ClientError as e:
            logger.error(e)
            raise

    def is_exists(self, object_name: str | None = None) -> bool:
        try:
            if object_name:
                self._s3.head_object(
                    Bucket=self._bucket_name,
                    Key=object_name,
                )
            else:
                self._s3.head_object(
                    Bucket=self._bucket_name,
                )
        except ClientError:
            return False
        else:
            return True
