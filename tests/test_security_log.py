import logging

import pytest
from allauth.mfa import signals as mfa_signals
from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

EMAIL = 'member@example.com'
PASSWORD = 'testpass123'
IP = '203.0.113.7'


@pytest.fixture
def user(db):
    return User.objects.create_user(username='member', email=EMAIL, password=PASSWORD)


@pytest.fixture
def security_log(caplog):
    """The lines written to the security log during the test."""
    caplog.set_level(logging.INFO, logger='security')

    def lines():
        return [record.getMessage() for record in caplog.records if record.name == 'security']

    return lines


def login(client, email=EMAIL, password=PASSWORD, **extra):
    return client.post(
        reverse('account_login'), {'login': email, 'password': password}, REMOTE_ADDR=IP, **extra
    )


def test_login_is_logged_with_user_and_address(client, user, security_log):
    login(client)

    assert security_log() == [f'login user={user.pk} ip={IP}']


def test_logout_is_logged(client, user, security_log):
    client.force_login(user)

    client.post(reverse('account_logout'), REMOTE_ADDR=IP)

    assert security_log()[-1] == f'logout user={user.pk} ip={IP}'


def test_failed_login_is_logged_with_the_attempted_address(client, user, security_log, caplog):
    login(client, password='wrong-password')

    assert security_log() == [f"login_failed email='{EMAIL}' ip={IP}"]
    assert caplog.records[-1].levelno == logging.WARNING
    assert 'wrong-password' not in caplog.text


def test_failed_login_text_is_cut_and_cannot_start_a_new_line(security_log):
    from users.audit import log_login_failed

    log_login_failed(credentials={'email': 'a\nlogin user=1 ' + 'x' * 500})

    (line,) = security_log()
    assert '\n' not in line
    assert len(line) < 150


def test_address_comes_from_the_proxy_header_when_a_proxy_is_trusted(
    client, user, security_log, settings
):
    settings.ALLAUTH_TRUSTED_PROXY_COUNT = 1

    login(client, HTTP_X_FORWARDED_FOR='198.51.100.1, 192.0.2.44')

    assert security_log() == [f'login user={user.pk} ip=192.0.2.44']


def test_proxy_header_is_ignored_without_a_trusted_proxy(client, user, security_log):
    login(client, HTTP_X_FORWARDED_FOR='192.0.2.44')

    assert security_log() == [f'login user={user.pk} ip={IP}']


def test_wrong_two_factor_code_is_logged(client, user, add_totp, security_log):
    add_totp(user)
    login(client)

    client.post(reverse('mfa_authenticate'), {'code': '000000'}, REMOTE_ADDR=IP)

    assert security_log() == [f'mfa_failed user={user.pk} ip={IP}']


def test_password_change_is_logged(client, user, security_log):
    client.force_login(user)

    client.post(
        reverse('account_change_password'),
        {'oldpassword': PASSWORD, 'password1': 'new-Passw0rd-xyz', 'password2': 'new-Passw0rd-xyz'},
        REMOTE_ADDR=IP,
    )

    assert f'password_changed user={user.pk} ip={IP}' in security_log()
    assert 'new-Passw0rd-xyz' not in ' '.join(security_log())


def test_signup_is_logged(client, db, security_log):
    client.post(
        reverse('account_signup'),
        {'email': 'new@example.com', 'password1': 'new-Passw0rd-xyz'},
        REMOTE_ADDR=IP,
    )

    new_user = User.objects.get(email='new@example.com')
    assert f'signup user={new_user.pk} ip={IP}' in security_log()


@pytest.mark.parametrize(
    'signal, event',
    [
        (mfa_signals.authenticator_added, 'mfa_added'),
        (mfa_signals.authenticator_removed, 'mfa_removed'),
        (mfa_signals.authenticator_reset, 'mfa_reset'),
    ],
)
def test_two_factor_changes_are_logged(user, add_totp, security_log, signal, event):
    add_totp(user)
    authenticator = Authenticator.objects.get(user=user)

    signal.send(sender=Authenticator, request=None, user=user, authenticator=authenticator)

    assert security_log() == [f'{event} user={user.pk} type=totp']

