"""The page with one other member's messages, and sending the next one."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects
from rest_framework.throttling import SimpleRateThrottle

from conversations.models import Conversation, Message, send
from forums.models import Forum, Thread
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
def as_anna(client, anna):
    client.force_login(anna)
    return client


def page(user):
    return reverse('conversation', kwargs={'pk': user.pk})


def test_the_address():
    assert reverse('conversation', kwargs={'pk': 7}) == '/messages/7/'


def test_a_visitor_is_sent_to_the_login_page(client, bo):
    for resp in (client.get(page(bo)), client.post(page(bo), {'text': 'Hello'})):
        assert resp.status_code == 302
        assert resp.url.startswith(reverse('account_login'))
    assert not Message.objects.exists()


def test_a_conversation_not_yet_started_is_an_empty_page(as_anna, bo):
    resp = as_anna.get(page(bo))

    assertContains(resp, 'No messages yet.')
    assertContains(resp, f'Member {bo.pk}')
    # Looking doesn't start it
    assert not Conversation.objects.exists()


def test_the_messages_are_shown_oldest_first_with_their_senders(as_anna, anna, bo):
    send(anna, bo, 'The first one')
    send(bo, anna, 'The **second** one')

    resp = as_anna.get(page(bo))

    assert [message.text for message in resp.context['messages_page']] == [
        'The first one',
        'The **second** one',
    ]
    assertContains(resp, '<strong>second</strong>')
    assertContains(resp, f'Member {anna.pk}')
    assertNotContains(resp, 'No messages yet.')


def test_the_page_never_shows_the_username_or_address(as_anna, anna, bo):
    send(bo, anna, 'Hello')

    resp = as_anna.get(page(bo))

    assertNotContains(resp, 'bo@example.com')
    assertNotContains(resp, '>bo<')


def test_only_the_pairs_messages_are_shown(as_anna, anna, bo):
    cia = add_member('cia')
    send(bo, cia, 'Not for Anna')
    send(cia, anna, 'From Cia')

    resp = as_anna.get(page(bo))

    assertNotContains(resp, 'Not for Anna')
    assertNotContains(resp, 'From Cia')


@pytest.mark.parametrize('who', ['oneself', 'nobody', 'deactivated'])
def test_no_page_for_oneself_a_missing_or_a_deactivated_member(as_anna, anna, bo, who):
    bo.is_active = False
    bo.save()
    url = {'oneself': page(anna), 'nobody': '/messages/999999/', 'deactivated': page(bo)}[who]

    assert as_anna.get(url).status_code == 404
    assert as_anna.post(url, {'text': 'Hello'}).status_code == 404
    assert not Message.objects.exists()


def test_sending_saves_the_message_and_returns_to_it(as_anna, anna, bo):
    resp = as_anna.post(page(bo), {'text': 'Hello Bo'})

    message = Message.objects.get()
    assert (message.sender, message.text) == (anna, 'Hello Bo')
    assert message.conversation == Conversation.between(anna, bo)
    assertRedirects(resp, f'{page(bo)}#message-{message.pk}', fetch_redirect_response=False)


def test_sending_notifies_the_receiver(as_anna, bo, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        as_anna.post(page(bo), {'text': 'Hello Bo'})

    notification = Notification.objects.get()
    assert (notification.user, notification.kind) == (bo, Notification.Kind.MESSAGE)


def test_an_empty_or_too_long_message_is_refused(as_anna, bo):
    for text in ('', '   ', 'x' * 20_001):
        resp = as_anna.post(page(bo), {'text': text})

        assert resp.status_code == 200
        assert resp.context['form'].errors['text']
    assert not Message.objects.exists()


def test_the_longest_message_is_accepted(as_anna, bo):
    assert as_anna.post(page(bo), {'text': 'x' * 20_000}).status_code == 302


def test_opening_marks_the_readers_notification_read(
    client, anna, bo, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        send(anna, bo, 'Hello')
        send(bo, anna, 'Hello yourself')
    client.force_login(bo)

    client.get(page(anna))

    assert {n.user: n.read for n in Notification.objects.all()} == {anna: False, bo: True}


def test_the_page_opens_on_the_newest_messages(as_anna, anna, bo, site_settings):
    site_settings(posts_per_page=2)
    for n in range(1, 6):
        send(bo, anna, f'Message {n}')

    newest = as_anna.get(page(bo))
    first = as_anna.get(page(bo) + '?page=1')

    assert [m.text for m in newest.context['messages_page']] == ['Message 5']
    assert [m.text for m in first.context['messages_page']] == ['Message 1', 'Message 2']
    assertContains(newest, 'Page 3 of 3')
    assertContains(newest, 'Earlier messages')
    assertContains(first, 'Later messages')


def test_default_rates():
    assert SimpleRateThrottle.THROTTLE_RATES['message_burst'] == '10/min'
    assert SimpleRateThrottle.THROTTLE_RATES['message_hour'] == '60/hour'


def test_messages_over_the_limit_are_refused_and_the_text_kept(
    as_anna, anna, bo, monkeypatch, security_log
):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, 'message_burst', '2/min')

    assert [as_anna.post(page(bo), {'text': 'Hi'}).status_code for _ in range(2)] == [302, 302]
    resp = as_anna.post(page(bo), {'text': 'My long message'})

    assertContains(resp, 'sending messages too fast', status_code=429)
    assertContains(resp, 'My long message', status_code=429)
    assert Message.objects.count() == 2
    assert security_log()[-1].startswith(f'denied status=429 user={anna.pk} method=POST')


def test_a_refused_form_does_not_count_and_posts_have_their_own_limit(
    as_anna, anna, bo, monkeypatch
):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, 'message_burst', '1/min')
    forum = Forum.objects.create(title='General', description='Everything')
    thread = Thread.objects.create(title='A thread', text='Text', forum=forum, user=bo)

    as_anna.post(page(bo), {'text': ''})
    assert as_anna.post(page(bo), {'text': 'Hi'}).status_code == 302
    assert as_anna.post(page(bo), {'text': 'Hi again'}).status_code == 429
    # A reply in a thread is counted elsewhere
    reply = as_anna.post(reverse('post_add', kwargs={'pk': thread.pk}), {'text': 'A reply'})
    assert reply.status_code == 302


def test_the_page_costs_a_fixed_number_of_queries(as_anna, anna, bo, django_assert_num_queries):
    for n in range(6):
        send(bo if n % 2 else anna, anna if n % 2 else bo, f'Message {n}')
    as_anna.get(page(bo))

    # Eight for a logged-in page, then: the other member, the conversation, the count
    # and the page of messages, the notification marked read
    with django_assert_num_queries(8 + 5):
        as_anna.get(page(bo))
