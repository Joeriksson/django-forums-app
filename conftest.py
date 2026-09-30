from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.core.cache import cache
from django.urls import reverse


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# Same notification path in CI and locally: CI unset, task recorded instead of queued
@pytest.fixture(autouse=True)
def notification_calls(monkeypatch):
    calls = []
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.setattr(
        'forums.tasks.send_notifications_task.delay', lambda *args: calls.append(args)
    )
    return calls


@pytest.fixture
def github_login(client, monkeypatch):
    """
    Log in with GitHub through allauth's real views. Only the calls to GitHub
    are faked: the token exchange and the profile with its email addresses.
    """

    def _login(email, uid=12345, emails=None):
        """`emails`: GitHub's addresses as (address, verified); default: `email`, verified."""
        monkeypatch.setattr(
            OAuth2Client, 'get_access_token', lambda *args, **kwargs: {'access_token': 'token'}
        )
        profile = {
            'id': uid,
            'login': 'octocat',
            'email': email,
            'emails': [
                {'email': address, 'verified': verified, 'primary': address == email}
                for address, verified in (emails or [(email, True)])
            ],
        }
        monkeypatch.setattr(
            GitHubOAuth2Adapter,
            'complete_login',
            lambda self, request, app, token, **kwargs: self.get_provider().sociallogin_from_response(
                request, profile
            ),
        )
        redirect = client.post(reverse('github_login'))
        state = parse_qs(urlsplit(redirect['Location']).query)['state'][0]
        return client.get(reverse('github_callback'), {'code': 'code', 'state': state})

    return _login
