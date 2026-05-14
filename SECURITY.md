# Security Policy

## Reporting

Report suspected vulnerabilities privately to the maintainers before public disclosure. Include:

- affected version
- deployment model and auth configuration
- reproduction steps or proof of concept
- expected impact

## Shared Responsibility

This library enforces S3 key-prefix isolation, optional auth hooks, and basic browser-facing hardening. Deployers are still responsible for:

- choosing least-privilege AWS credentials or IAM roles
- setting `SESSION_COOKIE_SECURE=True` in production when auth is enabled
- restricting allowed users via `permission_callback`, `allowed_emails`, or `allowed_domains`
- terminating TLS and protecting reverse proxies / CDN layers
- securing any writable cache directory permissions and placement

## Cache Format

The on-disk cache stores JSON payloads, not executable Python objects. Corrupt or legacy non-JSON cache files are treated as cache misses and removed.

## Supported Versions

Security fixes are targeted at the latest released 1.x line first.
