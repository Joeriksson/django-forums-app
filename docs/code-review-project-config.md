# Code Review: `project/` Package (Settings, Celery, URLs, Mail Helper)

**Date:** 2026-09-24
**Scope:** Full review (not only recent changes) of the `project/` package, plus the deployment files that directly feed its cache and Celery configuration.

## Code Review Summary

- **Files Reviewed**:
  - `project/__init__.py`
  - `project/settings/__init__.py` (empty)
  - `project/settings/base.py`
  - `project/settings/development.py`
  - `project/settings/production.py`
  - `project/settings/test.py`
  - `project/celery.py`
  - `project/urls.py`
  - `project/utils.py`
  - `project/views.py`
  - `project/wsgi.py`
  - Related context: `manage.py`, `forums/tasks.py`, `render.yaml`, `docker-compose-prod.yml`, `.github/workflows/django.yml`, `pyproject.toml`
  - Note: `project/settings/ci.py` and `project/asgi.py` **do not exist**, even though `CLAUDE.md` lists `ci.py`. CI selects its database through `ENVIRONMENT=CI` inside `base.py` and runs tests with `project.settings.test`.
- **Total Issues Found**: 22 (Critical: 3 | Important: 9 | Minor: 10)
- **Overall Assessment**: The settings split (base/development/production/test) is a good foundation. Several details are already right: `SecurityMiddleware` comes first, WhiteNoise and CORS middleware are in the correct order, cookies are marked secure in production, Celery accepts JSON only, and tests use an in-memory cache and a fast hasher. However, production hardening has real problems. HSTS is effectively off, production sends no email at all, and the Redis instance that serves as cache, broker and result backend is exposed and shared. Several settings are dead or ignored, and nothing warns about it.

Secrets policy: no secret values are reproduced in this report. The only credential-like literals found are the local/CI Postgres defaults and the dummy CI/test values. They are flagged as a pattern and not repeated.

---

## Critical Issues

### Issue #1: `SECURE_HSTS_SECONDS = True` means HSTS lasts 1 second
- **Location**: `project/settings/production.py:24-26`
- **Category**: Security
- **Severity**: Critical
- **Explanation**: `SECURE_HSTS_SECONDS` expects an integer number of seconds. `True` is an `int` subclass equal to `1`, so the header sent is `Strict-Transport-Security: max-age=1; includeSubDomains; preload`. Browsers forget the HSTS policy after one second. That leaves users open to SSL-stripping on their next visit, which is exactly what HSTS exists to prevent. The `preload` flag is also invalid here, because the HSTS preload list requires `max-age` of at least 31536000 (one year). Django's `check --deploy` (W004/W005/W021) will not flag this, because the value is technically non-zero.
- **Current Code**:
```python
SECURE_HSTS_SECONDS = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```
- **Improved Version**:
```python
# Roll out gradually: start small, verify HTTPS works everywhere (including all
# subdomains, because includeSubDomains is set), then raise to one year.
# Only enable PRELOAD once you are sure; getting off the preload list is slow.
SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 3600))  # target: 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'false').lower() == 'true'
```

### Issue #2: Production uses the console email backend, so no email is ever delivered
- **Location**: `project/settings/production.py:12-19`; `project/utils.py:1-12`; `project/settings/base.py:173-176`
- **Category**: Best Practice / Reliability
- **Severity**: Critical
- **Explanation**: `EMAIL_BACKEND` in production is `console.EmailBackend`. Every email is printed to the gunicorn/Celery stdout and nothing is sent. That affects thread-subscription notifications (`forums/tasks.py` -> `project/utils.send_mail`), the welcome email, allauth password-reset and email-confirmation mails, and `mail_admins` error reports to `ADMINS`. Users cannot recover their accounts. The code also logs recipient addresses and reset links in plain text, and those links are account-takeover tokens. `CLAUDE.md` and the CI workflow refer to SendGrid (`SENDGRID_USERNAME`/`SENDGRID_PASSWORD`), but no code reads those variables. The commented-out block refers to Mailgun instead.
- **Current Code**:
```python
# Sendgrid
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.mailgun.org'
# ...
```
- **Improved Version**:
```python
# SendGrid over SMTP (username is literally "apikey" for SendGrid API-key auth).
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ['SENDGRID_USERNAME']      # fail fast if missing
EMAIL_HOST_PASSWORD = os.environ['SENDGRID_PASSWORD']
EMAIL_TIMEOUT = 10  # never let a slow SMTP server hang a worker
```

