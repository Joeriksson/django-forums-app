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


def failed_login(client, address, attempt):
    # A new email each time, so only the limit per address counts, not the one per account
    return client.post(
        reverse('account_login'),
        {'login': f'nobody{attempt}@example.com', 'password': 'wrong-password'},
        HTTP_X_FORWARDED_FOR=address,
    )


@pytest.mark.django_db
def test_failed_logins_are_limited_per_forwarded_address(client, settings):
    # Every request reaches the app from the reverse proxy; the visitor is in X-Forwarded-For
    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1  # as in production
    too_many = 'Too many failed login attempts'
    for attempt in range(10):
        failed_login(client, '203.0.113.1', attempt)

    blocked = failed_login(client, '203.0.113.1', 'blocked')
    other_visitor = failed_login(client, '203.0.113.2', 'other')

    assert too_many in blocked.content.decode()
    assert too_many not in other_visitor.content.decode()


@pytest.mark.django_db
def test_allauth_names_the_member_not_the_username(client, django_user_model, verify_email):
    # allauth derives the username from the address: anna.berg@... becomes anna.berg
    user = django_user_model.objects.create_user(
        username='anna.berg', email='anna@example.com', password='testpass123'
    )
    verify_email(user)

    resp = client.post(
        reverse('account_login'),
        {'login': 'anna@example.com', 'password': 'testpass123'},
        follow=True,
    )

    messages = [str(message) for message in resp.context['messages']]
    assert messages == [f'Successfully signed in as {user.display_name}.']
