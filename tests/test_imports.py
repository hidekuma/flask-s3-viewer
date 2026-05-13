"""Smoke imports for re-export surfaces that otherwise have 0% coverage.

`flask_s3_viewer/routers.py` is a v0.x compatibility re-export
(`from .blueprints.view import blueprint as FlaskS3ViewerViewRouter`).
The main package no longer imports it dynamically since A2, so coverage
reports show 0% even though external users may still import it. A simple
smoke test pins the public surface and prevents accidental removal.
"""
from __future__ import annotations


def test_routers_reexports_blueprint() -> None:
    from flask_s3_viewer import routers

    assert routers.FlaskS3ViewerViewRouter is not None
    # FlaskS3ViewerViewRouter is a flask Blueprint instance.
    assert routers.FlaskS3ViewerViewRouter.name == 'flask_s3_viewer'
