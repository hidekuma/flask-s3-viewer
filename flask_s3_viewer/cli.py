import argparse
import os
import shutil
import textwrap

import click

from flask_s3_viewer.config import (
    FIXED_TEMPLATE_FOLDER,
    NAMESPACE,
)


class FlaskS3ViewerCli:
    parser: argparse.ArgumentParser

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(
            prog=NAMESPACE,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent(r"""

         ______ _           _       _____ ____   __      ___
        |  ____| |         | |     / ____|___ \  \ \    / (_)
        | |__  | | __ _ ___| | __ | (___   __) |  \ \  / / _  _____      _____ _ __
        |  __| | |/ _` / __| |/ /  \___ \ |__ <    \ \/ / | |/ _ \ \ /\ / / _ \ '__|
        | |    | | (_| \__ \   <   ____) |___) |    \  /  | |  __/\ V  V /  __/ |
        |_|    |_|\__,_|___/_|\_\ |_____/|____/      \/   |_|\___| \_/\_/ \___|_|
        =================== Flask S3Viewer Command Line Tool ====================
        """),
        )
        self.parser.add_argument(
            "-p",
            "--path",
            type=str,
            required=True,
            help="Enter the directory path where the template will be located",
        )
        self.parser.add_argument(
            "--with-static",
            action="store_true",
            help=(
                "Also copy the bundled static assets (css/app.css, "
                "vendor/htmx.min.js, js/flask.s3viewer.core.js) into "
                "<path>/static/. Useful when you intend to fork the entire "
                "UI bundle, not just the Jinja templates."
            ),
        )

    def handle(self) -> None:
        args: argparse.Namespace = self.parser.parse_args()

        # v1.0: templates were unified — copy the single bundled templates
        # directory verbatim. The legacy ``--template base|mdl`` switch is
        # gone (deprecation note in changelog / migration guide).
        file_path = os.path.dirname(os.path.abspath(__file__))
        target_root: str = args.path
        origin_template_path = os.path.join(
            file_path,
            'blueprints',
            FIXED_TEMPLATE_FOLDER,
        )

        if os.path.exists(target_root):
            click.echo(
                '\n {} : Already exists template directory ({}).'.format(
                    click.style(
                        "Failed",
                        fg="red",
                        bold=True,
                    ),
                    os.path.abspath(target_root),
                )
            )
            return

        shutil.copytree(origin_template_path, target_root)
        click.echo(
            '\n {} : Template successfully created. ({})'.format(
                click.style(
                    "Success",
                    fg="green",
                    bold=True,
                ),
                os.path.abspath(target_root),
            )
        )

        if args.with_static:
            origin_static = os.path.join(file_path, 'blueprints', 'static')
            target_static = os.path.join(target_root, 'static')
            shutil.copytree(origin_static, target_static)
            click.echo(
                ' {} : Static assets copied. ({})'.format(
                    click.style("Success", fg="green", bold=True),
                    os.path.abspath(target_static),
                )
            )


def handle() -> None:
    cli = FlaskS3ViewerCli()
    cli.handle()


if __name__ == "__main__":
    handle()
