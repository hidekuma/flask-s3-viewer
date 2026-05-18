"""Stand-alone audit logging example for flask-s3-viewer.

Copy the ``configure_audit_logger`` call into your own app's startup
to start auditing. The block is intentionally self-contained — no
other example file imports from it.

The ``flask_s3_viewer.audit`` logger emits one record per S3 CRUD
action (list / download / upload / delete / presign). Every record
carries these LogRecord extras:

    action / namespace / key / user / result / status_code /
    client_ip / user_agent / request_id (+ error on failure)

Multi-file requests emit one row per file. All rows from the same
Flask request share one ``request_id`` (8 hex chars), so plaintext
greps can group them, e.g. ``grep "req=a1b2c3d4" audit.log``.

Drop this file's body into your app's startup (after ``logging.basicConfig``
or whatever root logging your host already does) and adjust the
handler / formatter to taste — ``FileHandler`` with rotation, a JSON
formatter via ``python-json-logger``, a Loki/Fluent Bit sink, etc.
"""

from __future__ import annotations

import logging


class DemoUserRedactFilter(logging.Filter):
    """Cheap email-tail redaction for the demo.

    Production deployments should swap this out for the redaction
    policy that matches their compliance requirements — see
    ``docs/source/usage/configuration.rst`` for a ``RedactFilter`` /
    ``KeyErrorRedactFilter`` reference set.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        user = getattr(record, "user", None)
        if user and "@" in user:
            local, domain = user.split("@", 1)
            record.user = f"{local[:2]}***@{domain}"
        return True


def configure_audit_logger(
    *,
    level: int = logging.INFO,
    propagate: bool = True,
    redact_user_emails: bool = True,
) -> logging.Logger:
    """Attach a ``StreamHandler`` to ``flask_s3_viewer.audit`` and return it.

    Parameters
    ----------
    level
        Audit logger level. ``logging.INFO`` is the recommended default;
        denied (401/403) records emit at ``WARNING`` and exceptions at
        ``ERROR`` so they survive higher thresholds too.
    propagate
        When ``True`` (default) audit records also reach the host's root
        logger. Set ``False`` if you want the audit stream completely
        isolated from your application logs.
    redact_user_emails
        Install :class:`DemoUserRedactFilter` so emails appear as
        ``jo***@example.com`` in the demo output. Turn off (or replace
        with your own filter) for production.
    """
    audit_logger = logging.getLogger("flask_s3_viewer.audit")
    audit_logger.setLevel(level)
    audit_logger.propagate = propagate

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "AUDIT %(asctime)s %(levelname)s "
            "action=%(action)s namespace=%(namespace)s "
            "key=%(key)s user=%(user)s result=%(result)s "
            "status=%(status_code)s req=%(request_id)s "
            "ip=%(client_ip)s",
        ),
    )
    audit_logger.addHandler(handler)

    if redact_user_emails:
        audit_logger.addFilter(DemoUserRedactFilter())

    return audit_logger


if __name__ == "__main__":
    # Quick smoke test — emits one anonymous record outside a Flask
    # request context. Run with: python -m example.audit_logging
    from flask_s3_viewer.audit import emit
    from flask_s3_viewer.auth import ACTION_LIST

    configure_audit_logger()
    emit(
        action=ACTION_LIST,
        namespace="demo",
        key="demo/key",
        user="alice@example.com",
        result="ok",
        status_code=200,
    )
