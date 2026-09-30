from project.settings.base import *

# staticfiles/ only exists in the built image (collectstatic in the Dockerfile). Here WhiteNoise
# serves from the source directories, so don't look for it.
STATIC_ROOT = None
# Plain storage: the hashed names and their manifest only exist after collectstatic
STORAGES = {**STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}

DEBUG = False

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Use in-memory cache for tests so no Redis connection is required
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Provide dummy GitHub OAuth app credentials so allauth 0.61+ can resolve the
# provider without needing a SocialApp database record (required for signup template tests)
SOCIALACCOUNT_PROVIDERS = {
    'github': {
        'APP': {
            'client_id': 'test-client-id',
            'secret': 'test-secret',
            'key': '',
        }
    }
}
# Signup is closed by default; tests of the closed state switch it off themselves
SIGNUP_OPEN = True
