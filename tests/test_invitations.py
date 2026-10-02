from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import (
    assertContains,
    assertFormError,
    assertRedirects,
    assertTemplateUsed,
)

from users.models import Invitation

User = get_user_model()
PASSWORD = 'a-long-test-pass-123'


@pytest.fixture(autouse=True)
def signup_closed(settings):
    settings.SIGNUP_OPEN = False


@pytest.fixture
def invitation(db):
    return Invitation.objects.create(email='anna@example.com')


def accept_url(invitation):
    return reverse('accept_invitation', args=[invitation.key])


def sign_up(client, email):
    return client.post(reverse('account_signup'), {'email': email, 'password1': PASSWORD})


# Model


@pytest.mark.django_db
def test_invitation_gets_a_long_random_key():
    first = Invitation.objects.create(email='anna@example.com')
    second = Invitation.objects.create(email='bo@example.com')

    assert len(first.key) >= 40
    assert first.key != second.key


@pytest.mark.django_db
def test_invitation_valid_for_expiry_days(settings):
    settings.INVITATION_EXPIRY_DAYS = 7
    fresh = Invitation.objects.create(email='fresh@example.com')
    almost = Invitation.objects.create(
        email='almost@example.com', created=timezone.now() - timedelta(days=6, hours=23)
    )
    expired = Invitation.objects.create(
        email='expired@example.com', created=timezone.now() - timedelta(days=7, minutes=1)
    )
    used = Invitation.objects.create(email='used@example.com', accepted_at=timezone.now())

    assert set(Invitation.objects.valid()) == {fresh, almost}
    assert [fresh.is_valid(), almost.is_valid(), expired.is_valid(), used.is_valid()] == [
        True,
        True,
        False,
        False,
    ]


# Accepting the link


def test_valid_link_opens_signup_with_invited_email(client, invitation):
    resp = client.get(accept_url(invitation))

    assertRedirects(resp, reverse('account_signup'), fetch_redirect_response=False)
    signup = client.get(reverse('account_signup'))
    assertTemplateUsed(signup, 'account/signup.html')
    assert signup.context['form']['email'].value() == 'anna@example.com'


@pytest.mark.django_db
def test_unknown_link_is_invalid(client):
    resp = client.get(reverse('accept_invitation', args=['no-such-key']))

    assert resp.status_code == 404
    assertTemplateUsed(resp, 'account/invitation_invalid.html')


@pytest.mark.parametrize(
    'change',
    [
        {'created': timezone.now() - timedelta(days=30)},
        {'accepted_at': timezone.now()},
    ],
    ids=['expired', 'used'],
)
def test_expired_or_used_link_is_invalid(client, invitation, change):
    Invitation.objects.filter(pk=invitation.pk).update(**change)

    resp = client.get(accept_url(invitation))

    assert resp.status_code == 404
    assertTemplateUsed(resp, 'account/invitation_invalid.html')
    # And signup stays closed
    assertTemplateUsed(client.get(reverse('account_signup')), 'account/signup_closed.html')


def test_logged_in_user_is_sent_home(client, invitation):
    user = User.objects.create_user(username='member', email='member@example.com')
    client.force_login(user)

    resp = client.get(accept_url(invitation))

    assertRedirects(resp, reverse('home'), fetch_redirect_response=False)
    assert Invitation.objects.get(pk=invitation.pk).accepted_at is None


def test_navbar_shows_signup_link_with_invitation(client, invitation):
    client.get(accept_url(invitation))

    assertContains(client.get(reverse('home')), reverse('account_signup'))


# Signing up with the form


def test_signup_with_invited_email(client, invitation):
    client.get(accept_url(invitation))

    resp = sign_up(client, 'anna@example.com')

    assertRedirects(resp, reverse('home'), fetch_redirect_response=False)
    user = User.objects.get(email='anna@example.com')
    invitation.refresh_from_db()
    assert invitation.accepted_by == user
    assert invitation.accepted_at is not None
    # The link proved the address, so no confirmation mail is needed
    assert EmailAddress.objects.get(user=user).verified


def test_signup_with_invited_email_ignores_case(client, db):
    invitation = Invitation.objects.create(email='Anna@Example.com')
    client.get(accept_url(invitation))

    sign_up(client, 'anna@example.com')

    assert User.objects.filter(email__iexact='anna@example.com').exists()


