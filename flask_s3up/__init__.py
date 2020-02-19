from .blueprints.route import blueprint as router
from .blueprints.api import blueprint as apirouter

class FlaskS3Up:
    def __init__(self, app=None, config=None):
        if app:
            self.init_app(app, config)

    def init_app(self, app, config=None):
        if config:
            app.config.update(config)
        app.config.setdefault('PATH', '/flask-s3up')
        app.config.setdefault('API_PATH', '/flask-s3up-api')
        path = app.config.get('PATH', None)
        api_path = app.config.get('API_PATH', None)
        if path:
            if not path.startswith('/'):
                path = f'/{path}'
        if api_path:
            if not api_path.startswith('/'):
                api_path = f'/{path}'

        app.register_blueprint(router, url_prefix=path)
        app.register_blueprint(apirouter, url_prefix=api_path)

