"""Shared pytest fixtures for flask-s3-viewer.

Uses moto v5 ``mock_aws`` (unified decorator/context manager) — keep
``moto[s3]>=5.0`` in dev deps. AWS credential env vars are set to dummy
values so boto3.Session() never reaches the real AWS metadata service.
"""
import os

import boto3
import pytest
from flask import Flask
from moto import mock_aws

from flask_s3_viewer import FlaskS3Viewer


@pytest.fixture
def aws_credentials():
    """Mocked AWS credentials for boto3 / moto.

    moto requires *something* in these env vars so boto3.Session() succeeds
    inside the mock context — otherwise it tries the real metadata service.
    """
    os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
    os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
    os.environ.setdefault('AWS_SESSION_TOKEN', 'testing')
    os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')


@pytest.fixture
def s3_bucket(aws_credentials):
    """Provide a moto-mocked S3 client + a pre-created test bucket."""
    with mock_aws():
        client = boto3.client('s3', region_name='us-east-1')
        bucket = 'fsv-test'
        client.create_bucket(Bucket=bucket)
        yield client, bucket


@pytest.fixture
def app(s3_bucket, tmp_path):
    """Flask app with a single FlaskS3Viewer extension bound under 'fsv-test'.

    Uses the v1.0+ FlaskS3Viewer(app, ...) auto-registration pattern (not the
    removed register() call). Cache dir is isolated per-test via tmp_path.
    The fixture must run inside ``mock_aws()`` — that's done by depending on
    ``s3_bucket`` which yields from inside the mock context.
    """
    _client, bucket = s3_bucket
    flask_app = Flask(__name__)
    flask_app.config['TESTING'] = True
    FlaskS3Viewer(
        flask_app,
        namespace='fsv-test',
        config={
            # profile_name is a required field on the namedtuple config
            # snapshot; pass None to skip profile-based session lookup
            # (explicit access_key/secret_key path is used instead).
            'profile_name': None,
            'bucket_name': bucket,
            'region_name': 'us-east-1',
            'access_key': 'testing',
            'secret_key': 'testing',
            'cache_dir': str(tmp_path / 'cache'),
            'use_cache': True,
            'ttl': 60,
        },
    )
    yield flask_app


@pytest.fixture
def client(app):
    """Flask test client bound to the moto-mocked app."""
    return app.test_client()
