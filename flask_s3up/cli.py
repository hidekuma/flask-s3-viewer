import os
import shutil
import argparse
import textwrap
import click


TEMPLATE_PATH = 'templates'
class FlaskS3UpCli:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            prog="flask_s3up",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent("""\n
         ____  __     __   ____  __ _    ____  ____  _  _  ____
        (  __)(  )   / _\ / ___)(  / )  / ___)( __ \/ )( \(  _ \\
         ) _) / (_/\/    \\\___ \ )  (   \___ \ (__ () \/ ( ) __/
        (__)  \____/\_/\_/(____/(__\_)  (____/(____/\____/(__)\n
        ============= Flask S3Up Command Line Tool ==============
        """)
        )
        self.parser.add_argument(
            "-t",
            "--template",
            type=str,
            default='skeleton',
            help="Get a base template for customzing view. mdl means material-design-lite and skeleton means not designed template)",
            choices=['skeleton', 'mdl']
        )

    def handle(self):
        args = self.parser.parse_args()

        if args.template:
            file_path = os.path.dirname(os.path.abspath(__file__))
            template_path = os.path.join(TEMPLATE_PATH, 'flask_s3up')
            base_template_path = os.path.join(
                file_path,
                'blueprints',
                'templates'
            )

            i = 1
            while True:
                i += 1
                if os.path.exists(template_path):
                    click.echo(
                        '\n {} : Already exists template directory ({}).'.format(
                            click.style(
                                "Failed",
                                fg="red",
                                bold=True
                            ),
                            os.path.abspath(template_path)
                        )
                    )
                    template_path = os.path.join(TEMPLATE_PATH, f'flask_s3up_{i}')
                else:
                    if args.template == 'mdl':
                        origin_template_path = os.path.join(
                            base_template_path,
                            'flask_s3up'
                        )
                    elif args.template == 'skeleton':
                        origin_template_path = os.path.join(
                            base_template_path,
                            'flask_s3up_skeleton'
                        )
                    shutil.copytree(origin_template_path, template_path)
                    click.echo(
                        '\n {} : Template successfully created. ({}). \
                        \n {} '.format(
                            click.style(
                                "Success",
                                fg="green",
                                bold=True
                            ),
                            os.path.abspath(template_path),
                            click.style(
                                f'- ex) mv {template_path} [your.flask.template_folder]/flask_s3up \
                                \n Move the created template to your flask\'s templates folder and rerun your python application, then customzie the template.',
                                bold=True
                            )
                        )
                    )
                    break

def handle():
    cli = FlaskS3UpCli()
    cli.handle()

if __name__ == "__main__":
    handle()
