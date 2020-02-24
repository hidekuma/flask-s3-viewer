from .blueprints.route import blueprint as router

class FlaskS3Up:
    def __init__(self, app=None, config=None):
        if app:
            self.init_app(app, config)

    def init_app(self, app, config=None):
        if config:
            app.config.update(config)
        app.config.setdefault('S3UP_ROUTE_PATH', '/flask-s3up')
        app.config.setdefault('S3UP_OBJECT_HOSTNAME', '/')
        app.config.setdefault('S3UP_USE_CACHING', False)
        app.config.setdefault('S3UP_CACHE_DIR', None)

        route_path = app.config.get('S3UP_ROUTE_PATH', None)
        object_hostname = app.config.get('S3UP_OBJECT_HOSTNAME', None)

        if route_path:
            if not route_path.startswith('/'):
                route_path = f'/{route_path}'

        if object_hostname:
            if object_hostname.endswith('/'):
                app.config['S3UP_OBJECT_HOSTNAME'] = rreplace(object_hostname, '/', '', 1)

        app.register_blueprint(router, url_prefix=route_path)


def rreplace(s, old, new, occurrence):
    """
    to replace string from right

    :param s:
    :param old:
    :param new:
    :param occurrence:
    """
    li = s.rsplit(old, occurrence)
    return new.join(li)
