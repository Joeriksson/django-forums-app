"""Rows for the notification center: made by a direct message, read by opening the conversation."""

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from conversations.models import Conversation, Message, send
from forums.models import Forum, Thread
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


# The notifications page and the bell


def test_the_bell_counts_a_conversation_once(anna, bo, write, client):
    write(anna, bo)
    write(anna, bo)
    client.force_login(bo)

    assert client.get(reverse('notifications_count')).json() == {'unread': 1}


def test_the_page_lists_the_messages_with_a_link_to_the_conversation(anna, bo, write, client):
    write(anna, bo, 'The text itself')
    write(anna, bo)
    client.force_login(bo)

    resp = client.get(reverse('notifications'))

    url = reverse('conversation', kwargs={'pk': anna.pk})
    assertContains(resp, f'href="{url}">Messages with Member {anna.pk}</a>')
    assertContains(resp, '<strong>2</strong> new messages')
    # Not the text, and never the username
    assertNotContains(resp, 'The text itself')
    assertNotContains(resp, '>anna<')


def test_following_the_link_marks_the_row_read(anna, bo, write, client):
    write(anna, bo)
    client.force_login(bo)
    url = client.get(reverse('notifications')).context['notifications'][0].url

    client.get(url)

    resp = client.get(reverse('notifications'))
    assertContains(resp, 'Read')
    assertNotContains(resp, 'new message')
    assert client.get(reverse('notifications_count')).json() == {'unread': 0}


def test_mark_all_as_read_covers_messages(anna, bo, write, client):
    write(anna, bo)
    client.force_login(bo)

    client.post(reverse('notifications_read'))

    assert Notification.objects.get().read is True


def test_replies_and_messages_share_the_page(anna, bo, write, client):
    forum = Forum.objects.create(title='General', description='Everything')
    thread = Thread.objects.create(title='A thread', text='Text', forum=forum, user=anna)
    Notification.objects.create(user=bo, thread=thread)
    write(anna, bo)
    client.force_login(bo)

    resp = client.get(reverse('notifications'))

    assert len(resp.context['notifications']) == 2
    assertContains(resp, 'A thread')
    assertContains(resp, '<strong>1</strong> new message')


def test_the_page_still_uses_one_query(anna, bo, write, client, django_assert_num_queries):
    for n in range(3):
        write(add_member(f'member{n}'), bo)
    write(anna, bo)
    client.force_login(bo)
    client.get(reverse('notifications'))

    # Eight for the logged-in member, then the rows with both members of each conversation
    with django_assert_num_queries(8 + 1):
        client.get(reverse('notifications'))
