"""A2 regression: Flask extension standard pattern.

Covers:
    - FlaskS3Viewer(app, namespace=...) auto-registers under
      app.extensions['flask_s3_viewer'][namespace].
    - Same namespace double-init on the same app => ValueError.
    - Two apps with the same namespace are isolated.
    - get_instance(app, ns) staticmethod returns the same instance.
    - Deferred init pattern: FlaskS3Viewer(namespace=...) then .init_app(app).

These tests don't talk to S3 (no moto mock); the constructor builds a boto3
session against dummy creds which is enough for registration semantics.
"""
from __future__ import annotations

import os

import pytest
from flask import Flask

from flask_s3_viewer import FlaskS3Viewer


@pytest.fixture(autouse=True)
def _aws_env():
    """boto3.Session() needs *some* creds to construct successfully."""
    os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
    os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
    os.environ.setdefault('AWS_SESSION_TOKEN', 'testing')
    os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')


def _base_config(cache_dir: str) -> dict:
    return {
        # profile_name is a required field on the FLASK_S3_VIEWER_BUCKET
        # namedtuple. Pass None so the access_key/secret_key path is used.
        'profile_name': None,
        'bucket_name': 'fsv-test',
        'region_name': 'us-east-1',
        'access_key': 'testing',
        'secret_key': 'testing',
        'cache_dir': cache_dir,
        'use_cache': True,
        'ttl': 60,
    }


class TestAutoRegistration:
    def test_constructor_registers_under_extensions(self, tmp_path) -> None:
        app = Flask(__name__)
        sv = FlaskS3Viewer(
            app, namespace='ns-a', config=_base_config(str(tmp_path / 'c')),
        )
        assert app.extensions['flask_s3_viewer']['ns-a'] is sv

    def test_blueprint_registered_once(self, tmp_path) -> None:
        app = Flask(__name__)
        sv = FlaskS3Viewer(
            app, namespace='ns-a', config=_base_config(str(tmp_path / 'c1')),
        )
        # A second namespace should NOT re-register the same blueprint
        # (Flask raises if you try). Use add_new_one which targets the same app.
        sv.add_new_one(
            namespace='ns-b', config=_base_config(str(tmp_path / 'c2')),
        )
        assert 'flask_s3_viewer' in app.blueprints
        # Two namespaces share the single blueprint registration.
        assert len(
            [bp for bp in app.blueprints if bp == 'flask_s3_viewer']
        ) == 1


class TestDuplicateNamespace:
    def test_same_namespace_twice_raises_valueerror(self, tmp_path) -> None:
        app = Flask(__name__)
        FlaskS3Viewer(
            app, namespace='dup', config=_base_config(str(tmp_path / 'c1')),
        )
        with pytest.raises(ValueError, match="already registered"):
            FlaskS3Viewer(
                app, namespace='dup', config=_base_config(str(tmp_path / 'c2')),
            )


class TestMultiAppIsolation:
    def test_same_namespace_in_two_apps_is_isolated(self, tmp_path) -> None:
        app1 = Flask(__name__)
        app2 = Flask(__name__)
        sv1 = FlaskS3Viewer(
            app1, namespace='shared', config=_base_config(str(tmp_path / 'c1')),
        )
        sv2 = FlaskS3Viewer(
            app2, namespace='shared', config=_base_config(str(tmp_path / 'c2')),
        )
        assert sv1 is not sv2
        assert app1.extensions['flask_s3_viewer']['shared'] is sv1
        assert app2.extensions['flask_s3_viewer']['shared'] is sv2


class TestStaticAccessors:
    def test_get_instance_returns_registered(self, tmp_path) -> None:
        app = Flask(__name__)
        sv = FlaskS3Viewer(
            app, namespace='ns-a', config=_base_config(str(tmp_path / 'c')),
        )
        assert FlaskS3Viewer.get_instance(app, 'ns-a') is sv

    def test_get_instance_missing_raises_keyerror(self, tmp_path) -> None:
        app = Flask(__name__)
        FlaskS3Viewer(
            app, namespace='ns-a', config=_base_config(str(tmp_path / 'c')),
        )
        with pytest.raises(KeyError):
            FlaskS3Viewer.get_instance(app, 'does-not-exist')

    def test_get_boto_client_returns_s3(self, tmp_path) -> None:
        app = Flask(__name__)
        FlaskS3Viewer(
            app, namespace='ns-a', config=_base_config(str(tmp_path / 'c')),
        )
        c = FlaskS3Viewer.get_boto_client(app, 'ns-a')
        # boto3 S3 client carries a service-name-ish identity check.
        assert hasattr(c, 'list_objects_v2')

    def test_get_boto_session_returns_session(self, tmp_path) -> None:
        app = Flask(__name__)
        FlaskS3Viewer(
            app, namespace='ns-a', config=_base_config(str(tmp_path / 'c')),
        )
        s = FlaskS3Viewer.get_boto_session(app, 'ns-a')
        assert hasattr(s, 'client')


class TestDeferredInit:
    def test_init_app_after_construction(self, tmp_path) -> None:
        sv = FlaskS3Viewer(
            namespace='ns-x', config=_base_config(str(tmp_path / 'c')),
        )
        # No app at this point.
        app = Flask(__name__)
        assert 'flask_s3_viewer' not in app.extensions
        sv.init_app(app)
        assert app.extensions['flask_s3_viewer']['ns-x'] is sv
        assert 'flask_s3_viewer' in app.blueprints

    def test_init_app_requires_namespace(self, tmp_path) -> None:
        sv = FlaskS3Viewer(config=_base_config(str(tmp_path / 'c')))
        app = Flask(__name__)
        with pytest.raises(ValueError, match='non-empty namespace'):
            sv.init_app(app)

    def test_add_new_one_without_app_raises(self, tmp_path) -> None:
        sv = FlaskS3Viewer(
            namespace='ns-x', config=_base_config(str(tmp_path / 'c')),
        )
        with pytest.raises(RuntimeError, match='init_app'):
            sv.add_new_one(
                namespace='ns-y',
                config=_base_config(str(tmp_path / 'c2')),
            )
