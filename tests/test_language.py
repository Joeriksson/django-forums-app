import importlib
import sys

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse


def load_base():
    """Import project.settings.base fresh, then put the original module back."""
    original = sys.modules.pop('project.settings.base')
    try:
        return importlib.import_module('project.settings.base')
    finally:
        sys.modules['project.settings.base'] = original


@pytest.mark.parametrize(
    'value, expected',
    [(None, 'en'), ('', 'en'), ('en', 'en'), ('sv', 'sv'), (' sv ', 'sv')],
)
def test_language_from_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('DJANGO_LANGUAGE', raising=False)
    else:
        monkeypatch.setenv('DJANGO_LANGUAGE', value)

    assert load_base().LANGUAGE_CODE == expected


@pytest.mark.parametrize('value', ['de', 'swedish', 'sv-se', 'EN'])
def test_unknown_language_stops_the_app(monkeypatch, value):
    monkeypatch.setenv('DJANGO_LANGUAGE', value)

    with pytest.raises(ImproperlyConfigured, match='DJANGO_LANGUAGE'):
        load_base()


def test_tests_run_in_english():
    assert settings.LANGUAGE_CODE == 'en'


# The login page is allauth's, which has its own Swedish texts
SIGN_IN = {'en': 'Sign In', 'sv': 'Logga in'}


def language_of(response):
    return response.headers['Content-Language']


@pytest.mark.django_db
def test_site_language_without_a_choice(client):
    response = client.get(reverse('account_login'))

    assert language_of(response) == 'en'
    assert SIGN_IN['en'] in response.content.decode()


@pytest.mark.django_db
def test_site_language_follows_the_setting(client, settings):
    settings.LANGUAGE_CODE = 'sv'

    response = client.get(reverse('account_login'))

    assert language_of(response) == 'sv'
    assert SIGN_IN['sv'] in response.content.decode()


@pytest.mark.django_db
def test_cookie_chooses_the_language(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'

    response = client.get(reverse('account_login'))

    assert language_of(response) == 'sv'
    assert SIGN_IN['sv'] in response.content.decode()


@pytest.mark.django_db
def test_browser_language_is_not_followed(client):
    response = client.get(reverse('account_login'), headers={'Accept-Language': 'sv'})

    assert language_of(response) == 'en'


@pytest.mark.django_db
@pytest.mark.parametrize('value', ['de', 'sv-se', '', '../x'])
def test_unknown_cookie_gives_the_site_language(client, value):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = value

    response = client.get(reverse('account_login'))

    assert language_of(response) == 'en'


@pytest.mark.django_db
def test_language_does_not_stay_for_the_next_request(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'
    client.get(reverse('account_login'))
    del client.cookies[settings.LANGUAGE_COOKIE_NAME]

    response = client.get(reverse('account_login'))

    assert language_of(response) == 'en'
    assert SIGN_IN['en'] in response.content.decode()


@pytest.fixture
def admin_client(client, add_totp, django_user_model):
    admin = django_user_model.objects.create_superuser('admin', 'admin@example.com', 'testpass123')
    add_totp(admin)
    client.force_login(admin)
    return client


@pytest.mark.django_db
def test_admin_stays_english_for_a_swedish_choice(admin_client):
    admin_client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'

    response = admin_client.get(reverse('admin:index'))

    assert language_of(response) == 'en'
    assert 'Site administration' in response.content.decode()


@pytest.mark.django_db
def test_admin_stays_english_on_a_swedish_site(admin_client, settings):
    settings.LANGUAGE_CODE = 'sv'

    response = admin_client.get(reverse('admin:users_customuser_changelist'))

    assert language_of(response) == 'en'
    assert 'Select user to change' in response.content.decode()


@pytest.mark.django_db
def test_pages_outside_the_admin_follow_the_choice_of_an_admin(admin_client):
    admin_client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'

    response = admin_client.get(reverse('account_email'))

    assert language_of(response) == 'sv'
