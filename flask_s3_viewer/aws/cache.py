import os
import shutil
import hashlib
import tempfile
import time
import logging

try:
    import cPickle as pickle  # pyright: ignore[reportMissingImports]
except ImportError:
    import pickle


class AWSCache:
    SUFFIX = ".__flask_s3_viewer_cache"

    def __init__(self, cache_dir=None, timeout=None):
        if not cache_dir:
            raise ValueError('have to set cache_dir.')
        if not timeout:
            raise ValueError('have to set timeout.')
        self._cache_dir = cache_dir
        self._timeout = timeout

        if not os.path.isdir(cache_dir):
            os.makedirs(cache_dir)

    def make_hash(self, key):
        key = key.encode("utf-8")
        return hashlib.md5(key).hexdigest()

    def __make_key(self, key, salt=None, division=None):
        if key.endswith('/'):
            key = key[:-1]
        if not salt:
            salt = 'default'
        if isinstance(key, str):
            splited_keys = key.split('/')
            # for i, k in enumerate(splited_keys):
            # splited_keys[i] = self.make_hash(k)
            hash = '/'.join(splited_keys)
            if division:
                destination = os.path.join(self._cache_dir, division, hash)
            else:
                destination = os.path.join(self._cache_dir, hash)
            return destination, os.path.join(destination, f'{salt}')
        else:
            raise ValueError('key must be str.')

    def set(self, key, value, timeout=None, salt=None, division=None):
        logging.info(f'CACHE SET: "{key}"')
        file_handler, temp_path = tempfile.mkstemp(
            suffix=self.SUFFIX,
        )
        if timeout:
            expires_at = time.time() + timeout
        else:
            expires_at = time.time() + self._timeout

        with os.fdopen(file_handler, "wb") as f:
            # pickle protocol 3 >= python3.0
            pickle.dump(expires_at, f, 3)
            pickle.dump(value, f, 3)
        ddir, dpath = self.__make_key(key, salt=salt, division=division)
        if not os.path.isdir(ddir):
            os.makedirs(ddir)
        shutil.move(temp_path, dpath)

    def get(self, key, salt=None, division=None):
        try:
            _, dpath = self.__make_key(key, salt=salt, division=division)
            logging.info(f'CACHE GET: "{key}"')
            with open(dpath, "rb") as f:
                expires_at = pickle.load(f)
                if expires_at == 0 or expires_at >= time.time():
                    return pickle.load(f)
                else:
                    os.remove(dpath)
                    return None
        except FileNotFoundError:
            return None

    def remove(self, key, division=None):
        try:
            logging.info(f'CACHE REMOVED: "{key}"')
            ddir, _ = self.__make_key(key, division=division)
            if os.path.isdir(ddir):
                shutil.rmtree(ddir)
        except FileNotFoundError:
            return True
        else:
            return True

    # very danger
    # def clear(self):
        # shutil.rmtree(self._cache_dir)