def test_signup_with_other_email_is_refused(client, invitation):
    client.get(accept_url(invitation))

    resp = sign_up(client, 'someone.else@example.com')

    assertFormError(
        resp.context['form'], 'email', 'Sign up with the invited address: anna@example.com'
    )
    assert not User.objects.filter(email='someone.else@example.com').exists()
    assert Invitation.objects.get(pk=invitation.pk).accepted_at is None


def test_used_invitation_closes_signup_again(client, invitation):
    client.get(accept_url(invitation))
    sign_up(client, 'anna@example.com')
    client.logout()

    assertTemplateUsed(client.get(reverse('account_signup')), 'account/signup_closed.html')
    assertTemplateUsed(client.get(accept_url(invitation)), 'account/invitation_invalid.html')


def test_password_reset_ignores_invitation(client, invitation):
    # allauth's reset form calls the same clean_email; only signup is restricted
    User.objects.create_user(username='member', email='member@example.com')
    client.get(accept_url(invitation))

    resp = client.post(reverse('account_reset_password'), {'email': 'member@example.com'})

    assertRedirects(resp, reverse('account_reset_password_done'), fetch_redirect_response=False)


# Signing up with GitHub


def test_github_signup_with_invited_email(client, github_login, invitation):
    client.get(accept_url(invitation))

    github_login('anna@example.com')

    user = User.objects.get(email='anna@example.com')
    assert Invitation.objects.get(pk=invitation.pk).accepted_by == user


def test_github_signup_with_invited_email_as_secondary_address(client, github_login, invitation):
    client.get(accept_url(invitation))

    github_login('anna@work.example.com', emails=[('anna@work.example.com', True), ('anna@example.com', True)])

    assert Invitation.objects.get(pk=invitation.pk).accepted_by is not None


@pytest.mark.parametrize(
    'emails',
    [[('octocat@example.com', True)], [('octocat@example.com', True), ('anna@example.com', False)]],
    ids=['other-address', 'invited-address-unverified'],
)
def test_github_signup_without_invited_email_is_refused(client, github_login, invitation, emails):
    client.get(accept_url(invitation))

    resp = github_login('octocat@example.com', emails=emails)

    assertTemplateUsed(resp, 'account/signup_closed.html')
    # Tell the person how to use the invitation instead
    assertContains(resp, 'anna@example.com')
    assert User.objects.count() == 0
    assert Invitation.objects.get(pk=invitation.pk).accepted_at is None


# Admin


@pytest.fixture
def admin_client_for(client, add_totp):
    def _client(*permissions):
        user = User.objects.create_user(
            username='staff', email='staff@example.com', password=PASSWORD, is_staff=True
        )
        user.user_permissions.add(
            *Permission.objects.filter(content_type__app_label='users', codename__in=permissions)
        )
        add_totp(user)
        client.force_login(user)
        return client, user

    return _client


@pytest.mark.django_db
def test_admin_creates_invitation_with_inviter_and_link(admin_client_for):
    client, staff = admin_client_for('add_invitation', 'change_invitation', 'view_invitation')

    client.post(reverse('admin:users_invitation_add'), {'email': 'anna@example.com'})

    invitation = Invitation.objects.get(email='anna@example.com')
    assert invitation.invited_by == staff
    change_page = client.get(reverse('admin:users_invitation_change', args=[invitation.pk]))
    assertContains(change_page, accept_url(invitation))


@pytest.mark.django_db
def test_admin_invitations_need_permission(admin_client_for):
    client, _ = admin_client_for()

    resp = client.get(reverse('admin:users_invitation_add'))

    assert resp.status_code == 403


# Security log


def test_signup_with_an_invitation_is_logged(client, invitation, security_log):
    client.get(accept_url(invitation))

    sign_up(client, 'anna@example.com')

    user = User.objects.get(email='anna@example.com')
    assert f'invitation_used user={user.pk} invitation={invitation.pk} ip=127.0.0.1' in security_log()
    assert invitation.key not in ' '.join(security_log())


@pytest.mark.django_db
def test_invalid_link_is_logged_without_the_key(client, security_log):
    client.get(reverse('accept_invitation', args=['no-such-key']))

    assert security_log() == ['invitation_refused ip=127.0.0.1']


def test_signup_without_an_invitation_logs_no_invitation(client, db, settings, security_log):
    settings.SIGNUP_OPEN = True

    sign_up(client, 'open@example.com')

    assert User.objects.filter(email='open@example.com').exists()
    assert not [line for line in security_log() if line.startswith('invitation')]
