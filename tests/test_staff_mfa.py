import importlib
import sys

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal import auth as totp
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import CommandError, call_command
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from forums.models import Forum, Thread

User = get_user_model()

PASSWORD = 'testpass123'
ADMIN_INDEX = reverse('admin:index')
MFA_INDEX = reverse('mfa_index')
FORUM_LIST = reverse('forum_list')


def totp_code(secret):
    counter = next(totp.yield_hotp_counters_from_time())
    return totp.format_hotp_value(totp.hotp_value(secret, counter))


def token_client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=user).key}')
    return client


@pytest.fixture
def staff(db):
    return User.objects.create_superuser(
        username='staff', email='staff@example.com', password=PASSWORD
    )


@pytest.fixture
def member(db):
    return User.objects.create_user(username='member', email='member@example.com', password=PASSWORD)


@pytest.fixture
def moderator(member):
    member.groups.add(Group.objects.get(name='Moderators'))
    return member


@pytest.fixture(params=['superuser', 'staff', 'moderator', 'permission'])
def privileged(request, member):
    """A user who can do more than a member, in each of the ways an account can get there."""
    if request.param == 'superuser':
        member.is_superuser = True
    elif request.param == 'staff':
        member.is_staff = True
    elif request.param == 'moderator':
        member.groups.add(Group.objects.get(name='Moderators'))
    else:
        member.user_permissions.add(Permission.objects.get(codename='add_forum'))
    member.save()
    return member


@pytest.fixture
def mfa_not_required(settings):
    settings.STAFF_REQUIRE_MFA = False


# Admin


@pytest.mark.django_db
def test_admin_login_goes_through_the_site_login(client):
    resp = client.get(ADMIN_INDEX, follow=True)

    assertRedirects(resp, f"{reverse('account_login')}?next={ADMIN_INDEX}")


def test_staff_without_authenticator_app_is_sent_to_set_it_up(client, staff):
    client.force_login(staff)

    resp = client.get(ADMIN_INDEX, follow=True)

    assertRedirects(resp, MFA_INDEX)
    assertContains(resp, 'need two-factor authentication')


def test_admin_subpage_is_closed_too(client, staff):
    client.force_login(staff)

    resp = client.post(reverse('admin:users_invitation_add'), {'email': 'anna@example.com'})

    assertRedirects(resp, MFA_INDEX)


def test_recovery_codes_alone_are_not_enough(client, staff):
    RecoveryCodes.activate(staff)
    client.force_login(staff)

    assertRedirects(client.get(ADMIN_INDEX), MFA_INDEX)


def test_staff_with_authenticator_app_reaches_admin(client, staff, add_totp):
    add_totp(staff)
    client.force_login(staff)

    assert client.get(ADMIN_INDEX).status_code == 200


def test_staff_logs_in_to_admin_with_password_and_code(client, staff, add_totp):
    secret = add_totp(staff)

    resp = client.post(
        f"{reverse('account_login')}?next={ADMIN_INDEX}",
        {'login': staff.email, 'password': PASSWORD},
    )
    assertRedirects(resp, reverse('mfa_authenticate'), fetch_redirect_response=False)
    # Password alone: not logged in, so the admin sends back to the login page
    assert client.get(ADMIN_INDEX).status_code == 302

    client.post(reverse('mfa_authenticate'), {'code': totp_code(secret)})

    assert client.get(ADMIN_INDEX).status_code == 200


# The rest of the site: staff, superusers, moderators and anyone given a permission


@pytest.mark.parametrize('url_name', ['home', 'forum_list'])
def test_privileged_user_without_authenticator_app_is_sent_to_set_it_up(
    client, privileged, url_name
):
    client.force_login(privileged)

    resp = client.get(reverse(url_name), follow=True)

    assertRedirects(resp, MFA_INDEX)
    assertContains(resp, 'need two-factor authentication')


def test_moderator_without_authenticator_app_cannot_moderate(client, moderator, staff):
    forum = Forum.objects.create(title='Forum', description='A forum')
    thread = Thread.objects.create(title='Thread', text='Text', forum=forum, user=staff)
    client.force_login(moderator)

    resp = client.post(reverse('thread_delete', args=[forum.pk, thread.pk]))

    assertRedirects(resp, MFA_INDEX)
    assert Thread.objects.filter(pk=thread.pk).exists()


@pytest.mark.parametrize('url_name', ['mfa_index', 'account_logout', 'account_email'])
def test_account_pages_stay_open_to_set_it_up(client, privileged, url_name):
    client.force_login(privileged)

    assert client.get(reverse(url_name)).status_code == 200


def test_privileged_user_with_authenticator_app_uses_the_site(client, privileged, add_totp):
    add_totp(privileged)
    client.force_login(privileged)

    assert client.get(FORUM_LIST).status_code == 200


