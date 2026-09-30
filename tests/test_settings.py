import importlib
import sys

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def test_pytest_uses_test_settings():
    # DJANGO_SETTINGS_MODULE from .env must not override the test settings
    assert settings.SETTINGS_MODULE == 'project.settings.test'


def test_celery_runs_tasks_eagerly_outside_production():
    from project.celery import app

    assert app.conf.task_always_eager is True
    assert app.conf.task_eager_propagates is True


def test_cache_and_celery_use_separate_redis_databases():
    from project.settings import base

    assert base.CACHES['default']['LOCATION'].endswith('/0')
    assert base.CELERY_BROKER_URL.endswith('/1')
    assert base.CELERY_RESULT_BACKEND.endswith('/1')


def test_redis_url_with_db_keeps_password():
    from project.settings.base import redis_url_with_db

    assert (
        redis_url_with_db('redis://:secret@redis:6379/0', 1)
        == 'redis://:secret@redis:6379/1'
    )
    assert redis_url_with_db('redis://redis:6379', 1) == 'redis://redis:6379/1'


JANE = ('jane@example.com', 'jane@example.com')
JOHN = ('john@example.com', 'john@example.com')


@pytest.mark.parametrize(
    'value, expected',
    [
        (None, []),
        ('', []),
        ('jane@example.com', [JANE]),
        ('jane@example.com,john@example.com', [JANE, JOHN]),
        (' jane@example.com , john@example.com ,', [JANE, JOHN]),
    ],
)
def test_admins_from_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('DJANGO_ADMINS', raising=False)
    else:
        monkeypatch.setenv('DJANGO_ADMINS', value)

    assert load_base().ADMINS == expected


def test_admins_from_env_rejects_names(monkeypatch):
    # The old ADMIN1 format 'Name, email' must not turn the name into an address
    monkeypatch.setenv('DJANGO_ADMINS', 'Jane Doe, jane@example.com')

    with pytest.raises(ImproperlyConfigured, match="'Jane Doe'"):
        load_base()


@pytest.mark.parametrize(
    'value, expected',
    [(None, False), ('', False), ('false', False), ('true', True), ('1', True)],
)
def test_signup_closed_unless_env_opens_it(monkeypatch, value, expected):
    # base.py's value is what production uses: it doesn't set SIGNUP_OPEN itself
    if value is None:
        monkeypatch.delenv('DJANGO_SIGNUP_OPEN', raising=False)
    else:
        monkeypatch.setenv('DJANGO_SIGNUP_OPEN', value)

    assert load_base().SIGNUP_OPEN is expected


def load_base():
    """Import project.settings.base fresh, then put the original module back."""
    original = sys.modules.pop('project.settings.base')
    try:
        return importlib.import_module('project.settings.base')
    finally:
        sys.modules['project.settings.base'] = original
