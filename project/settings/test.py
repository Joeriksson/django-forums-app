from project.settings.base import *

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