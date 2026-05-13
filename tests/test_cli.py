"""CLI tests: template copy via argparse-driven FlaskS3ViewerCli.

The CLI ships the unified template directory under
``flask_s3_viewer/blueprints/templates/`` and copies it to a user-chosen
destination. We test the public ``handle()`` flow end-to-end against tmp_path.

v1.0: ``--template base|mdl`` was removed — only ``-p/--path`` remains.
"""
from __future__ import annotations

import os
import sys

import pytest

from flask_s3_viewer.cli import FlaskS3ViewerCli


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, 'argv', ['flask_s3_viewer', *argv])
    FlaskS3ViewerCli().handle()


class TestTemplateCopy:
    def test_template_directory_copied(self, tmp_path, monkeypatch) -> None:
        dest = tmp_path / 'tpl'
        _run(monkeypatch, ['-p', str(dest)])
        assert dest.is_dir()
        # The bundled templates ship layout.html / files.html among others.
        names = {p.name for p in dest.iterdir()}
        assert 'layout.html' in names
        assert 'files.html' in names

    def test_existing_path_does_not_overwrite(
        self, tmp_path, monkeypatch, capsys,
    ) -> None:
        dest = tmp_path / 'tpl-existing'
        dest.mkdir()
        sentinel = dest / 'sentinel.txt'
        sentinel.write_text('keep me')

        _run(monkeypatch, ['-p', str(dest)])

        # The sentinel must still be there — the CLI must refuse the copy
        # when the destination already exists.
        assert sentinel.exists()
        assert sentinel.read_text() == 'keep me'
        captured = capsys.readouterr()
        assert 'Already exists' in captured.out or 'Failed' in captured.out

    def test_legacy_template_flag_rejected(
        self, tmp_path, monkeypatch,
    ) -> None:
        # v1.0 removed ``-t/--template``. argparse must reject unknown args.
        with pytest.raises(SystemExit) as excinfo:
            _run(
                monkeypatch,
                ['-p', str(tmp_path / 'tpl-bad'), '-t', 'mdl'],
            )
        assert excinfo.value.code == 2

    def test_missing_required_path_arg_rejected(self, monkeypatch) -> None:
        with pytest.raises(SystemExit) as excinfo:
            _run(monkeypatch, [])
        assert excinfo.value.code == 2

    def test_path_arg_is_absolute_when_relative_input(
        self, tmp_path, monkeypatch,
    ) -> None:
        # Use a relative dest under tmp_path by chdir'ing there.
        monkeypatch.chdir(tmp_path)
        _run(monkeypatch, ['-p', 'tpl-rel'])
        assert (tmp_path / 'tpl-rel').is_dir()


class TestModuleEntryPoint:
    def test_module_handle_function_constructs_cli(self, monkeypatch, tmp_path) -> None:
        # The pyproject entry_point is ``flask_s3_viewer.cli:handle`` (module
        # function, not bound method).
        from flask_s3_viewer.cli import handle as module_handle

        monkeypatch.setattr(
            sys, 'argv', ['flask_s3_viewer', '-p', str(tmp_path / 'tpl-mod')]
        )
        module_handle()
        assert os.path.isdir(str(tmp_path / 'tpl-mod'))
