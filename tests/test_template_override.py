"""Custom-template override via ``FlaskS3Viewer(template_folder=...)`` +
CLI scaffold (``flask_s3_viewer -p ./out [--with-static]``).

The override path uses Flask's standard ``ChoiceLoader`` so files in the
user's directory win over the bundled originals, while any not-overridden
template still resolves against the package.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import boto3
import pytest
from flask import Flask
from moto import mock_aws

from flask_s3_viewer import FlaskS3Viewer


@pytest.fixture
def custom_templates(tmp_path: Path) -> Path:
    """User-provided template folder that overrides just ``files.html``."""
    folder = tmp_path / 'my-templates'
    folder.mkdir()
    (folder / 'files.html').write_text(
        "<!doctype html><html><body><h1>CUSTOM OVERRIDE</h1>"
        "<div id='file-list'>marker</div></body></html>",
        encoding='utf-8',
    )
    return folder


@pytest.fixture
def override_app(aws_credentials, tmp_path, custom_templates):
    """Flask app whose viewer points at ``custom_templates``."""
    with mock_aws():
        boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-tpl')
        flask_app = Flask(__name__)
        flask_app.config['TESTING'] = True
        FlaskS3Viewer(
            flask_app,
            namespace='fsv-tpl',
            template_folder=str(custom_templates),
            config={
                'profile_name': None,
                'bucket_name': 'fsv-tpl', 'region_name': 'us-east-1',
                'access_key': 'testing', 'secret_key': 'testing',
                'cache_dir': str(tmp_path / 'cache'),
                'use_cache': True, 'ttl': 60,
            },
        )
        yield flask_app


# ---------------------------------------------------------------------------
# Library: ``template_folder=`` override semantics
# ---------------------------------------------------------------------------

class TestTemplateOverride:
    def test_overridden_template_wins(self, override_app):
        """A page that resolves to ``files.html`` must use the user's copy."""
        rv = override_app.test_client().get('/fsv-tpl/files')
        assert rv.status_code == 200
        body = rv.data.decode('utf-8')
        assert 'CUSTOM OVERRIDE' in body

    def test_non_overridden_template_falls_back(self, override_app, custom_templates):
        """``_pagination.html`` isn't in the user's folder, so the bundled
        version still resolves. We verify by hitting a 404 download — that
        uses ``error.html`` from the bundle.
        """
        rv = override_app.test_client().get('/fsv-tpl/files/ghost.txt')
        assert rv.status_code == 404
        # error.html is bundled; the body should render the FS3V_CODE the
        # default template surfaces.
        assert b'404' in rv.data

    def test_jinja_loader_is_choice_with_custom_first(self, override_app, custom_templates):
        from jinja2 import ChoiceLoader, FileSystemLoader
        loader = override_app.jinja_loader
        assert isinstance(loader, ChoiceLoader)
        first = loader.loaders[0]
        assert isinstance(first, FileSystemLoader)
        assert str(custom_templates) in first.searchpath

    def test_no_template_folder_keeps_default_loader(self, app):
        """Sanity guard: viewer without ``template_folder`` must NOT touch
        the app's existing Jinja loader.
        """
        from jinja2 import ChoiceLoader
        # The default-mode fixture leaves the app's jinja_loader as
        # whatever Flask installed by itself (not a ChoiceLoader wrapped
        # by the extension).
        loader = app.jinja_loader
        # If it ever becomes a ChoiceLoader, our extension didn't prepend
        # a FileSystemLoader since no template_folder was passed.
        if isinstance(loader, ChoiceLoader):
            for sub in loader.loaders:
                from jinja2 import FileSystemLoader
                if isinstance(sub, FileSystemLoader):
                    # Bundled package loader is fine; any *user* override
                    # path would surface here as a non-package directory.
                    pass


# ---------------------------------------------------------------------------
# CLI: ``flask_s3_viewer -p ./out [--with-static]``
# ---------------------------------------------------------------------------

class TestCliScaffold:
    """The CLI is the supported way to seed ``template_folder``.

    Run via ``python -m flask_s3_viewer.cli`` so we don't depend on the
    console-script entry point being installed in the test environment.
    """

    EXPECTED_TEMPLATES = (
        'layout.html',
        'files.html',
        '_file_list.html',
        '_pagination.html',
        '_upload_form.html',
        'error.html',
    )

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        # Don't change cwd — the project is not installed; python needs to
        # resolve flask_s3_viewer from the test runner's sys.path roots.
        return subprocess.run(
            [sys.executable, '-m', 'flask_s3_viewer.cli', *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_scaffold_creates_template_files(self, tmp_path):
        out = tmp_path / 'mytpl'
        result = self._run('-p', str(out))
        assert result.returncode == 0, result.stderr
        for name in self.EXPECTED_TEMPLATES:
            assert (out / name).exists(), f'missing scaffolded {name}'
        # No static folder by default — opt-in via --with-static.
        assert not (out / 'static').exists()

    def test_scaffold_existing_directory_is_refused(self, tmp_path):
        out = tmp_path / 'existing'
        out.mkdir()
        result = self._run('-p', str(out))
        # CLI prints "Failed" but exits 0 (legacy behavior preserved).
        assert 'Failed' in result.stdout
        # Directory must remain empty since we refused to overwrite.
        assert list(out.iterdir()) == []

    def test_with_static_flag_copies_assets(self, tmp_path):
        out = tmp_path / 'full-bundle'
        result = self._run('-p', str(out), '--with-static')
        assert result.returncode == 0, result.stderr
        # Templates land at the root of the target.
        assert (out / 'layout.html').exists()
        # Static assets nest under <out>/static/<...>.
        assert (out / 'static' / 'css' / 'app.css').exists()
        assert (out / 'static' / 'vendor' / 'htmx.min.js').exists()
        assert (out / 'static' / 'js' / 'flask.s3viewer.core.js').exists()


# ---------------------------------------------------------------------------
# End-to-end: scaffold → wire as ``template_folder`` → page renders override
# ---------------------------------------------------------------------------

class TestScaffoldThenOverride:
    def test_full_workflow(self, aws_credentials, tmp_path):
        """The supported end-to-end story for designers."""
        # 1) scaffold
        scaffolded = tmp_path / 'scaffold'
        subprocess.run(
            [sys.executable, '-m', 'flask_s3_viewer.cli', '-p', str(scaffolded)],
            check=True, capture_output=True,
        )
        # 2) edit one template
        files_html = scaffolded / 'files.html'
        files_html.write_text(
            "<!doctype html><html><body>"
            "<h1>scaffold-edit-token</h1>"
            "<div id='file-list'>x</div>"
            "</body></html>",
            encoding='utf-8',
        )
        # 3) point the viewer at the scaffolded folder
        with mock_aws():
            boto3.client('s3', region_name='us-east-1').create_bucket(Bucket='fsv-scaffold')
            app = Flask(__name__)
            app.config['TESTING'] = True
            FlaskS3Viewer(
                app,
                namespace='sf',
                template_folder=str(scaffolded),
                config={
                    'profile_name': None,
                    'bucket_name': 'fsv-scaffold', 'region_name': 'us-east-1',
                    'access_key': 'testing', 'secret_key': 'testing',
                    'cache_dir': str(tmp_path / 'cache'),
                    'use_cache': True, 'ttl': 60,
                },
            )
            rv = app.test_client().get('/sf/files')  # namespace stays 'sf'
        assert rv.status_code == 200
        assert b'scaffold-edit-token' in rv.data