### Issue #3: Production Redis is published on the host with no authentication
- **Location**: `docker-compose-prod.yml:23-26` (feeds `project/settings/base.py:283-301`)
- **Category**: Security
- **Severity**: Critical (if this compose file runs on an internet-reachable host)
- **Explanation**: `ports: - 6379:6379` binds Redis on all host interfaces, and the URL built in `base.py` has no password. On a public host, anyone can connect. They can read or poison the cache, which holds cached Thread/Post querysets, inject or drop Celery messages, or use well-known Redis `CONFIG SET` tricks to write files on the host. The web and Celery containers reach Redis over the internal compose network (`redis://redis:6379/0`), so publishing the port is not needed.
- **Current Code**:
```yaml
  redis:
    image: redis:alpine
    ports:
      - 6379:6379
```
- **Improved Version**:
```yaml
  redis:
    image: redis:alpine
    # No "ports:" -- only reachable from other services on the compose network.
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]
# ...and set REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0 in .env
```

---

## Important Issues

### Issue #4: Production `ALLOWED_HOSTS` is too broad and includes local hosts
- **Location**: `project/settings/production.py:6-8`
- **Category**: Security
- **Severity**: Important
- **Explanation**: `'.herokuapp.com'` matches every Heroku app, not only this one. `'localhost'`, `'127.0.0.1'` and `'0.0.0.0'` do not belong in a production allow-list. `ALLOWED_HOSTS` is Django's defence against Host-header poisoning, which matters because absolute URLs in emails, such as password-reset and notification links, can be built from the request host. The list should name only the real public hostnames. The Render hook is also duplicated from `base.py:17-19`, and `production.py` then overwrites the base list anyway.
- **Current Code**:
```python
ALLOWED_HOSTS = ['.herokuapp.com', 'localhost', '127.0.0.1', '0.0.0.0']
if RENDER_EXTERNAL_HOSTNAME := os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
```
- **Improved Version**:
```python
# Comma-separated list of exact public hostnames, e.g. "forum.example.com"
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()
]
if RENDER_EXTERNAL_HOSTNAME := os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
```

### Issue #5: Sentry is configured to send PII, and the DSN is built from possibly-`None` values
- **Location**: `project/settings/base.py:265-279`
- **Category**: Security / Privacy
- **Severity**: Important
- **Explanation**: `send_default_pii=True` sends user IDs, emails, usernames, IP addresses, cookies and request bodies to a third party (Sentry). On a public forum this has GDPR implications and may leak session cookies or form contents into error reports. Separately, if `SENTRY_KEY`/`SENTRY_PROJECT` are unset, the DSN becomes a literal `https://None@sentry.io/None`, and errors are silently lost. Sentry init also lives in `base.py` and is gated on an env var rather than living in `production.py`.
- **Current Code**:
```python
if os.environ.get('ENVIRONMENT') == 'production':
    ...
    sentry_sdk.init(
        dsn=f'https://{SENTRY_KEY}@sentry.io/{SENTRY_PROJECT}',
        integrations=[DjangoIntegration()],
        send_default_pii=True
    )
```
- **Improved Version**:
```python
# In production.py
if SENTRY_DSN := os.environ.get('SENTRY_DSN'):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment='production',
        send_default_pii=False,  # opt in deliberately, not by default
    )
```

