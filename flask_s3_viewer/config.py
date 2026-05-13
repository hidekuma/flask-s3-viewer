from typing import Final

NAMESPACE: Final[str] = 'flask_s3_viewer'
# v1.0: templates were unified — SUPPORT_TEMPLATES (base/mdl) removed.
FIXED_TEMPLATE_FOLDER: Final[str] = 'templates'  # flask_s3_viewer's template folder
UPLOAD_TYPES: Final[list[str]] = ['default', 'presign']
