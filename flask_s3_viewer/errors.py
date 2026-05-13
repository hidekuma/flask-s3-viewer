from .config import (
    NAMESPACE,
    UPLOAD_TYPES,
)


class FlaskS3ViewerError(Exception):
    pass


class NotConfiguredCacheDir(FlaskS3ViewerError):
    def __init__(self) -> None:
        super().__init__(
            f'{NAMESPACE} have to configure "cache_dir", if you want to use caching.'
        )


class NotSupportUploadType(FlaskS3ViewerError):
    def __init__(self) -> None:
        super().__init__(
            f'{NAMESPACE} is only support {UPLOAD_TYPES} upload types.'
        )


class InvalidPrefix(FlaskS3ViewerError):
    def __init__(self, prefix: str) -> None:
        super().__init__(
            f'{NAMESPACE}: invalid prefix (path-traversal/illegal token): {prefix!r}'
        )


class InvalidRangeError(FlaskS3ViewerError):
    """The client supplied a Range header that S3 (or boto3) couldn't honor."""
    def __init__(self, header: str) -> None:
        super().__init__(f'{NAMESPACE}: invalid Range header: {header!r}')
