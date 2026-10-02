"""DJANGO_API_ENABLED: without it there is no /api/ at all."""

import importlib
import sys

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import clear_url_caches, reverse
from pytest_django.asserts import assertRedirects

import project.urls

User = get_user_model()

API_URLS = ['/api/', '/api/forums/', '/api/threads/', '/api/posts/', '/api/users/', '/api/schema/']


def reload_urls():
    """Build the URL configuration again: it reads the setting when it is imported."""
    # project/urls.py wraps the admin's login view; unwrap it first, so it is wrapped once
    admin.site.login = admin.site.login.__wrapped__
    importlib.reload(project.urls)
    clear_url_caches()


@pytest.fixture
def api_off(settings):
    settings.API_ENABLED = False
    reload_urls()
    yield
    settings.API_ENABLED = True
    reload_urls()


def test_api_is_on_in_the_tests(settings):
    assert settings.API_ENABLED is True


@pytest.mark.django_db
def test_api_answers_while_enabled(client):
    assert client.get('/api/forums/').status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('url', API_URLS)
def test_no_api_for_visitors_while_disabled(client, api_off, url):
    assert client.get(url).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize('url', API_URLS)
def test_no_api_for_staff_while_disabled(client, api_off, add_totp, url):
    staff = User.objects.create_superuser(username='staff', email='staff@example.com', password='x')
    add_totp(staff)
    client.force_login(staff)

    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_site_works_while_disabled(client, api_off):
    assert client.get(reverse('home')).status_code == 200
    assert client.get(reverse('forum_list')).status_code == 200


@pytest.mark.django_db
def test_staff_without_authenticator_app_is_still_sent_to_setup_while_disabled(client, api_off):
    """The two-factor middleware must not depend on the API's routes."""
    staff = User.objects.create_superuser(username='staff', email='staff@example.com', password='x')
    client.force_login(staff)

    resp = client.get(reverse('home'))

    assertRedirects(resp, reverse('mfa_index'), fetch_redirect_response=False)


@pytest.mark.django_db
def test_api_is_back_after_the_switch_is_on_again(client, api_off, settings):
    settings.API_ENABLED = True
    reload_urls()

    assert client.get('/api/forums/').status_code == 200


def load_settings(name):
    """Import project.settings.<name> (and base) fresh, then put the original modules back."""
    names = {'project.settings.base', f'project.settings.{name}'}
    originals = {n: sys.modules.pop(n) for n in names if n in sys.modules}
    try:
        return importlib.import_module(f'project.settings.{name}')
    finally:
        for n in names:
            sys.modules.pop(n, None)
        sys.modules.update(originals)


@pytest.mark.parametrize(
    'module, env, expected',
    [
        ('base', None, False),
        ('base', 'true', True),
        ('development', None, True),
        ('development', 'false', False),
        ('test', None, True),
    ],
)
def test_api_is_off_unless_switched_on(monkeypatch, module, env, expected):
    monkeypatch.delenv('DJANGO_API_ENABLED', raising=False)
    if env is not None:
        monkeypatch.setenv('DJANGO_API_ENABLED', env)

    assert load_settings(module).API_ENABLED is expected
