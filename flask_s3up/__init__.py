from .blueprints.route import blueprint as router

class FlaskS3Up:
    def __init__(self, app=None, config=None):
        if app:
            self.init_app(app, config)

    def init_app(self, app, config=None):
        if config:
            app.config.update(config)
        app.config.setdefault('S3UP_SERVICE_POINT', None)
        app.config.setdefault('S3UP_IS_COMPATIBLE', False)
        app.config.setdefault('S3UP_VIEW_PATH', '/flask-s3up')
        app.config.setdefault('S3UP_OBJECT_HOSTNAME', '/')
        app.config.setdefault('S3UP_USE_CACHING', False)
        app.config.setdefault('S3UP_CACHE_DIR', None)
        app.config.setdefault('S3UP_TTL', 300)

        view_path = app.config['S3UP_VIEW_PATH']
        object_hostname = app.config['S3UP_OBJECT_HOSTNAME']

        if view_path:
            if not view_path.startswith('/'):
                view_path = f'/{view_path}'

        if object_hostname:
            if object_hostname.endswith('/'):
                app.config['S3UP_OBJECT_HOSTNAME'] = object_hostname[:-1]

        if app.config['S3UP_USE_CACHING'] and not app.config['S3UP_CACHE_DIR']:
            raise ValueError('have to set "S3UP_CACHE_DIR".')

        if app.config['S3UP_IS_COMPATIBLE'] and not app.config['S3UP_SERVICE_POINT']:
            raise ValueError('have to set "S3UP_SERVICE_POINT".')

        app.register_blueprint(router, url_prefix=view_path)
