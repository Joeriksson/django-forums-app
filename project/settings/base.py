import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes')


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
# One os.path.dirname added after moving this file into a sub folder of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = os.environ.get('DEBUG')

#ALLOWED_HOSTS = ['127.0.0.1']
ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third party
    'rest_framework',
    'rest_framework.authtoken',
    # 'rest_auth',
    'corsheaders',
    # 'rest_auth.registration',
    'crispy_forms',
    'crispy_bootstrap4',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.github',
    'allauth.mfa',
    # Local
    'users.apps.UsersConfig',
    'pages.apps.PagesConfig',
    'forums.apps.ForumsConfig',
    'api.apps.ApiConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # 'django.middleware.cache.UpdateCacheMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.cache.FetchFromCacheMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    # Before the middleware and views that refuse requests, so it sees their responses
    'users.audit.DeniedRequestLogMiddleware',
    'users.security.StaffMFAMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'

# Database
if os.environ.get('ENVIRONMENT') == "CI":
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'postgres',
            'USER': 'postgres',
            'PASSWORD': 'postgres',
            'HOST': 'localhost',
            'PORT': 5432
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'postgres',
            'USER': 'postgres',
            'PASSWORD': 'postgres',
            'HOST': 'db',
            'PORT': 5432
        }
    }

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static'), ]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]
# collectstatic (in the Dockerfile) adds a content hash to each file name and gzips it, so
# browsers can cache static files forever and still get new ones after a deploy. A
# {% static %} path missing from the manifest raises an error when DEBUG is False.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# custom settings
AUTH_USER_MODEL = 'users.CustomUser'
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

LOGIN_REDIRECT_URL = 'home'
ACCOUNT_LOGOUT_REDIRECT_URL = 'home'

CRISPY_TEMPLATE_PACK = 'bootstrap4'

# django-allauth config
SITE_ID = 1

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)


def admins_from_env():
    """
    Return ADMINS from DJANGO_ADMINS, a comma-separated list of email addresses.
    Django's default logging mails them the traceback of every 500 when DEBUG is False.
    """
    addresses = [
        address.strip()
        for address in os.environ.get('DJANGO_ADMINS', '').split(',')
        if address.strip()
    ]
    for address in addresses:
        if '@' not in address:
            raise ImproperlyConfigured(
                f'DJANGO_ADMINS must be email addresses separated by commas, got {address!r}'
            )
    # Django 5.2 expects (name, address) pairs but never uses the name.
    # Django 6 takes plain addresses: return `addresses` then.
    return [(address, address) for address in addresses]


ADMINS = admins_from_env()

# Everything from INFO up goes to stdout with a timestamp, where Docker collects it.
# Django's own default prints nothing when DEBUG is False.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'timestamped': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {'()': 'django.utils.log.RequireDebugFalse'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'formatter': 'timestamped',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        # Replaces Django's default, which also has a console handler: the messages
        # reach the root handler, so they would be printed twice
        'django': {'handlers': ['mail_admins'], 'level': 'INFO'},
    },
}

ACCOUNT_SESSION_REMEMBER = True
# Log in with email; sign up with email and one password field (no username)
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*']
ACCOUNT_UNIQUE_EMAIL = True
# Two-factor login: an authenticator app (TOTP) plus recovery codes. No passkeys.
MFA_SUPPORTED_TYPES = ['totp', 'recovery_codes']
MFA_TOTP_ISSUER = 'Wildvasa Forums'
# Staff, moderators and anyone else with a permission need an authenticator app to use
# the site, and their API tokens are refused (users/security.py, api/authentication.py).
# On unless switched off.
STAFF_REQUIRE_MFA = env_bool('DJANGO_STAFF_REQUIRE_MFA', True)
# New accounts, by email or GitHub, only while DJANGO_SIGNUP_OPEN is true. Closed by
# default, so a missing variable never opens a production forum by accident.
ACCOUNT_ADAPTER = 'users.adapters.AccountAdapter'
SOCIALACCOUNT_ADAPTER = 'users.adapters.SocialAccountAdapter'
SIGNUP_OPEN = env_bool('DJANGO_SIGNUP_OPEN')
# Invitation links (users.Invitation) let one address sign up while signup is closed
INVITATION_EXPIRY_DAYS = 7

# The site's public address, for links in emails. Production requires DJANGO_SITE_URL;
# elsewhere it defaults to the development server.
SITE_URL = os.environ.get('DJANGO_SITE_URL', 'http://127.0.0.1:8000').strip().rstrip('/')

DEFAULT_FROM_EMAIL = 'noreply@email.com'


MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'api.authentication.NonStaffTokenAuthentication',
    ],
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
    # Anonymous clients are counted per address, logged-in users per user.
    # The counters are in the cache
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '120/min',
        # New threads and posts per user, on the site and in the API together (forums/throttling.py)
        'posting_burst': '5/min',
        'posting_hour': '30/hour',
        # Web views: search per user or address, the editor's preview per user
        'search': '20/min',
        'preview': '30/min',
    },
    # No proxy: the address is the connection's. DRF's default would trust any
    # X-Forwarded-For header, so a client could reset its count by making one up
    'NUM_PROXIES': 0,
}

# Override the database with DATABASE_URL when it is set
import dj_database_url
db_from_env = dj_database_url.config(conn_max_age=500)
DATABASES['default'].update(db_from_env)

CACHE_MIDDLEWARE_ALIAS = 'default'

if os.environ.get('REDIS_URL') is not None:
    redis_host = os.environ.get('REDIS_URL')
elif os.environ.get('REDIS_LOCALHOST'):
    redis_host = f'redis://localhost:6379/0'
else:
    redis_host = f'redis://redis:6379/0'


def redis_url_with_db(url, db):
    """Return the Redis URL pointing at database number `db`."""
    return urlsplit(url)._replace(path=f'/{db}').geturl()


# Cache on database 0, Celery broker on database 1
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': redis_url_with_db(redis_host, 0),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

CELERY_BROKER_URL = redis_url_with_db(redis_host, 1)
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
# The tasks only send mail and nothing reads their results, so there is no result backend:
# with one, queuing a task waits about 20 seconds when Redis is down
CELERY_TASK_IGNORE_RESULT = True
# Give up queuing after a few seconds when Redis is unreachable, instead of minutes.
# The request carries on without the mail (project.utils.queue_task)
CELERY_BROKER_TRANSPORT_OPTIONS = {'socket_connect_timeout': 2}
CELERY_TASK_PUBLISH_RETRY_POLICY = {'max_retries': 1}
if not os.environ.get('ENVIRONMENT') == 'production':
    # Run tasks in-process outside production, so errors surface in the web log
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True


# An example below how to set up a scheduled task
# The tasks code could live in a tasks.py in the app folder of choice
# If using tasks in the core folder I explicitly import it
# Couldn't get it to work otherwise

# from celery.schedules import crontab
# import project.tasks
#
# CELERY_BEAT_SCHEDULE = {
#     'my_scheduled_task': {
#         'task': 'project.tasks.my_scheduled_task',
#         'schedule': crontab(minute='*/1'),
#     },
# }

CORS_ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000"
]
