from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.template.defaultfilters import date as format_date
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains

from users.models import Invitation
from users.tasks import send_invitation_email_task

User = get_user_model()
ADD_URL = reverse('admin:users_invitation_add')
LIST_URL = reverse('admin:users_invitation_changelist')


@pytest.fixture
def staff_client(client, add_totp):
    boss = User.objects.create_superuser(username='boss', email='boss@example.com')
    add_totp(boss)
    client.force_login(boss)
    return client


def invite(staff_client, email, capture, execute=True):
    with capture(execute=execute) as callbacks:
        response = staff_client.post(ADD_URL, {'email': email})
    return response, callbacks


def resend(staff_client, capture, *invitations):
    with capture(execute=True):
        return staff_client.post(
            LIST_URL,
            {'action': 'resend_invitations', '_selected_action': [i.pk for i in invitations]},
            follow=True,
        )


# Adding sends the email


def test_adding_sends_the_invitation_email(
    staff_client, settings, django_capture_on_commit_callbacks
):
    settings.DEFAULT_FROM_EMAIL = 'forum@example.com'
    settings.SITE_URL = 'https://forum.example.org'

    invite(staff_client, 'anna@example.com', django_capture_on_commit_callbacks)

    invitation = Invitation.objects.get(email='anna@example.com')
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ['anna@example.com']
    assert message.from_email == 'forum@example.com'
    link = 'https://forum.example.org' + reverse('accept_invitation', args=[invitation.key])
    assert link in message.body
    assert invitation.sent_at is not None


def test_email_says_when_the_link_expires_and_hides_the_inviter(
    staff_client, django_capture_on_commit_callbacks
):
    invite(staff_client, 'anna@example.com', django_capture_on_commit_callbacks)

    invitation = Invitation.objects.get(email='anna@example.com')
    body = mail.outbox[0].body
    assert format_date(invitation.created + timedelta(days=7), 'j F Y') in body
    assert 'boss@example.com' not in body


def test_email_is_sent_only_after_the_save_commits(
    staff_client, django_capture_on_commit_callbacks
):
    _, callbacks = invite(
        staff_client, 'anna@example.com', django_capture_on_commit_callbacks, execute=False
    )

    assert len(mail.outbox) == 0
    assert len(callbacks) == 1


@pytest.mark.parametrize(
    'change',
    [{'created': timezone.now() - timedelta(days=30)}, {'accepted_at': timezone.now()}],
    ids=['expired', 'used'],
)
def test_task_sends_nothing_for_an_invitation_that_is_no_longer_valid(db, change):
    invitation = Invitation.objects.create(email='anna@example.com', **change)

    send_invitation_email_task(invitation.pk)

    assert len(mail.outbox) == 0
    assert Invitation.objects.get(pk=invitation.pk).sent_at is None


@pytest.mark.django_db
def test_task_ignores_a_deleted_invitation():
    send_invitation_email_task(12345)

    assert len(mail.outbox) == 0


# The add form


def test_adding_refuses_an_address_with_an_account(
    staff_client, django_capture_on_commit_callbacks
):
    User.objects.create_user(username='anna', email='Anna@Example.com')

    response, _ = invite(staff_client, 'anna@example.com', django_capture_on_commit_callbacks)

    assertContains(response, 'This address already has an account.')
    assert not Invitation.objects.exists()
    assert len(mail.outbox) == 0


def test_adding_refuses_an_address_with_a_pending_invitation(
    staff_client, django_capture_on_commit_callbacks
):
    Invitation.objects.create(email='Anna@Example.com')

    response, _ = invite(staff_client, 'anna@example.com', django_capture_on_commit_callbacks)

    assertContains(response, 'This address already has a pending invitation.')
    assert Invitation.objects.count() == 1


def test_adding_allows_an_address_whose_invitation_expired(
    staff_client, django_capture_on_commit_callbacks
):
    Invitation.objects.create(
        email='anna@example.com', created=timezone.now() - timedelta(days=30)
    )

    invite(staff_client, 'anna@example.com', django_capture_on_commit_callbacks)

    assert Invitation.objects.valid().filter(email='anna@example.com').count() == 1
    assert len(mail.outbox) == 1


# Resending


def test_resend_makes_a_new_link_and_sends_it(staff_client, django_capture_on_commit_callbacks):
    invitation = Invitation.objects.create(
        email='anna@example.com', created=timezone.now() - timedelta(days=30)
    )
    old_key = invitation.key

    resend(staff_client, django_capture_on_commit_callbacks, invitation)

    invitation.refresh_from_db()
    assert invitation.key != old_key
    # The 7 days start again, and the old link is dead
    assert invitation.is_valid()
    assert not Invitation.objects.filter(key=old_key).exists()
    assert len(mail.outbox) == 1
    assert reverse('accept_invitation', args=[invitation.key]) in mail.outbox[0].body
    assert invitation.sent_at is not None


def test_resend_skips_used_invitations(staff_client, django_capture_on_commit_callbacks):
    used = Invitation.objects.create(email='anna@example.com', accepted_at=timezone.now())
    old_key = used.key

    response = resend(staff_client, django_capture_on_commit_callbacks, used)

    assert Invitation.objects.get(pk=used.pk).key == old_key
    assert len(mail.outbox) == 0
    assertContains(response, 'Skipped 1')


def test_resend_skips_addresses_that_have_registered(
    staff_client, django_capture_on_commit_callbacks
):
    User.objects.create_user(username='anna', email='anna@example.com')
    pending = Invitation.objects.create(email='anna@example.com')

    response = resend(staff_client, django_capture_on_commit_callbacks, pending)

    assert len(mail.outbox) == 0
    assertContains(response, 'Skipped 1')


def test_list_shows_whether_the_email_was_sent(staff_client):
    Invitation.objects.create(email='anna@example.com')

    assertContains(staff_client.get(LIST_URL), 'column-sent_at')
