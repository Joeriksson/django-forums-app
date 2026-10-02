import logging

import pytest
from allauth.mfa import signals as mfa_signals
from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()

EMAIL = 'member@example.com'
PASSWORD = 'testpass123'
IP = '203.0.113.7'


@pytest.fixture
def user(db, verify_email):
    return verify_email(User.objects.create_user(username='member', email=EMAIL, password=PASSWORD))


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


def test_remove_mfa_command_is_logged(user, add_totp, security_log):
    add_totp(user)

    call_command('remove_mfa', EMAIL)

    assert security_log() == [f'mfa_removed_by_command user={user.pk} count=1']


def test_remove_mfa_command_logs_nothing_when_there_was_nothing_to_remove(user, security_log):
    call_command('remove_mfa', EMAIL)

    assert security_log() == []


# Refused requests


def test_a_refused_request_is_logged_with_the_user(client, user, security_log):
    client.force_login(user)

    resp = client.get(reverse('forum_add'), REMOTE_ADDR=IP)

    assert resp.status_code == 403
    # The first line is the login
    assert security_log()[1:] == [
        f"denied status=403 user={user.pk} method=GET path='/forums/add/' ip={IP}"
    ]


def test_a_refused_api_request_is_logged_with_the_token_user(user, security_log):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=user).key}')

    resp = client.post('/api/forums/', {'title': 'x', 'description': 'x'}, REMOTE_ADDR=IP)

    assert resp.status_code == 403
    assert security_log() == [f"denied status=403 user={user.pk} method=POST path='/api/forums/' ip={IP}"]


def test_a_refused_anonymous_request_is_logged_without_a_user(client, db, security_log):
    resp = client.post('/api/forums/', {'title': 'x', 'description': 'x'}, REMOTE_ADDR=IP)

    assert resp.status_code in (401, 403)
    assert security_log() == [
        f"denied status={resp.status_code} method=POST path='/api/forums/' ip={IP}"
    ]


def test_a_rate_limited_request_is_logged(client, user, security_log, settings):
    settings.ACCOUNT_RATE_LIMITS = {'reset_password': '1/m/ip'}
    url = reverse('account_reset_password')
    client.post(url, {'email': EMAIL}, REMOTE_ADDR=IP)

    resp = client.post(url, {'email': EMAIL}, REMOTE_ADDR=IP)

    assert resp.status_code == 429
    assert security_log()[-1] == f"denied status=429 method=POST path='{url}' ip={IP}"


def test_ordinary_requests_are_not_logged(client, db, security_log):
    client.get(reverse('home'))
    client.get('/no-such-page/')

    assert security_log() == []
