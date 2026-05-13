"""Legacy re-export for ``FlaskS3ViewerViewRouter``.

The blueprint is registered automatically by :meth:`FlaskS3Viewer.init_app`
(v1.0+), so this module is no longer required for normal usage. It is kept as
a backward-compatibility surface for external code that imported the symbol
directly. Targeted for removal in the v1.x cleanup phase (A7).
"""
from .blueprints.view import blueprint as FlaskS3ViewerViewRouter  # noqa: F401

__all__ = ["FlaskS3ViewerViewRouter"]