### Issue #6: Hardcoded database credentials, duplicated in two branches
- **Location**: `project/settings/base.py:89-111`, `project/settings/base.py:209-212`
- **Category**: Security / Readability
- **Severity**: Important
- **Explanation**: Superuser-level Postgres credentials are hardcoded in `base.py`, which every environment, production included, inherits. They are only overridden if `DATABASE_URL` happens to be set. The production compose file does not set `DATABASE_URL` itself, so a production container would silently use these defaults. The two branches differ only in `HOST`. `dj_database_url` is also imported in the middle of the file, and the "Heroku" comment is stale.
- **Current Code**:
```python
if os.environ.get('ENVIRONMENT') == "CI":
    DATABASES = {'default': {... 'USER': ..., 'PASSWORD': ..., 'HOST': 'localhost', ...}}
else:
    DATABASES = {'default': {... 'USER': ..., 'PASSWORD': ..., 'HOST': 'db', ...}}
...
import dj_database_url
db_from_env = dj_database_url.config(conn_max_age=500)
DATABASES['default'].update(db_from_env)
```
- **Improved Version**:
```python
import dj_database_url  # at top of file

# DATABASE_URL is required; dev/CI provide their own value via .env / workflow env.
DATABASES = {
    'default': dj_database_url.config(
        env='DATABASE_URL',
        conn_max_age=600,
        conn_health_checks=True,  # Django 4.1+: drop dead persistent connections
    )
}
```

### Issue #7: Cache, Celery broker and Celery result backend share one Redis database
- **Location**: `project/settings/base.py:283-301`
- **Category**: Performance / Reliability
- **Severity**: Important
- **Explanation**: All three use the same `redis_host`, which is DB `0`. A `cache.clear()` (django-redis runs `FLUSHDB`) will also wipe queued Celery tasks and results. If the Redis instance hits `maxmemory` with an eviction policy suited to caching, queued notification tasks can be evicted. The cache has no `KEY_PREFIX` either, so keys like `thread_objects_forum_1` collide across any other app that uses the same Redis. The f-strings on lines 286/288 contain no placeholders.
- **Current Code**:
```python
if os.environ.get('REDIS_URL') is not None:
    redis_host = os.environ.get('REDIS_URL')
elif os.environ.get('REDIS_LOCALHOST'):
    redis_host = f'redis://localhost:6379/0'
else:
    redis_host = f'redis://redis:6379/0'
...
CELERY_BROKER_URL = redis_host
CELERY_RESULT_BACKEND = redis_host
```
- **Improved Version**:
```python
_default_redis = 'redis://localhost:6379' if os.environ.get('REDIS_LOCALHOST') else 'redis://redis:6379'
REDIS_BASE_URL = os.environ.get('REDIS_BASE_URL', _default_redis)

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ.get('CACHE_REDIS_URL', f'{REDIS_BASE_URL}/0'),
        'KEY_PREFIX': 'forums',
        'OPTIONS': {'CLIENT_CLASS': 'django_redis.client.DefaultClient'},
    }
}
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', f'{REDIS_BASE_URL}/1')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', f'{REDIS_BASE_URL}/2')
```

