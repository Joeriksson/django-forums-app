from django.conf import settings


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
