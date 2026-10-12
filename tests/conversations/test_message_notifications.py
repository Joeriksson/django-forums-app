"""Rows for the notification center: made by a direct message, read by opening the conversation."""

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse

from conversations.models import Conversation, Message, send
from notifications import events
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def add_member(name):
    return get_user_model().objects.create_user(
        username=name, email=f'{name}@example.com', password='testpass123'
    )


@pytest.fixture
def anna():
    return add_member('anna')


@pytest.fixture
def bo():
    return add_member('bo')


@pytest.fixture
def write(django_capture_on_commit_callbacks):
    """A message, with what happens once it is committed."""

    def _write(sender, receiver, text='Hello'):
        with django_capture_on_commit_callbacks(execute=True):
            return send(sender, receiver, text)

    return _write


def test_a_message_notifies_the_receiver(anna, bo, write):
    message = write(anna, bo)

    notification = Notification.objects.get()
    assert notification.user == bo
    assert notification.kind == Notification.Kind.MESSAGE
    assert notification.conversation == message.conversation
    assert notification.message == message
    assert notification.thread is None
    assert notification.count == 1
    assert notification.read is False


def test_more_messages_are_counted_on_the_same_row(anna, bo, write):
    first = write(anna, bo)
    write(anna, bo)
    write(anna, bo)

    notification = Notification.objects.get()
    assert notification.count == 3
    # Still where the reading starts
    assert notification.message == first


def test_a_message_after_reading_starts_over(anna, bo, write):
    write(anna, bo)
    write(anna, bo)
    events.conversation_opened(bo, Conversation.between(anna, bo))
    assert Notification.objects.get().read is True

    latest = write(anna, bo)

    notification = Notification.objects.get()
    assert notification.read is False
    assert notification.count == 1
    assert notification.message == latest


def test_an_answer_notifies_the_other_member(anna, bo, write):
    write(anna, bo)
    write(bo, anna)

    assert {n.user: n.count for n in Notification.objects.all()} == {anna: 1, bo: 1}


def test_opening_marks_only_the_readers_row(anna, bo, write):
    write(anna, bo)
    write(bo, anna)

    events.conversation_opened(bo, Conversation.between(anna, bo))

    assert {n.user: n.read for n in Notification.objects.all()} == {anna: False, bo: True}


def test_each_conversation_has_its_own_row(anna, bo, write):
    cia = add_member('cia')
    write(anna, bo)
    write(cia, bo)
    write(cia, bo)

    counts = {n.conversation.other_id(bo.pk): n.count for n in Notification.objects.all()}
    assert counts == {anna.pk: 1, cia.pk: 2}


def test_a_deactivated_receiver_is_not_notified(anna, bo, write):
    bo.is_active = False
    bo.save()

    write(anna, bo)

    assert Message.objects.count() == 1
    assert not Notification.objects.exists()


def test_a_message_rolled_back_notifies_nobody(anna, bo, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                send(anna, bo, 'Hello')
                raise RuntimeError
        except RuntimeError:
            pass

    assert not Message.objects.exists()
    assert not Notification.objects.exists()


def test_the_queries_of_notifying(anna, bo, write, django_assert_num_queries):
    message = write(anna, bo)

    # The receiver, then inside a savepoint: an unread row, a read row, a new row
    with django_assert_num_queries(1 + 3 + 2):
        events.message_sent(message)


def test_a_deleted_first_message_leaves_the_row(anna, bo, write):
    first = write(anna, bo)
    write(anna, bo)

    first.delete()

    notification = Notification.objects.get()
    assert notification.message is None
    assert notification.count == 2


def test_deleting_the_senders_account_deletes_the_row(anna, bo, write):
    write(anna, bo)

    anna.delete()

    assert not Notification.objects.exists()


def test_the_bell_counts_a_message_and_the_page_lists_replies_only(anna, bo, write, client):
    # Until the conversation pages exist there is nowhere for the row to lead
    write(anna, bo)
    client.force_login(bo)

    assert client.get(reverse('notifications_count')).json() == {'unread': 1}
    assert client.get(reverse('notifications')).context['notifications'] == []