def test_member_needs_no_authenticator_app(client, member):
    client.force_login(member)

    assert client.get(FORUM_LIST).status_code == 200


def test_switch_off_lets_privileged_users_in(client, privileged, mfa_not_required):
    client.force_login(privileged)

    assert client.get(FORUM_LIST).status_code == 200


def test_staff_with_unconfirmed_address_cannot_set_up_yet(client, staff):
    # allauth's default, kept on purpose; the deploy doc tells staff to confirm first
    EmailAddress.objects.create(user=staff, email=staff.email, primary=True, verified=False)
    client.force_login(staff)

    resp = client.get(reverse('mfa_activate_totp'), follow=True)

    assertRedirects(resp, MFA_INDEX)
    assertContains(resp, 'until you have verified your email address')


def test_member_gets_403_from_admin(client, member):
    client.force_login(member)

    assert client.get(ADMIN_INDEX, follow=True).status_code == 403


def test_switch_off_lets_staff_in_without_authenticator_app(client, staff, mfa_not_required):
    client.force_login(staff)

    assert client.get(ADMIN_INDEX).status_code == 200


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
        ('base', None, True),
        ('base', 'false', False),
        ('development', None, False),
        ('development', 'true', True),
    ],
)
def test_required_unless_switched_off_and_off_by_default_in_development(
    monkeypatch, module, env, expected
):
    if env is None:
        monkeypatch.delenv('DJANGO_STAFF_REQUIRE_MFA', raising=False)
    else:
        monkeypatch.setenv('DJANGO_STAFF_REQUIRE_MFA', env)

    assert load_settings(module).STAFF_REQUIRE_MFA is expected


def test_tests_run_with_the_requirement_on(settings):
    assert settings.STAFF_REQUIRE_MFA is True


# API


@pytest.mark.parametrize('url', ['/api/users/', '/api/forums/'])
def test_api_needs_authenticator_app(staff, url):
    client = APIClient()
    client.force_login(staff)

    resp = client.get(url)

    # The API answers with an error, not with a redirect to a page
    assert resp.status_code == 403
    assert 'need two-factor authentication' in resp.json()['detail']


def test_api_closed_to_moderator_without_authenticator_app(moderator, staff):
    forum = Forum.objects.create(title='Forum', description='A forum')
    thread = Thread.objects.create(title='Thread', text='Text', forum=forum, user=staff)
    client = APIClient()
    client.force_login(moderator)

    assert client.delete(f'/api/threads/{thread.pk}/').status_code == 403
    assert Thread.objects.filter(pk=thread.pk).exists()


def test_api_users_open_to_staff_with_authenticator_app(staff, add_totp):
    add_totp(staff)
    client = APIClient()
    client.force_login(staff)

    assert client.get('/api/users/').status_code == 200


@pytest.mark.parametrize('url', ['/api/users/', '/api/forums/'])
def test_staff_token_is_refused(staff, add_totp, url):
    # Even with an authenticator app: a token never passes the two-factor step
    add_totp(staff)

    resp = token_client(staff).get(url)

    # 403, not 401: DRF answers for its first authentication class (session)
    assert resp.status_code == 403
    assert 'cannot use API tokens' in resp.json()['detail']


def test_privileged_token_is_refused(privileged, add_totp):
    add_totp(privileged)

    resp = token_client(privileged).get('/api/forums/')

    assert resp.status_code == 403
    assert 'cannot use API tokens' in resp.json()['detail']


def test_member_token_still_works(member):
    resp = token_client(member).post('/api/forums/', {'title': 't', 'description': 'd'})

    # Authenticated (403, not 401): members just may not add forums
    assert resp.status_code == 403


def test_switch_off_accepts_staff_token(staff, mfa_not_required):
    assert token_client(staff).get('/api/users/').status_code == 200


def test_switch_off_accepts_privileged_token(privileged, mfa_not_required):
    assert token_client(privileged).get('/api/forums/').status_code == 200


# manage.py remove_mfa


def test_remove_mfa_deletes_the_users_authenticators(staff, member, add_totp):
    add_totp(staff)
    RecoveryCodes.activate(staff)
    add_totp(member)

    call_command('remove_mfa', 'STAFF@example.com')

    assert not Authenticator.objects.filter(user=staff).exists()
    assert Authenticator.objects.filter(user=member).exists()


def test_remove_mfa_lets_the_user_log_in_with_password_only(client, staff, add_totp):
    add_totp(staff)
    call_command('remove_mfa', staff.email)

    client.post(reverse('account_login'), {'login': staff.email, 'password': PASSWORD})

    assert client.session['_auth_user_id'] == str(staff.pk)


@pytest.mark.django_db
def test_remove_mfa_unknown_address_fails():
    with pytest.raises(CommandError, match='No user'):
        call_command('remove_mfa', 'nobody@example.com')
