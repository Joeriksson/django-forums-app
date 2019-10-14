from .base import *

DEBUG = False

# Add any host where your app is published
ALLOWED_HOSTS = ['.herokuapp.com', 'localhost', '127.0.0.1', '0.0.0.0']

DEFAULT_FROM_EMAIL = 'noreply@email.com'

# Sendgrid
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_PASSWORD = os.environ['SENDGRID_PASSWORD']
EMAIL_HOST_USER = os.environ['SENDGRID_USERNAME']

SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')