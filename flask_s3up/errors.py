from .config import (
    NAMESPACE
)

class FlaskS3UpError(Exception):
    pass

class NotConfiguredCacheDir(FlaskS3UpError):
    def __init__(self):
        super().__init__(f'{NAMESPACE} have to configure "cache_dir", if you want to use caching.')
