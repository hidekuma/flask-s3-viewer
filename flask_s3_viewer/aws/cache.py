import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from datetime import date, datetime
from typing import Any

from ..errors import InvalidPrefix


class AWSCache:
    SUFFIX: str = ".__flask_s3_viewer_cache"

    def __init__(
        self,
        cache_dir: str | None = None,
        timeout: int | None = None,
    ) -> None:
        if not cache_dir:
            raise ValueError('have to set cache_dir.')
        if not timeout:
            raise ValueError('have to set timeout.')
        self._cache_dir: str = cache_dir
        self._timeout: int = timeout

        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir, mode=0o700)
        try:
            os.chmod(cache_dir, 0o700)
        except OSError:
            pass

    def make_hash(self, key: str) -> str:
        encoded = key.encode("utf-8")
        return hashlib.md5(encoded).hexdigest()

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(k): self._json_safe(v)
                for k, v in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._json_safe(v) for v in value]
        return str(value)

    def __make_key(
        self,
        key: str,
        salt: str | None = None,
        division: str | None = None,
    ) -> tuple[str, str]:
        if not isinstance(key, str):
            raise ValueError('key must be str.')
        # 일관성: trailing '/'는 rstrip으로 정리(planner step 5).
        key = key.rstrip('/')
        # 백슬래시는 Windows 경로/escape 오해를 유발하므로 거부.
        if '\\' in key:
            raise InvalidPrefix(key)
        # 단일 leading '/'까지는 호환을 위해 한 글자만 정규화 허용. 이상('//x' 등)은
        # 빈 segment 검증에서 거부되어야 하므로 lstrip을 쓰지 않는다.
        if key.startswith('/'):
            key = key[1:]
        # 정규화 후 traversal/현재디렉터리/빈 segment 토큰을 거부한다.
        # 빈 문자열 key('')는 cache_dir 루트(또는 division 디렉터리)를 의미하므로 허용.
        if key:
            for seg in key.split('/'):
                if seg in ('', '.', '..'):
                    raise InvalidPrefix(key)
        if not salt:
            salt = 'default'
        splited_keys = key.split('/') if key else []
        hash_ = '/'.join(splited_keys)
        if division:
            destination = os.path.join(self._cache_dir, division, hash_)
        else:
            destination = os.path.join(self._cache_dir, hash_)
        # defense-in-depth: 정규화/심볼릭링크 등 어떤 우회가 있어도 cache_dir
        # 밖으로 escape 하지 못하도록 realpath 봉쇄를 검증한다.
        real_dest = os.path.realpath(destination)
        real_root = os.path.realpath(self._cache_dir)
        if os.path.commonpath([real_dest, real_root]) != real_root:
            raise InvalidPrefix(key)
        return destination, os.path.join(destination, f'{salt}')

    def set(
        self,
        key: str,
        value: Any,
        timeout: int | None = None,
        salt: str | None = None,
        division: str | None = None,
    ) -> None:
        logging.debug(f'CACHE SET: "{key}"')
        file_handler, temp_path = tempfile.mkstemp(
            suffix=self.SUFFIX,
        )
        if timeout:
            expires_at = time.time() + timeout
        else:
            expires_at = time.time() + self._timeout

        with os.fdopen(file_handler, "wb") as f:
            payload = {
                'expires_at': expires_at,
                'value': self._json_safe(value),
            }
            f.write(json.dumps(payload).encode('utf-8'))
        ddir, dpath = self.__make_key(key, salt=salt, division=division)
        if not os.path.isdir(ddir):
            os.makedirs(ddir, mode=0o700)
        try:
            os.chmod(ddir, 0o700)
        except OSError:
            pass
        shutil.move(temp_path, dpath)
        try:
            os.chmod(dpath, 0o600)
        except OSError:
            pass

    def get(
        self,
        key: str,
        salt: str | None = None,
        division: str | None = None,
    ) -> Any | None:
        try:
            _, dpath = self.__make_key(key, salt=salt, division=division)
            logging.debug(f'CACHE GET: "{key}"')
            with open(dpath, encoding='utf-8') as f:
                payload = json.load(f)
                expires_at = payload['expires_at']
                if expires_at == 0 or expires_at >= time.time():
                    return payload['value']
                else:
                    os.remove(dpath)
                    return None
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            try:
                os.remove(dpath)
            except FileNotFoundError:
                pass
            return None

    def remove(self, key: str, division: str | None = None) -> bool:
        try:
            logging.debug(f'CACHE REMOVED: "{key}"')
            ddir, _ = self.__make_key(key, division=division)
            if os.path.isdir(ddir):
                shutil.rmtree(ddir)
        except FileNotFoundError:
            return True
        else:
            return True
