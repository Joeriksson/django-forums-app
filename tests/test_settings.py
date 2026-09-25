from django.conf import settings


def test_pytest_uses_test_settings():
    # DJANGO_SETTINGS_MODULE from .env must not override the test settings
    assert settings.SETTINGS_MODULE == 'project.settings.test'
