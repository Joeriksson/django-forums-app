"""
The mail about a direct message follows the rule for replies: it waits a few minutes
(Site settings) and goes to the receiver only if they haven't opened the conversation
by then; the messages that follow send none until they have. The tests run the task
themselves, at the moment the worker would.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

from conversations.models import Block, send
from conversations.tasks import send_message_mail_task
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def add_member(name):
    return get_user_model().objects.create_user(
        username=name, email=f'{name}@example.com', password='testpass123'
    )


@pytest.fixture
def anna(verify_email):
    return verify_email(add_member('anna'))


@pytest.fixture
def bo(verify_email):
    return verify_email(add_member('bo'))


@pytest.fixture
def write(django_capture_on_commit_callbacks):
    """A message, committed; its mail still waits."""

    def _write(sender, receiver, text='Hello'):
        with django_capture_on_commit_callbacks(execute=True):
            return send(sender, receiver, text)

    return _write


# How long the mail waits


def test_the_mail_waits_five_minutes_by_default(anna, bo, write, message_mail_calls, mailoutbox):
    message = write(anna, bo)

    assert message_mail_calls == [(message.pk, 5 * 60)]
    assert mailoutbox == []


@pytest.mark.parametrize('minutes', [0, 12])
def test_the_wait_comes_from_the_site_settings(anna, bo, write, message_mail_calls, site_settings, minutes):
    site_settings(notification_mail_delay=minutes)

    message = write(anna, bo)

    assert message_mail_calls == [(message.pk, minutes * 60)]


def test_nothing_is_queued_in_ci_or_for_a_deactivated_receiver(anna, bo, write, message_mail_calls, monkeypatch):
    monkeypatch.setenv('CI', 'true')
    write(anna, bo)
    monkeypatch.delenv('CI')
    bo.is_active = False
    bo.save()
    write(anna, bo)

    assert message_mail_calls == []
    # The notification center was told the first time all the same
    assert Notification.objects.count() == 1


def test_a_message_rolled_back_queues_nothing(anna, bo, message_mail_calls):
    send(anna, bo, 'Hello')

    assert message_mail_calls == []


def test_the_posting_mail_is_not_queued_for_a_message(anna, bo, write, notification_calls):
    write(anna, bo)

    assert notification_calls == []


# What the mail says


def test_the_mail_names_the_sender_and_links_to_the_conversation(anna, bo, write, mailoutbox, settings):
    message = write(anna, bo, 'The text itself')

    send_message_mail_task(message.pk)

    mail = mailoutbox[0]
    assert mail.bcc == ['bo@example.com']
    assert mail.to == []
    assert mail.subject.endswith(f'New message from Member {anna.pk}')
    assert f'Member {anna.pk} has sent you a message.' in mail.body
    assert f"{settings.SITE_URL}{reverse('conversation', kwargs={'pk': anna.pk})}" in mail.body
    # A link, never the text; and never the sender's username or address
    assert 'The text itself' not in mail.body
    assert 'anna@example.com' not in mail.body + mail.subject


def test_the_mail_is_in_the_site_language(anna, bo, write, mailoutbox, monkeypatch):
    monkeypatch.setattr(
        translation._trans,
        'gettext',
        lambda message: f'<{translation.get_language()}>{message}',
        raising=False,
    )
    message = write(anna, bo)

    with translation.override('sv'):
        send_message_mail_task(message.pk)

    assert '<en>New message from <en>Member' in mailoutbox[0].subject
    assert '<sv>' not in mailoutbox[0].subject + mailoutbox[0].body


# Who gets it


def test_who_opened_the_conversation_gets_no_mail(anna, bo, write, client, mailoutbox):
    message = write(anna, bo)
    client.force_login(bo)
    client.get(reverse('conversation', kwargs={'pk': anna.pk}))

    send_message_mail_task(message.pk)

    assert mailoutbox == []


def test_who_marked_all_as_read_gets_no_mail(anna, bo, write, client, mailoutbox):
    message = write(anna, bo)
    client.force_login(bo)
    client.post(reverse('notifications_read'))

    send_message_mail_task(message.pk)

    assert mailoutbox == []


def test_one_mail_for_several_messages_until_the_receiver_has_been_there(anna, bo, write, client, mailoutbox):
    messages = [write(anna, bo) for _ in range(3)]
    for message in messages:
        send_message_mail_task(message.pk)
    assert len(mailoutbox) == 1

    client.force_login(bo)
    client.get(reverse('conversation', kwargs={'pk': anna.pk}))
    later = write(anna, bo)
    send_message_mail_task(later.pk)

    assert len(mailoutbox) == 2


def test_the_sender_gets_no_mail_about_their_own_message(anna, bo, write, mailoutbox):
    write(bo, anna)
    mine = write(anna, bo)

    send_message_mail_task(mine.pk)

    assert [mail.bcc for mail in mailoutbox] == [['bo@example.com']]


def test_an_unconfirmed_address_gets_no_mail(anna, write, mailoutbox):
    cia = add_member('cia')
    message = write(anna, cia)

    send_message_mail_task(message.pk)

    assert mailoutbox == []
    assert Notification.objects.get().user == cia


def test_an_account_deactivated_during_the_wait_gets_no_mail(anna, bo, write, mailoutbox):
    message = write(anna, bo)
    bo.is_active = False
    bo.save()

    send_message_mail_task(message.pk)

    assert mailoutbox == []


def test_a_block_during_the_wait_stops_the_mail(anna, bo, write, mailoutbox):
    message = write(anna, bo)
    Block.objects.create(blocker=bo, blocked=anna)

    send_message_mail_task(message.pk)

    assert mailoutbox == []


def test_the_senders_own_block_during_the_wait_does_not_stop_it(anna, bo, write, mailoutbox):
    # The receiver still has a message to read
    message = write(anna, bo)
    Block.objects.create(blocker=anna, blocked=bo)

    send_message_mail_task(message.pk)

    assert len(mailoutbox) == 1


def test_an_account_deleted_during_the_wait_sends_nothing(anna, bo, write, mailoutbox):
    message = write(anna, bo)
    anna.delete()

    send_message_mail_task(message.pk)

    assert mailoutbox == []


def test_the_task_costs_a_fixed_number_of_queries(anna, bo, write, django_assert_num_queries):
    message = write(anna, bo)

    # The message with its sender, the receiver's unread notification and address, the block
    with django_assert_num_queries(3):
        send_message_mail_task(message.pk)
