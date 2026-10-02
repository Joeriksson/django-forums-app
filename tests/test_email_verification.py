import re

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from forums.models import Forum, Notification, Post, Thread

User = get_user_model()

EMAIL = 'member@example.com'
PASSWORD = 'a-long-test-pass-123'


def is_logged_in(client):
    return '_auth_user_id' in client.session


def password_login(client):
    return client.post(reverse('account_login'), {'login': EMAIL, 'password': PASSWORD})


def confirmation_path():
    """The path of the confirmation link in the mails sent so far."""
    for message in mail.outbox:
        match = re.search(r'/accounts/confirm-email/[^/\s]+/', message.body)
        if match:
            return match.group()
    return None


@pytest.fixture
def signup_open(settings):
    settings.SIGNUP_OPEN = True


@pytest.fixture
def user(db):
    return User.objects.create_user(username='member', email=EMAIL, password=PASSWORD)


@pytest.mark.django_db
def test_signup_does_not_log_in_before_confirmation(client, signup_open):
    resp = client.post(reverse('account_signup'), {'email': EMAIL, 'password1': PASSWORD})

    assertRedirects(resp, reverse('account_email_verification_sent'))
    assert not is_logged_in(client)
    assert not EmailAddress.objects.get(email=EMAIL).verified
    assert confirmation_path()


@pytest.mark.django_db
def test_confirmation_link_lets_the_user_log_in(client, signup_open):
    client.post(reverse('account_signup'), {'email': EMAIL, 'password1': PASSWORD})

    client.post(confirmation_path())

    assert EmailAddress.objects.get(email=EMAIL).verified
    password_login(client)
    assert is_logged_in(client)


@pytest.mark.django_db
def test_login_with_unverified_address_sends_confirmation(client, user):
    """An account made without signup (createsuperuser, the admin) confirms at its first login."""
    resp = password_login(client)

    assertRedirects(resp, reverse('account_email_verification_sent'))
    assert not is_logged_in(client)
    assert confirmation_path()


@pytest.mark.django_db
def test_login_with_verified_address(client, user, verify_email):
    verify_email(user)

    resp = password_login(client)

    assertRedirects(resp, reverse('home'), fetch_redirect_response=False)
    assert is_logged_in(client)


@pytest.mark.django_db
def test_github_signup_needs_no_confirmation(client, github_login, signup_open):
    github_login(EMAIL)

    assert is_logged_in(client)
    assert EmailAddress.objects.get(email=EMAIL).verified
    assert confirmation_path() is None


@pytest.fixture
def thread(db):
    author = User.objects.create_user(username='author', email='author@example.com', password=PASSWORD)
    forum = Forum.objects.create(title='Test Forum', description='Description')
    return Thread.objects.create(title='Test Thread', text='Thread text', forum=forum, user=author)


def notified_addresses(thread, notification_calls, django_capture_on_commit_callbacks):
    """Post a reply as the thread's author; return the addresses the notification goes to."""
    with django_capture_on_commit_callbacks(execute=True):
        Post.objects.create(text='A reply', thread=thread, user=thread.user)
    return [address for call in notification_calls for address in call[4]]


@pytest.mark.django_db
def test_notification_skips_unverified_subscriber(
    thread, user, verify_email, notification_calls, django_capture_on_commit_callbacks
):
    verified = User.objects.create_user(username='verified', email='verified@example.com', password=PASSWORD)
    verify_email(verified)
    Notification.objects.create(thread=thread, user=user)
    Notification.objects.create(thread=thread, user=verified)

    assert notified_addresses(thread, notification_calls, django_capture_on_commit_callbacks) == [
        'verified@example.com'
    ]


@pytest.mark.django_db
def test_notification_skips_deactivated_subscriber(
    thread, user, verify_email, notification_calls, django_capture_on_commit_callbacks
):
    verify_email(user)
    user.is_active = False
    user.save()
    Notification.objects.create(thread=thread, user=user)

    assert notified_addresses(thread, notification_calls, django_capture_on_commit_callbacks) == []


@pytest.mark.django_db
def test_notification_uses_the_verified_address_only(
    thread, user, verify_email, notification_calls, django_capture_on_commit_callbacks
):
    """A verified address that is not the account's current one doesn't count."""
    verify_email(user)
    user.email = 'changed@example.com'
    user.save()
    Notification.objects.create(thread=thread, user=user)

    assert notified_addresses(thread, notification_calls, django_capture_on_commit_callbacks) == []
