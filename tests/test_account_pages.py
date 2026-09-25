import pytest
from django.urls import reverse

ACCOUNT_PAGES = ['account_login', 'account_signup']


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', ACCOUNT_PAGES)
def test_account_page_without_github_app(client, settings, url_name):
    settings.SOCIALACCOUNT_PROVIDERS = {}

    resp = client.get(reverse(url_name))

    assert resp.status_code == 200
    assert 'btn-github' not in resp.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', ACCOUNT_PAGES)
def test_account_page_with_github_app(client, url_name):
    # project.settings.test configures a GitHub app
    resp = client.get(reverse(url_name))

    assert resp.status_code == 200
    assert 'btn-github' in resp.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('github_configured', [True, False])
def test_login_page_always_shows_forgot_password(client, settings, github_configured):
    if not github_configured:
        settings.SOCIALACCOUNT_PROVIDERS = {}

    resp = client.get(reverse('account_login'))

    assert reverse('account_reset_password') in resp.content.decode()
