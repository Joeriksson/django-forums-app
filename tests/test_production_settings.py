import importlib
import sys

import pytest

PRODUCTION_ENV_VARS = [
    'DJANGO_ALLOWED_HOSTS',
    'DJANGO_SECURE_HSTS_SECONDS',
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
    'DJANGO_SECURE_HSTS_PRELOAD',
    'RENDER_EXTERNAL_HOSTNAME',
    'EMAIL_HOST',
    'EMAIL_PORT',
    'EMAIL_USE_TLS',
    'EMAIL_HOST_USER',
    'EMAIL_HOST_PASSWORD',
    'DEFAULT_FROM_EMAIL',
]


@pytest.fixture
def load_production(monkeypatch):
    """Import project.settings.production fresh with the given env vars."""

    def _load(**env):
        for name in PRODUCTION_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        sys.modules.pop('project.settings.production', None)
        return importlib.import_module('project.settings.production')

    yield _load
    sys.modules.pop('project.settings.production', None)


def test_allowed_hosts_from_env(load_production):
    production = load_production(
        DJANGO_ALLOWED_HOSTS='forum.example.com, www.forum.example.com'
    )

    assert production.ALLOWED_HOSTS == ['forum.example.com', 'www.forum.example.com']
    assert production.CSRF_TRUSTED_ORIGINS == [
        'https://forum.example.com',
        'https://www.forum.example.com',
    ]


def test_allowed_hosts_empty_without_env(load_production):
    production = load_production()

    assert production.ALLOWED_HOSTS == []
    assert production.CSRF_TRUSTED_ORIGINS == []


def test_no_render_or_heroku_hosts(load_production):
    production = load_production(RENDER_EXTERNAL_HOSTNAME='mysite.onrender.com')

    assert 'mysite.onrender.com' not in production.ALLOWED_HOSTS
    assert '.herokuapp.com' not in production.ALLOWED_HOSTS


def test_hsts_defaults(load_production):
    production = load_production()

    assert production.SECURE_HSTS_SECONDS == 3600
    assert production.SECURE_HSTS_INCLUDE_SUBDOMAINS is False
    assert production.SECURE_HSTS_PRELOAD is False


def test_hsts_from_env(load_production):
    production = load_production(
        DJANGO_SECURE_HSTS_SECONDS='31536000',
        DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS='true',
        DJANGO_SECURE_HSTS_PRELOAD='true',
    )

    assert production.SECURE_HSTS_SECONDS == 31536000
    assert production.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert production.SECURE_HSTS_PRELOAD is True


def test_smtp_with_host_and_credentials(load_production):
    production = load_production(
        EMAIL_HOST='smtp.example.com',
        EMAIL_HOST_USER='forum@example.com',
        EMAIL_HOST_PASSWORD='smtp-token',
    )

    assert production.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
    assert production.EMAIL_HOST == 'smtp.example.com'
    assert production.EMAIL_PORT == 587
    assert production.EMAIL_USE_TLS is True
    assert production.EMAIL_HOST_USER == 'forum@example.com'
    assert production.EMAIL_HOST_PASSWORD == 'smtp-token'
    # Sender defaults to the SMTP login
    assert production.DEFAULT_FROM_EMAIL == 'forum@example.com'
    assert production.SERVER_EMAIL == 'forum@example.com'


def test_smtp_settings_from_env(load_production):
    production = load_production(
        EMAIL_HOST='smtp.example.com',
        EMAIL_PORT='2525',
        EMAIL_USE_TLS='false',
        EMAIL_HOST_USER='forum@example.com',
        EMAIL_HOST_PASSWORD='smtp-token',
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )

    assert production.EMAIL_HOST == 'smtp.example.com'
    assert production.EMAIL_PORT == 2525
    assert production.EMAIL_USE_TLS is False
    assert production.DEFAULT_FROM_EMAIL == 'noreply@example.com'
    assert production.SERVER_EMAIL == 'noreply@example.com'


@pytest.mark.parametrize(
    'env',
    [
        {},
        {'EMAIL_HOST_USER': 'forum@example.com', 'EMAIL_HOST_PASSWORD': 'smtp-token'},
        {'EMAIL_HOST': 'smtp.example.com', 'EMAIL_HOST_USER': 'forum@example.com'},
    ],
)
def test_console_email_without_host_or_credentials(load_production, env):
    production = load_production(**env)

    assert production.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend'
