import os
import shutil
import hashlib
import tempfile
import time

try:
    import cPickle as pickle
except ImportError:
    import pickle

class AWSCache:
    SUFFIX = ".__flask_s3up_cache"
    def __init__(self, temp_dir=None, timeout=300):
        if not temp_dir:
            raise ValueError
        self._temp_dir = temp_dir
        self._timeout = timeout

        if not os.path.isdir(temp_dir):
            os.makedirs(temp_dir)

    def make_hash(self, key):
        key = key.encode("utf-8")
        return hashlib.md5(key).hexdigest()

    def __make_key(self, key, salt=None):
        if key.endswith('/'):
            key = key[:-1]
        if not salt:
            salt = 'default'
        if isinstance(key, str):
            splited_key = key.split('/')
            for i, k in enumerate(splited_key):
                splited_key[i] = self.make_hash(k)
            hash = '/'.join(splited_key)
            destination = os.path.join(self._temp_dir, hash)
        return destination, os.path.join(destination, f'{salt}')

    def set(self, key, value, timeout=None, salt=None):
        file_handler, temp_path = tempfile.mkstemp(
            suffix = self.SUFFIX,
        )
        if timeout:
            expires_at = time.time() + timeout
        else:
            expires_at = time.time() + self._timeout

        with os.fdopen(file_handler, "wb") as f:
            # pickle protocol 3 >= python3.0
            pickle.dump(expires_at, f, 3)
            pickle.dump(value, f, 3)
        ddir, dpath = self.__make_key(key, salt)
        if not os.path.isdir(ddir):
            os.makedirs(ddir)
        shutil.move(temp_path, dpath)

    def get(self, key, salt=None):
        try:
            _, dpath = self.__make_key(key, salt)
            with open(dpath, "rb") as f:
                expires_at = pickle.load(f)
                if expires_at == 0 or expires_at >= time.time():
                    return pickle.load(f)
                else:
                    os.remove(dpath)
                    return None
        except FileNotFoundError:
            return None

    def remove(self, key):
        try:
            ddir, _ = self.__make_key(key)
            if os.path.isdir(ddir):
                shutil.rmtree(ddir)
        except FileNotFoundError:
            return True
        else:
            return True

    # very danger
    # def clear(self):
        # shutil.rmtree(self._temp_dir)
