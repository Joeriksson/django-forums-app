from project.settings.base import *

# staticfiles/ only exists in the built image (collectstatic in the Dockerfile). Here WhiteNoise
# serves from the source directories, so don't look for it.
STATIC_ROOT = None
# Plain storage: the hashed names and their manifest only exist after collectstatic
STORAGES = {**STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}

DEBUG = True

INSTALLED_APPS += [
    'debug_toolbar',
]

MIDDLEWARE += [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEBUG_TOOLBAR_CONFIG = {
    'JQUERY_URL': '',
}


# Django-debug-toolbar
import socket
hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
INTERNAL_IPS = [ip[:-1] + "1" for ip in ips]