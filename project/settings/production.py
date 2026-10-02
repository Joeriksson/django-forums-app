from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False


# Comma-separated hosts the app is served on, e.g. 'forum.example.com'
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS]

# Links in emails are built from this, so refuse to start without a usable value
SITE_URL = os.environ.get('DJANGO_SITE_URL', '').strip().rstrip('/')
_site_url = urlsplit(SITE_URL)
if _site_url.scheme != 'https' or not _site_url.netloc or _site_url.path or _site_url.query:
    raise ImproperlyConfigured(
        'Set DJANGO_SITE_URL to the address of the site, with https and without a path, '
        f'e.g. https://forum.example.com (got {SITE_URL!r}).'
    )

# SMTP when host and credentials are set. Refuse to start otherwise, unless
# DJANGO_EMAIL_CONSOLE=true opts in to printing mail to the console.
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
if EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
elif env_bool('DJANGO_EMAIL_CONSOLE'):
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    missing = [
        name
        for name in ('EMAIL_HOST', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD')
        if not os.environ.get(name)
    ]
    raise ImproperlyConfigured(
        f'Missing SMTP settings: {", ".join(missing)}. '
        'Set them, or set DJANGO_EMAIL_CONSOLE=true to print mail to the console.'
    )

# SMTP servers usually only accept senders that belong to the account
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or DEFAULT_FROM_EMAIL
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = True
# Start low; raise to 31536000 (and consider preload) once HTTPS is stable
SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', 3600))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS')
SECURE_HSTS_PRELOAD = env_bool('DJANGO_SECURE_HSTS_PRELOAD')
# Both flags above are deliberate opt-ins, so check --deploy (run in CI) doesn't warn about them
SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021']
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# One reverse proxy in front of the app: allauth takes the visitor's address from the last
# X-Forwarded-For entry, the one that proxy added. Without this its rate limits (failed
# logins, signups, password resets) would count every visitor as the proxy.
ALLAUTH_TRUSTED_PROXY_COUNT = 1
# The same for the API's throttles
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 1}
