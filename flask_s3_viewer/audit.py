"""Audit logging for flask_s3_viewer S3 CRUD actions.

Emits a single structured log line per blueprint action
(``list``/``download``/``upload``/``delete``/``presign``) with the
authenticated user, HTTP status, client IP, User-Agent, and exception
message when applicable.

Activation
----------
The ``flask_s3_viewer.audit`` logger is always present; the host
application controls verbosity, propagation, and handlers via the
standard ``logging`` API. No constructor flag toggles it on/off — set
``logging.getLogger('flask_s3_viewer.audit').setLevel(...)`` or
``.disabled = True`` to silence it.

Record shape
------------
Each call to :func:`emit` produces one record whose ``extra`` dict
carries:

  - ``action`` — one of ``list``/``download``/``upload``/``delete``/``presign``
  - ``namespace`` — the viewer namespace this request landed on
  - ``key`` — the canonical S3 key / prefix touched (``''`` for listings
    that operate on the namespace root)
  - ``user`` — authenticated email or ``"anonymous"``
  - ``result`` — ``ok`` / ``denied`` / ``error``
  - ``status_code`` — HTTP status emitted to the client
  - ``client_ip`` — ``request.remote_addr`` or ``''`` outside a request
  - ``user_agent`` — capped at :data:`MAX_UA_LEN`, sanitised
  - ``error`` — present only when an exception was attached

Log injection is defended at this layer: newline / carriage return /
tab and other ASCII control bytes inside user-controllable fields
(key/email/UA/error) are escaped to ``\\x##``.
"""
from __future__ import annotations

import logging
from typing import Any

from flask import has_request_context, request

logger = logging.getLogger('flask_s3_viewer.audit')

# A genuine User-Agent rarely exceeds 256 bytes; capping defends against
# log-store amplification when an attacker sends a multi-MB UA header.
MAX_UA_LEN = 256

# Same cap for free-form fields that may carry attacker-controlled
# payloads — keep records bounded.
_MAX_FIELD_LEN = 1024


def _sanitize(value: Any, limit: int | None = None) -> str:
    """Escape ASCII control bytes and optionally truncate.

    Newlines / CRs / tabs in any user-controllable field (key, email,
    UA, exception message) would otherwise let an attacker forge a
    log entry by smuggling a fake row into a single record. We
    backslash-escape the whole control range (``\\x00``..``\\x1f`` plus
    ``\\x7f``) so the on-disk line stays a single physical row.
    """
    if value is None:
        return ''
    s = str(value)
    out: list[str] = []
    for ch in s:
        code = ord(ch)
        if code < 0x20 or code == 0x7f:
            out.append(f'\\x{code:02x}')
        else:
            out.append(ch)
    result = ''.join(out)
    if limit is not None and len(result) > limit:
        result = result[:limit] + '...'
    return result


def _level_for(result: str) -> int:
    if result == 'denied':
        return logging.WARNING
    if result == 'error':
        return logging.ERROR
    return logging.INFO


def emit(
    action: str,
    namespace: str | None,
    key: str | None,
    user: str | None,
    result: str,
    status_code: int,
    exc: BaseException | None = None,
) -> None:
    """Emit one audit record for a single blueprint action.

    Callers MUST pass the canonical ``key`` (post-prefixer) when one
    exists so the audit trail uses the same identifier the S3 layer
    saw. ``user`` of ``None`` is normalised to ``"anonymous"``.

    Public API
    ----------
    This function is part of the v1.x public surface — host
    integrations may ``from flask_s3_viewer.audit import emit`` to
    record extra audit lines for non-CRUD operations they layer on
    top of the viewer (e.g. a custom admin route, a bulk-tagging
    cron). Calling convention:

      - ``action`` SHOULD be one of the ``flask_s3_viewer.auth.ACTION_*``
        constants. Custom action strings are sanitised and accepted,
        but downstream filters that key off ``record.action`` will
        not recognise them.
      - ``key`` MUST be pre-normalised by the caller (post-prefixer)
        when one exists.
      - ``result`` drives the log level — ``ok``→INFO, ``denied``→
        WARNING, ``error``→ERROR.
      - When called outside a Flask request context (e.g. from a
        background worker), ``client_ip`` and ``user_agent`` are
        emitted as empty strings — the rest of the record is intact.

    The signature is stable across the v1.x line; new keyword
    arguments may be added but existing positions / names will not
    change without a major version bump.
    """
    safe_key = _sanitize(key, limit=_MAX_FIELD_LEN)
    safe_user = _sanitize(user or 'anonymous', limit=_MAX_FIELD_LEN)
    safe_namespace = _sanitize(namespace, limit=_MAX_FIELD_LEN)
    safe_action = _sanitize(action, limit=64)
    safe_result = _sanitize(result, limit=32)

    client_ip = ''
    user_agent = ''
    if has_request_context():
        client_ip = _sanitize(request.remote_addr, limit=64)
        user_agent = _sanitize(
            request.headers.get('User-Agent', ''),
            limit=MAX_UA_LEN,
        )

    error_msg = ''
    if exc is not None:
        error_msg = _sanitize(
            f'{exc.__class__.__name__}: {exc}',
            limit=_MAX_FIELD_LEN,
        )

    extra: dict[str, Any] = {
        'action': safe_action,
        'namespace': safe_namespace,
        'key': safe_key,
        'user': safe_user,
        'result': safe_result,
        'status_code': int(status_code) if status_code is not None else 0,
        'client_ip': client_ip,
        'user_agent': user_agent,
    }
    if error_msg:
        extra['error'] = error_msg

    message = (
        f'action={safe_action} namespace={safe_namespace} '
        f'key={safe_key} user={safe_user} '
        f'result={safe_result} status={extra["status_code"]}'
    )
    if error_msg:
        message = f'{message} error={error_msg}'

    # Keep user-supplied bytes out of the % format string — pass the
    # whole composed message as one positional arg.
    logger.log(_level_for(result), '%s', message, extra=extra)