### Issue #8: `CELERY_ALWAYS_EAGER` is the pre-4.0 setting name and is ignored with the `CELERY` namespace
- **Location**: `project/settings/base.py:305-306`, `project/celery.py:7`
- **Category**: Best Practice / Bug
- **Severity**: Important
- **Explanation**: `celery.py` loads settings with `namespace='CELERY'`. Celery therefore maps `CELERY_<NEW_NAME>` onto its lowercase settings. The new name for eager mode is `task_always_eager`, so the Django setting must be `CELERY_TASK_ALWAYS_EAGER`. `CELERY_ALWAYS_EAGER` is the old Celery 3 name (Celery >= 5.5 is pinned in `pyproject.toml`), so the "run tasks synchronously outside production" behaviour described in `CLAUDE.md` does not happen. In development, tasks go to the broker, which only works if a worker is running. Eager mode is also gated on the `ENVIRONMENT` env var rather than the settings module (see Issue #13), so the decision belongs in `development.py`/`test.py`.
- **Current Code**:
```python
if not os.environ.get('ENVIRONMENT') == 'production':
    CELERY_ALWAYS_EAGER = True
```
- **Improved Version**:
```python
# development.py and test.py (not base.py)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True  # surface task exceptions in dev/tests
```

### Issue #9: Entry points default to different settings modules, and `manage.py` defaults to `base`
- **Location**: `manage.py:8`, `project/wsgi.py:14`, `project/celery.py:4`, `project/settings/base.py:13-17`
- **Category**: Security / Best Practice
- **Severity**: Important
- **Explanation**: `manage.py` defaults to `project.settings.base`, which is not a runnable configuration. `DEBUG` is commented out, so it falls back to `False`, and `ALLOWED_HOSTS` is empty. `wsgi.py` and `celery.py` default to `production`. If an operator runs `manage.py migrate` or `createsuperuser` in production without `--settings`, the command runs against `base`, not `production`. Anything production-only is silently skipped, and a missing `DJANGO_SETTINGS_MODULE` goes unnoticed. The comment in `base.py` still points to the Django 2.2 checklist.
- **Current Code**:
```python
# manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings.base')
# wsgi.py / celery.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings.production')
```
- **Improved Version**:
```python
# manage.py: default to the developer-safe module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings.development')

# wsgi.py / celery.py: keep 'production', but in deployment always set
# DJANGO_SETTINGS_MODULE explicitly (Dockerfile ENV / render.yaml envVars)
# so every process agrees on one settings module.
```

### Issue #10: `ADMIN1`/`ADMIN2` parsing crashes when unset and leaves whitespace in emails
- **Location**: `project/settings/base.py:173-180`
- **Category**: Best Practice / Reliability
- **Severity**: Important
- **Explanation**: `os.environ.get('ADMIN1').split(',')` raises `AttributeError: 'NoneType' object has no attribute 'split'` at import time if the variable is missing. Every settings module inherits this, `test` included, so a fresh checkout cannot even run tests without these two variables. The documented format `Name, email@example.com` also yields `' email@example.com'` with a leading space. The design caps admins at exactly two. Leftover commented code adds noise.
- **Current Code**:
```python
ADMIN1 = tuple(os.environ.get('ADMIN1').split(','))
ADMIN2 = tuple(os.environ.get('ADMIN2').split(','))

ADMINS = [ADMIN1, ADMIN2]
# ADMINS.append(ADMIN1)
# ADMINS.append(ADMIN2)

# ADMINS = os.environ.get('ADMINS')
```
- **Improved Version**:
```python
def _parse_admin(value):
    """Parse 'Name, email@example.com' into ('Name', 'email@example.com')."""
    name, _, email = value.partition(',')
    return (name.strip(), email.strip())

ADMINS = [
    _parse_admin(os.environ[key])
    for key in ('ADMIN1', 'ADMIN2')
    if os.environ.get(key)
]
```

### Issue #11: The `send_mail` helper uses `print`, has no guard, and shadows Django's `send_mail`
- **Location**: `project/utils.py:1-12` (caller: `forums/tasks.py:18-26`)
- **Category**: Readability / Best Practice
- **Severity**: Important
- **Explanation**:
  1. `print('email sent ####################')` runs in Celery workers. It goes to unstructured stdout, prints even if nothing was actually sent (see Issue #2), and gives no context such as the subject or recipient count. Use `logging`.
  2. There is no guard for an empty `bcc` list. Django silently sends nothing when there are no recipients, which hides upstream bugs.
  3. `EmailMultiAlternatives` is used, but no HTML alternative is ever attached. Plain `EmailMessage` is sufficient.
  4. The function name `send_mail` shadows `django.core.mail.send_mail` and has a different signature. That is easy to import by mistake.
  5. The docs say the helper uses SendGrid, but it is only a thin wrapper over Django's configured backend.
  6. Large subscriber lists all go in one SMTP transaction. Most providers cap recipients per message, and SendGrid's limit is 1000.
  7. The caller hardcodes `from_email='info@wildvasa.com'` instead of using `settings.DEFAULT_FROM_EMAIL`.
- **Current Code**:
```python
from django.core.mail import EmailMultiAlternatives


def send_mail(subject, from_email, bcc, text_content):

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, bcc=bcc
    )

    msg.send()

    print('email sent ####################')
```
- **Improved Version**:
```python
import logging

from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)

MAX_RECIPIENTS_PER_MESSAGE = 500  # stay well under provider BCC limits


def send_bcc_mail(subject, text_content, bcc, from_email=None):
    """Send a plain-text email to many recipients via BCC, in batches.

    Returns the number of messages successfully sent.
    """
    recipients = list(bcc)
    if not recipients:
        logger.info('send_bcc_mail skipped: no recipients (subject=%r)', subject)
        return 0

    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    sent = 0
    for start in range(0, len(recipients), MAX_RECIPIENTS_PER_MESSAGE):
        batch = recipients[start:start + MAX_RECIPIENTS_PER_MESSAGE]
        sent += EmailMessage(
            subject=subject, body=text_content, from_email=from_email, bcc=batch
        ).send()

    logger.info('Sent %d message(s) to %d recipient(s): %r', sent, len(recipients), subject)
    return sent
```

### Issue #12: The Render blueprint never supplies the Redis URL that settings actually read
- **Location**: `render.yaml:11-41` (consumed by `project/settings/base.py:283-301`)
- **Category**: Best Practice / Reliability
- **Severity**: Important
- **Explanation**: `base.py` builds the cache, broker and result-backend URL from `REDIS_URL`/`REDIS_LOCALHOST`. `render.yaml` only sets `CELERY_BROKER_URL`. On Render, the Django cache therefore falls back to `redis://redis:6379/0`, a Docker-compose hostname that does not exist there, and cached views will error. The web service also references Redis with `fromDatabase` (lines 22-25) instead of `fromService`. The worker runs `celery --app tasks`, but no top-level `tasks` module exists; the Celery app is `project`. Neither service sets `DJANGO_SETTINGS_MODULE` or `ENVIRONMENT`, so Sentry and non-eager Celery never activate there.
- **Current Code**:
```yaml
      - key: CELERY_BROKER_URL
        fromDatabase:
          name: forum-app-redis
          type: redis
          property: connectionString
...
    startCommand: "celery --app tasks worker --loglevel info --concurrency 4"
```
- **Improved Version**:
```yaml
      - key: REDIS_URL
        fromService:
          name: forum-app-redis
          type: redis
          property: connectionString
      - key: DJANGO_SETTINGS_MODULE
        value: project.settings.production
      - key: ENVIRONMENT
        value: production
...
    startCommand: "celery --app project worker --loglevel info --concurrency 4"
```

---

## Minor Issues

### Issue #13: Environment behaviour is controlled by two independent switches
- **Location**: `project/settings/base.py:90`, `base.py:265`, `base.py:305`; `project/__init__.py:4-6`
- **Category**: Best Practice / Readability
- **Severity**: Minor
- **Explanation**: `base.py` branches on `ENVIRONMENT` for the DB host, Sentry and Celery eager mode. `project/__init__.py` branches on a different variable (`CI`). Meanwhile `DEBUG`, email and security headers depend on which settings module is loaded. Combinations like `settings.production` with `ENVIRONMENT=development` (eager Celery, no Sentry, on prod) are possible and hard to spot. Environment-specific decisions belong in the environment's settings module.
- **Current Code**:
```python
if os.environ.get('ENVIRONMENT') == "CI": ...
if os.environ.get('ENVIRONMENT') == 'production': ...   # Sentry
if not os.environ.get('ENVIRONMENT') == 'production':   # Celery eager
```
- **Improved Version**:
```python
# base.py: no ENVIRONMENT branches at all.
# development.py / test.py: CELERY_TASK_ALWAYS_EAGER = True
# production.py:           sentry_sdk.init(...)
# DB host differences:     supplied by DATABASE_URL per environment (Issue #6)
```

### Issue #14: `SECRET_KEY` does not fail fast when missing
- **Location**: `project/settings/base.py:11`
- **Category**: Security
- **Severity**: Minor
- **Explanation**: `os.environ.get('SECRET_KEY')` yields `None` when unset. Since Django 3.2, the "must not be empty" error only fires lazily, the first time something signs data. A misconfigured deploy can therefore boot, pass health checks, and fail on the first login or form POST. Indexing `os.environ` makes the failure immediate and obvious. No secret value is committed here, which is good. (CI uses a dummy value in `.github/workflows/django.yml`; that is acceptable for tests.)
- **Current Code**:
```python
SECRET_KEY = os.environ.get('SECRET_KEY')
```
- **Improved Version**:
```python
SECRET_KEY = os.environ['SECRET_KEY']  # KeyError at startup if missing
```

### Issue #15: The DRF API has no throttling, and the browsable API is enabled in production
- **Location**: `project/settings/base.py:196-207`
- **Category**: Security / Performance
- **Severity**: Minor
- **Explanation**: With no `DEFAULT_THROTTLE_CLASSES`, anonymous clients can hammer list endpoints. Those endpoints return nested serializers (Forum -> Threads -> Posts), which are expensive. Token-auth brute force is also unthrottled. The browsable HTML renderer is enabled by default in production too, which is extra attack surface and extra rendering cost.
- **Current Code**:
```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [...],
    'DEFAULT_AUTHENTICATION_CLASSES': [...],
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}
```
- **Improved Version**:
```python
REST_FRAMEWORK = {
    # ...existing keys...
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {'anon': '60/min', 'user': '300/min'},
}

# production.py
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = ['rest_framework.renderers.JSONRenderer']
```

### Issue #16: Localhost CORS origins also apply in production
- **Location**: `project/settings/base.py:324-327`
- **Category**: Security
- **Severity**: Minor
- **Explanation**: `http://localhost:3000` and `http://127.0.0.1:3000` are allowed cross-origin in every environment, production included. The risk is low because `CORS_ALLOW_CREDENTIALS` is not set. Still, dev-only origins should not ship to production, and the production list should come from configuration.
- **Current Code**:
```python
CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000"
]
```
- **Improved Version**:
```python
# base.py
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if o.strip()
]
# development.py
CORS_ALLOWED_ORIGINS += ["http://127.0.0.1:3000", "http://localhost:3000"]
```

### Issue #17: Dead, deprecated, or misnamed settings
- **Location**: `project/settings/production.py:21-22`; `project/settings/base.py:140`, `base.py:160`, `base.py:244-251`, `base.py:14-16`, `base.py:35-37`, `base.py:57`, `base.py:60`, `base.py:309-322`
- **Category**: Readability / Best Practice
- **Severity**: Minor
- **Explanation**: Several settings do nothing and give a false sense that something is configured:
  - `SECURE_BROWSER_XSS_FILTER` was removed in Django 4.0 and has no effect.
  - `X_FRAME_OPTIONS = 'DENY'` is already Django's default. It is harmless but redundant.
  - `USE_L10N` is deprecated in Django 4.x and removed in 5.0. It will break the upgrade.
  - `ACCOUNT_LOGOUT_REDIRECT` is not an allauth setting. The real name is `ACCOUNT_LOGOUT_REDIRECT_URL`, so this one is silently ignored. It only appears to work because the default is `/`.
  - `MARKDOWNX_MARKDOWN_EXTENSIONS_CONFIGS` belongs to django-markdownx, not martor, so it is ignored.
  - Commented-out `DEBUG`/`ALLOWED_HOSTS`/`rest_auth`/cache-middleware/Celery-beat blocks add noise. Git history preserves them.
- **Current Code**:
```python
SECURE_BROWSER_XSS_FILTER = True          # production.py:21
USE_L10N = True                           # base.py:140
ACCOUNT_LOGOUT_REDIRECT = 'home'          # base.py:160
MARKDOWNX_MARKDOWN_EXTENSIONS_CONFIGS = {...}  # base.py:244
```
- **Improved Version**:
```python
# production.py: delete SECURE_BROWSER_XSS_FILTER and X_FRAME_OPTIONS
# base.py:
ACCOUNT_LOGOUT_REDIRECT_URL = 'home'
# delete USE_L10N and MARKDOWNX_MARKDOWN_EXTENSIONS_CONFIGS
# (if codehilite config is wanted, martor's key is MARTOR_MARKDOWN_EXTENSION_CONFIGS)
```

### Issue #18: Martor @mentions render links to an unrelated third-party site
- **Location**: `project/settings/base.py:217`, `base.py:239`, `base.py:260`
- **Category**: Security / Best Practice
- **Severity**: Minor
- **Explanation**: The mention toolbar is disabled (`'mention': 'false'`), but the `martor.extensions.mention` markdown extension is still enabled. `MARTOR_MARKDOWN_BASE_MENTION_URL` is left at martor's sample value, `https://python.web.id/author/`. Any `@[username]` typed in a post therefore renders as a link to an external site the project does not control. Either remove the extension or point it at your own profile URL.
- **Current Code**:
```python
'martor.extensions.mention',    # to parse markdown mention
...
MARTOR_MARKDOWN_BASE_MENTION_URL = 'https://python.web.id/author/'
```
- **Improved Version**:
```python
# Remove 'martor.extensions.mention' from MARTOR_MARKDOWN_EXTENSIONS,
# or point mentions at an internal route:
MARTOR_MARKDOWN_BASE_MENTION_URL = '/users/'  # adjust to a real profile URL
```

### Issue #19: Sender addresses use a domain the project does not own, and `SERVER_EMAIL` is unset
- **Location**: `project/settings/base.py:189`, `project/settings/production.py:10` (and `forums/tasks.py:18`)
- **Category**: Best Practice
- **Severity**: Minor
- **Explanation**: `DEFAULT_FROM_EMAIL = 'noreply@email.com'` uses a real third-party domain. Once real sending is enabled (Issue #2), SPF/DKIM/DMARC will fail and mail will be rejected or land in spam. The value is duplicated in `production.py`. `SERVER_EMAIL`, the sender for `ADMINS` error mails, defaults to `root@localhost`. The task hardcodes yet another sender.
- **Current Code**:
```python
DEFAULT_FROM_EMAIL = 'noreply@email.com'
```
- **Improved Version**:
```python
# base.py only
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@localhost')
SERVER_EMAIL = os.environ.get('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
```

### Issue #20: `SECURE_PROXY_SSL_HEADER` is trusted even where gunicorn is exposed directly
- **Location**: `project/settings/production.py:23`, `production.py:30`; `docker-compose-prod.yml:8`, `docker-compose-prod.yml:13-14`
- **Category**: Security
- **Severity**: Minor
- **Explanation**: Trusting `X-Forwarded-Proto` is only safe when a proxy in front of Django always overwrites that header, as Render/Heroku routers do. The compose production setup publishes gunicorn on port 8000 with no proxy. A client can then send plain HTTP with `X-Forwarded-Proto: https`, bypass `SECURE_SSL_REDIRECT`, and Django will believe the request is secure. Either put a TLS-terminating proxy in front of gunicorn, or make this setting conditional on deployment.
- **Current Code**:
```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```
- **Improved Version**:
```python
# Only trust the header when explicitly told a trusted proxy is in front.
if os.environ.get('BEHIND_TLS_PROXY', 'true').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

### Issue #21: A Redis outage turns every cached page into a 500
- **Location**: `project/settings/base.py:290-298`, `base.py:281`
- **Category**: Performance / Reliability
- **Severity**: Minor
- **Explanation**: django-redis raises on connection errors by default. The cache is only an optimisation for Thread/Post querysets, so a Redis blip should fall back to the database rather than fail the request. No connect or socket timeouts are set either, so a hung Redis can stall gunicorn workers. `CACHE_MIDDLEWARE_ALIAS` is set, but the cache middleware is commented out.
- **Current Code**:
```python
'OPTIONS': {
    'CLIENT_CLASS': 'django_redis.client.DefaultClient',
}
```
- **Improved Version**:
```python
'OPTIONS': {
    'CLIENT_CLASS': 'django_redis.client.DefaultClient',
    'IGNORE_EXCEPTIONS': True,      # treat cache failures as cache misses
    'SOCKET_CONNECT_TIMEOUT': 2,
    'SOCKET_TIMEOUT': 2,
},
# and at module level:
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True
```

### Issue #22: Celery lacks basic production safeguards
- **Location**: `project/settings/base.py:300-306`; `docker-compose-prod.yml:30`
- **Category**: Performance / Reliability
- **Severity**: Minor
- **Explanation**:
  - No task time limits are set, so a hung SMTP connection can pin a worker forever.
  - `CELERY_RESULT_BACKEND` stores results nobody reads; `send_notifications_task` is fire-and-forget. That is wasted Redis writes.
  - Celery 5.3+ warns unless `broker_connection_retry_on_startup` is set explicitly.
  - The production worker runs at `-l DEBUG`, which is very noisy and can log message bodies containing subscriber email addresses.
- **Current Code**:
```python
CELERY_BROKER_URL = redis_host
CELERY_RESULT_BACKEND = redis_host
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
```
- **Improved Version**:
```python
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_IGNORE_RESULT = True               # nothing consumes results today
CELERY_TASK_SOFT_TIME_LIMIT = 60
CELERY_TASK_TIME_LIMIT = 90
CELERY_TASK_ACKS_LATE = True                   # redeliver if a worker dies mid-task
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# docker-compose-prod.yml: celery -A project worker -l INFO
```

---

## What Is Already Done Well

- `SecurityMiddleware` is first, `WhiteNoiseMiddleware` is second, and `CorsMiddleware` sits before `CommonMiddleware`. This is the documented, correct order (`base.py:53-66`).
- Production sets `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` and `SECURE_CONTENT_TYPE_NOSNIFF` (`production.py:23-29`).
- Celery accepts JSON only, which avoids pickle deserialization risk (`base.py:302-304`).
- The admin URL is configurable and non-default (`urls.py:10-14`), and the debug toolbar URLs are only mounted when `DEBUG` (`urls.py:30-35`).
- `static()` for media is a no-op when `DEBUG=False`, so it does not accidentally serve uploads in production (`urls.py:28`).
- Test settings use `LocMemCache` and a fast hasher, and provide dummy OAuth config, so the tests are hermetic (`test.py`).
- `UserProfileUpdate` correctly combines `LoginRequiredMixin` with an ownership `test_func` (`views.py:9-22`).

## Quick Wins

1. **Fix HSTS** (`production.py:24`): replace `True` with a real integer, and ramp to `31536000` before keeping `SECURE_HSTS_PRELOAD`. This is a one-line change that turns HSTS on for real.
2. **Configure real email delivery in production** (`production.py:13`): switch to the SMTP backend with the existing `SENDGRID_*` variables and a sender domain you own. Notifications, password resets and admin error mails currently go nowhere.
3. **Lock down and separate Redis** (`docker-compose-prod.yml:25-26`, `base.py:283-301`): stop publishing port 6379, add a password, and give the cache and Celery broker separate DB indexes. Also rename `CELERY_ALWAYS_EAGER` to `CELERY_TASK_ALWAYS_EAGER` so eager mode actually works in dev and tests.
