from django.conf import settings


def test_pytest_uses_test_settings():
    # DJANGO_SETTINGS_MODULE from .env must not override the test settings
    assert settings.SETTINGS_MODULE == 'project.settings.test'


def test_celery_runs_tasks_eagerly_outside_production():
    from project.celery import app

    assert app.conf.task_always_eager is True
    assert app.conf.task_eager_propagates is True
