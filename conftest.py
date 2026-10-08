import logging
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.totp.internal import auth as totp
from allauth.socialaccount.providers.github.views import GitHubOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from django.core.cache import cache
from django.urls import reverse


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# Same notification path in CI and locally: CI unset, task recorded instead of queued.
# Each call is (the reply's id, the seconds the mail waits); a test that wants the mail
# runs send_notifications_task(post.pk) itself
@pytest.fixture(autouse=True)
def notification_calls(monkeypatch):
    calls = []
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.setattr(
        'forums.tasks.send_notifications_task.apply_async',
        lambda args, countdown: calls.append((args[0], countdown)),
    )
    return calls


@pytest.fixture
def reply_with_mail(django_capture_on_commit_callbacks):
    """Post a reply and run its mail task, as the worker does after the wait. Returns the post."""

    def _reply(thread, user, text='A reply'):
        from forums.models import Post
        from forums.tasks import send_notifications_task

        with django_capture_on_commit_callbacks(execute=True):
            post = Post.objects.create(text=text, thread=thread, user=user)
        send_notifications_task(post.pk)
        return post

    return _reply


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


@pytest.fixture
def add_totp(db):
    """Give a user an authenticator app, as staff need for the admin; returns its secret."""

    def _add_totp(user):
        secret = totp.generate_totp_secret()
        totp.TOTP.activate(user, secret)
        return secret

    return _add_totp


@pytest.fixture
def totp_code(monkeypatch):
    """
    The code an authenticator app shows for a secret: totp_code(secret).

    Holds allauth's clock still for the test. A code is valid for one 30-second period,
    so with the real clock a test fails whenever a period ends between making the code
    and checking it.
    """
    now = time.time()
    monkeypatch.setattr(totp, 'time', SimpleNamespace(time=lambda: now))

    def _totp_code(secret):
        counter = next(totp.yield_hotp_counters_from_time())
        return totp.format_hotp_value(totp.hotp_value(secret, counter))

    return _totp_code


@pytest.fixture
def verify_email(db):
    """Mark a user's address as verified, as the confirmation link does: needed to log in."""

    def _verify_email(user):
        EmailAddress.objects.update_or_create(
            user=user, email=user.email, defaults={'primary': True, 'verified': True}
        )
        return user

    return _verify_email


@pytest.fixture
def security_log(caplog):
    """The lines written to the security log during the test."""
    caplog.set_level(logging.INFO, logger='security')

    def lines():
        return [record.getMessage() for record in caplog.records if record.name == 'security']

    return lines


@pytest.fixture
def site_settings(db):
    """Change the site settings for a test, e.g. site_settings(posts_per_page=2)."""
    from pages.models import SiteSettings

    def _site_settings(**fields):
        # update(): no validation, so tests may use pages smaller than the admin allows
        SiteSettings.objects.filter(pk=SiteSettings.PK).update(**fields)

    return _site_settings
