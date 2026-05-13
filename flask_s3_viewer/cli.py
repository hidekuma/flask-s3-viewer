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

    def handle(self) -> None:
        args: argparse.Namespace = self.parser.parse_args()

        # v1.0: templates were unified — copy the single bundled templates
        # directory verbatim. The legacy ``--template base|mdl`` switch is
        # gone (deprecation note in changelog / migration guide).
        file_path = os.path.dirname(os.path.abspath(__file__))
        template_path: str = args.path
        origin_template_path = os.path.join(
            file_path,
            'blueprints',
            FIXED_TEMPLATE_FOLDER,
        )

        if os.path.exists(template_path):
            click.echo(
                '\n {} : Already exists template directory ({}).'.format(
                    click.style(
                        "Failed",
                        fg="red",
                        bold=True,
                    ),
                    os.path.abspath(template_path),
                )
            )
        else:
            shutil.copytree(origin_template_path, template_path)
            click.echo(
                '\n {} : Template successfully created. ({})'.format(
                    click.style(
                        "Success",
                        fg="green",
                        bold=True,
                    ),
                    os.path.abspath(template_path),
                )
            )


def handle() -> None:
    cli = FlaskS3ViewerCli()
    cli.handle()


if __name__ == "__main__":
    handle()
