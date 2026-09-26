import importlib
import sys

import pytest

PRODUCTION_ENV_VARS = [
    'DJANGO_ALLOWED_HOSTS',
    'DJANGO_SECURE_HSTS_SECONDS',
    'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
    'DJANGO_SECURE_HSTS_PRELOAD',
    'RENDER_EXTERNAL_HOSTNAME',
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
