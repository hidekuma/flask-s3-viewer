import base64
import logging
import mimetypes
import warnings
from collections import namedtuple
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask

from .aws.s3 import AWSS3Client
from .config import (
    FIXED_TEMPLATE_FOLDER,
    NAMESPACE,
    UPLOAD_TYPES,
)
from .errors import (
    NotConfiguredCacheDir,
    NotSupportUploadType,
)

APP_TEMPLATE_FOLDER: str = FIXED_TEMPLATE_FOLDER

__version__: str = "1.0.0a2"

_EXTENSION_KEY: str = "flask_s3_viewer"


def _install_security_headers(app: Flask) -> None:
    if app.extensions.get("flask_s3_viewer.security_headers"):
        return

    @app.after_request
    def _apply_security_headers(response: Any) -> Any:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    app.extensions["flask_s3_viewer.security_headers"] = True


def _resolve_logo(logo_url: str | None, logo_path: str | None) -> str | None:
    """Return a browser-usable URL for the logo.

    If ``logo_path`` is provided, read the file once and inline it as a
    ``data:`` URI so the deployer doesn't need to expose it via a static
    route. Otherwise fall through to ``logo_url`` (which may itself be a
    Flask ``url_for`` result, an absolute URL, or ``None``).
    """
    if logo_path:
        mime, _ = mimetypes.guess_type(logo_path)
        if not mime:
            mime = "application/octet-stream"
        with open(logo_path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    return logo_url


class FlaskS3Viewer(AWSS3Client):
    """
    v1.0 breaking change:
      - Singleton 메타클래스 제거.
      - 동일 namespace 재초기화 시 ValueError raise.
      - blueprint는 첫 init_app 호출에서 자동 등록되며 `register()`는 제거됨.
      - `get_instance`/`get_boto_client`/`get_boto_session`은 staticmethod(app, namespace).
    """

    FLASK_S3_VIEWER_BUCKET_CONFIGS: dict = {}
    # mypy: namedtuple typename은 변수명과 동일해야 한다.
    FLASK_S3_VIEWER_BUCKET = namedtuple(
        "FLASK_S3_VIEWER_BUCKET",
        """
        profile_name
        region_name
        endpoint_url
        bucket_name
        secret_key
        access_key
        session_token
        cache_dir
        ttl
        use_cache
        timezone
        verify
        base_path
        role_arn
        role_session_name
        external_id
        duration_seconds
        mfa_serial
        token_code
        token_code_callback
        """,
    )

    def __init__(
        self,
        app: Flask | None = None,
        namespace: str | None = None,
        object_hostname: str | None = None,
        allowed_extensions: set[str] | None = None,
        template_namespace: str | None = None,
        upload_type: str = "default",
        title: str | None = None,
        logo_url: str | None = None,
        logo_path: str | None = None,
        template_folder: str | None = None,
        auth_callback: Any = None,
        permission_callback: Any = None,
        google_client_id: str | None = None,
        google_client_secret: str | None = None,
        allowed_emails: list[str] | set[str] | None = None,
        allowed_domains: list[str] | set[str] | None = None,
        config: dict | None = None,
    ) -> None:
        """
        :param Flask.app app: Flask application (Optional, v1.0+). If provided,
            extension is auto-registered. Otherwise call :meth:`init_app` later.
        :param str namespace: Unique namespace of Flask S3Viewer (Required)
        :param url object_hostname: Hostname, e.g. Cloudfront endpoint
        :param set allowed_extensions: e.g. {'jpg', 'png'}
        :param str template_namespace: DEPRECATED — templates were unified in
            v1.0. Passing this argument emits a :class:`DeprecationWarning`
            and the value is ignored.
        :param str upload_type: Upload type
        :param str title: Heading + browser title text. Defaults to
            ``"Flask S3 Viewer"``.
        :param str logo_url: URL of a custom logo image (absolute URL, Flask
            ``url_for`` result, or any browser-resolvable path).
        :param str logo_path: Local filesystem path to a logo image. It is
            read once and inlined as a ``data:`` URI — convenient when you
            don't want to expose the file via a separate static route.
            ``logo_path`` takes precedence over ``logo_url``.
        :param str template_folder: Optional path to a directory containing
            overrides for any of the bundled templates (``layout.html``,
            ``files.html``, ``_file_list.html``, ``_pagination.html``,
            ``_upload_form.html``, ``error.html``). Files in this folder are
            preferred by Jinja over the bundled originals. Scaffold a
            ready-to-edit starting point with ``flask_s3_viewer -p ./out``.
        :param dict config: Bucket configs
        """
        if template_namespace is not None:
            warnings.warn(
                "template_namespace is removed in v1.0; templates are unified.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.app: Flask | None = app
        self.namespace: str | None = namespace
        if object_hostname and object_hostname.endswith("/"):
            object_hostname = object_hostname[:-1]
        self.object_hostname: str | None = object_hostname
        self.allowed_extensions: set[str] | None = allowed_extensions
        self.title: str = title or "Flask S3 Viewer"
        self.logo_url: str | None = _resolve_logo(logo_url, logo_path)
        self.template_folder: str | None = template_folder
        # ---- auth wiring ----
        from .auth import (
            allow_all_auth,
            allow_all_permissions,
            email_allowlist,
        )

        # Google OAuth opt-in: deploying with credentials wires the
        # session-based default auth_callback unless the caller
        # supplies their own.
        self.google_client_id: str | None = google_client_id
        self.google_client_secret: str | None = google_client_secret
        if auth_callback is None and google_client_id:
            from .auth.google import session_auth_callback

            auth_callback = session_auth_callback
        self.auth_callback = auth_callback or allow_all_auth
        # Permission wiring precedence: explicit callback > allow_lists > allow-all.
        if permission_callback is None and (allowed_emails or allowed_domains):
            permission_callback = email_allowlist(
                emails=list(allowed_emails or []),
                domains=list(allowed_domains or []),
            )
        self.permission_callback = permission_callback or allow_all_permissions
        # Bookkeeping: enable enforcement only when the caller passed at
        # least one auth-related option. `auth_callback` may have been
        # rewritten above (None → session_auth_callback when Google is
        # configured) — so check against the post-defaults state.
        self.auth_enabled: bool = bool(
            auth_callback is not None
            or permission_callback is not None
            or google_client_id
            or allowed_emails
            or allowed_domains
        )
        if upload_type not in UPLOAD_TYPES:
            raise NotSupportUploadType
        self.upload_type: str = upload_type
        self.__max_pages: int = 10
        self.__max_items: int = 50

        if not config:
            config = dict()

        # bucket_name is required. profile_name은 호출자가 항상 명시할
        # 것이라는 암묵 가정을 제거하기 위해 None default를 추가한다.
        # namedtuple FLASK_S3_VIEWER_BUCKET 필드 누락에 의한 TypeError 방어.
        config.setdefault("profile_name", None)
        config.setdefault("region_name", None)
        config.setdefault("endpoint_url", None)
        config.setdefault("secret_key", None)
        config.setdefault("access_key", None)
        config.setdefault("session_token", None)
        if config.get("use_cache"):
            if not config.get("cache_dir"):
                raise NotConfiguredCacheDir
        config.setdefault("cache_dir", None)
        config.setdefault("ttl", 300)
        config.setdefault("use_cache", None)
        config.setdefault("timezone", None)
        config.setdefault("verify", None)
        config.setdefault("base_path", "")
        # STS AssumeRole + MFA — all None by default so boto3's standard
        # credential chain handles 99% of deployments untouched.
        config.setdefault("role_arn", None)
        config.setdefault("role_session_name", None)
        config.setdefault("external_id", None)
        config.setdefault("duration_seconds", None)
        config.setdefault("mfa_serial", None)
        config.setdefault("token_code", None)
        config.setdefault("token_code_callback", None)
        self.display_timezone: ZoneInfo | None = None
        if config.get("timezone"):
            try:
                self.display_timezone = ZoneInfo(config["timezone"])
            except ZoneInfoNotFoundError as e:
                raise ValueError(f"Unknown timezone: {config['timezone']}") from e
        super().__init__(**config)

        self.FLASK_S3_VIEWER_BUCKET_CONFIGS[namespace] = self.FLASK_S3_VIEWER_BUCKET(**config)

        if app is not None:
            self.init_app(app)

    @property
    def max_pages(self) -> int:
        return self.__max_pages

    @property
    def max_items(self) -> int:
        return self.__max_items

    def init_app(self, app: Flask) -> None:
        """
        Register this FlaskS3Viewer instance to a Flask application.

        - Stores the instance in ``app.extensions['flask_s3_viewer'][namespace]``.
        - Registers the blueprint once per app (first init_app call).
        - Raises :class:`ValueError` if the namespace is already registered for
          the given app (this is the v1.0 breaking change replacing Singleton's
          silent reuse semantics).
        """
        if self.namespace is None:
            raise ValueError("FlaskS3Viewer requires a non-empty namespace.")

        registry = app.extensions.setdefault(_EXTENSION_KEY, {})
        if self.namespace in registry:
            raise ValueError(
                f"FlaskS3Viewer namespace '{self.namespace}' is already registered on this app."
            )
        registry[self.namespace] = self
        # Remember the first app so add_new_one() can default to it.
        if self.app is None:
            self.app = app

        # Register the blueprint only once per app.
        if NAMESPACE not in app.blueprints:
            from .blueprints.view import auth_blueprint, blueprint

            app.register_blueprint(blueprint)
            # Auth blueprint lives outside the namespace prefix — the
            # handlers themselves 404 when no viewer on this app has
            # auth wired up, so it's safe to always register.
            app.register_blueprint(auth_blueprint)
            logging.info("*** registered FlaskS3Viewer blueprint! ***")
            logging.info(app.url_map)
        _install_security_headers(app)

        # When the deployer points at a custom templates directory, prepend a
        # FileSystemLoader so their files override the bundled originals via
        # Flask's standard Jinja ChoiceLoader pattern. Per-namespace folders
        # are merged into a single search path so add_new_one() can stack
        # overrides without clobbering each other.
        if self.template_folder:
            self._install_template_override(app, self.template_folder)

        # Google OAuth: register the Authlib client lazily (only when
        # the deployer supplied credentials) so the optional [auth]
        # extra remains optional for the no-auth flow.
        if self.google_client_id and self.google_client_secret:
            from .auth.google import configure_google_oauth

            configure_google_oauth(app, self.google_client_id, self.google_client_secret)

        logging.info(f"*** FlaskS3Viewer initialized for namespace='{self.namespace}' ***")

    @staticmethod
    def _install_template_override(app: Flask, folder: str) -> None:
        """Prepend ``folder`` to the app's Jinja loader so its templates win.

        Uses Flask's ``ChoiceLoader`` + ``FileSystemLoader`` pattern so other
        blueprints' template resolution is untouched.
        """
        from jinja2 import ChoiceLoader, FileSystemLoader

        custom = FileSystemLoader(folder)
        existing = app.jinja_loader
        if isinstance(existing, ChoiceLoader):
            # Merge while keeping previously-installed overrides at the front.
            loaders = [custom] + list(existing.loaders)
            app.jinja_loader = ChoiceLoader(loaders)
        elif existing is not None:
            app.jinja_loader = ChoiceLoader([custom, existing])
        else:
            app.jinja_loader = custom

    @staticmethod
    def get_instance(app: Flask, namespace: str) -> "FlaskS3Viewer":
        """
        Return a Flask S3Viewer instance for the given app + namespace.

        v1.0 breaking: previously ``get_instance(namespace)`` returned the
        global Singleton entry. It now requires an explicit ``app`` argument
        (or use ``current_app.extensions['flask_s3_viewer'][namespace]`` from
        within a request).
        """
        instance: FlaskS3Viewer = app.extensions[_EXTENSION_KEY][namespace]
        return instance

    @staticmethod
    def get_boto_client(app: Flask, namespace: str) -> Any:
        """
        Return the underlying boto3 S3 client for the given app + namespace.
        """
        return app.extensions[_EXTENSION_KEY][namespace]._s3

    @staticmethod
    def get_boto_session(app: Flask, namespace: str) -> Any:
        """
        Return the underlying boto3 Session for the given app + namespace.
        """
        return app.extensions[_EXTENSION_KEY][namespace]._session

    def add_new_one(
        self,
        namespace: str | None = None,
        object_hostname: str | None = None,
        allowed_extensions: set[str] | None = None,
        template_namespace: str | None = None,
        upload_type: str = "default",
        config: dict | None = None,
    ) -> "FlaskS3Viewer":
        """
        Initialize another bucket bound to the same Flask app.

        :param str namespace: Unique namespace of Flask S3Viewer
        :param url object_hostname: Hostname, e.g. Cloudfront endpoint
        :param set allowed_extensions: e.g. {'jpg', 'png'}
        :param str template_namespace: DEPRECATED — see :meth:`__init__`.
        :param str upload_type: Upload type
        :param dict config: Bucket configs

        Return:
            :class:`FlaskS3Viewer`
        """
        if self.app is None:
            raise RuntimeError(
                "add_new_one() requires the initial FlaskS3Viewer to be bound "
                "to a Flask app (pass app=... or call init_app() first)."
            )
        return FlaskS3Viewer(
            self.app,
            namespace=namespace,
            object_hostname=object_hostname,
            allowed_extensions=allowed_extensions,
            template_namespace=template_namespace,
            upload_type=upload_type,
            config=config,
        )
