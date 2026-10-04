import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal import auth as totp
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

User = get_user_model()

EMAIL = 'member@example.com'
PASSWORD = 'testpass123'


def password_login(client):
    return client.post(reverse('account_login'), {'login': EMAIL, 'password': PASSWORD})


def is_logged_in(client):
    return '_auth_user_id' in client.session


@pytest.fixture
def user(db, verify_email):
    return verify_email(User.objects.create_user(username='member', email=EMAIL, password=PASSWORD))


@pytest.fixture
def totp_secret(user):
    """Give `user` an authenticator app and recovery codes; return the app's secret."""
    secret = totp.generate_totp_secret()
    totp.TOTP.activate(user, secret)
    RecoveryCodes.activate(user)
    return secret


def test_mfa_page_uses_site_layout(client, user):
    client.force_login(user)

    resp = client.get(reverse('mfa_index'))

    assertContains(resp, 'site-header')
    assertContains(resp, reverse('mfa_activate_totp'))


def test_navbar_links_to_mfa_page_when_logged_in(client, user):
    client.force_login(user)

    resp = client.get(reverse('home'))

    assertContains(resp, reverse('mfa_index'))


@pytest.mark.django_db
def test_navbar_has_no_mfa_link_for_anonymous(client):
    resp = client.get(reverse('home'))

    assertNotContains(resp, reverse('mfa_index'))


def test_passkeys_are_not_offered():
    with pytest.raises(NoReverseMatch):
        reverse('mfa_add_webauthn')


def test_user_sets_up_authenticator_app(client, user, totp_code):
    password_login(client)
    page = client.get(reverse('mfa_activate_totp'))
    assertContains(page, 'site-header')
    secret = page.context['form'].secret

    resp = client.post(reverse('mfa_activate_totp'), {'code': totp_code(secret)})

    assert resp.status_code == 302
    types = set(Authenticator.objects.filter(user=user).values_list('type', flat=True))
    assert types == {Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES}


def test_setup_refuses_wrong_code(client, user):
    password_login(client)
    client.get(reverse('mfa_activate_totp'))

    resp = client.post(reverse('mfa_activate_totp'), {'code': '000000'})

    assert resp.status_code == 200
    assert not Authenticator.objects.filter(user=user).exists()


def test_password_login_without_mfa_needs_no_code(client, user):
    password_login(client)

    assert is_logged_in(client)


def test_password_login_asks_for_code(client, user, totp_secret, totp_code):
    resp = password_login(client)

    assertRedirects(resp, reverse('mfa_authenticate'), fetch_redirect_response=False)
    assert not is_logged_in(client)
    assertContains(client.get(reverse('mfa_authenticate')), 'site-header')

    client.post(reverse('mfa_authenticate'), {'code': totp_code(totp_secret)})

    assert client.session['_auth_user_id'] == str(user.pk)


def test_wrong_code_does_not_log_in(client, user, totp_secret):
    password_login(client)

    resp = client.post(reverse('mfa_authenticate'), {'code': '000000'})

    assert resp.status_code == 200
    assert not is_logged_in(client)


def test_github_login_asks_for_code(client, user, totp_secret, github_login, totp_code):
    SocialAccount.objects.create(user=user, provider='github', uid='12345')

    resp = github_login(EMAIL)

    assertRedirects(resp, reverse('mfa_authenticate'), fetch_redirect_response=False)
    assert not is_logged_in(client)

    client.post(reverse('mfa_authenticate'), {'code': totp_code(totp_secret)})

    assert client.session['_auth_user_id'] == str(user.pk)


def test_recovery_code_logs_in_once(client, user, totp_secret):
    recovery_codes = Authenticator.objects.get(user=user, type=Authenticator.Type.RECOVERY_CODES)
    code = recovery_codes.wrap().get_unused_codes()[0]

    password_login(client)
    client.post(reverse('mfa_authenticate'), {'code': code})
    assert is_logged_in(client)

    client.logout()
    password_login(client)
    client.post(reverse('mfa_authenticate'), {'code': code})
    assert not is_logged_in(client)
