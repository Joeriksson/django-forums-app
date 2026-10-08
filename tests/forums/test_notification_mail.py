"""
The mail about a reply waits a few minutes (Site settings) and goes only to subscribers
who haven't opened the thread by then; the replies that follow send none until they have.
The tests run the task themselves, at the moment the worker would.
"""

import pytest
from django.urls import reverse

from forums.models import Post, Subscription
from forums.tasks import send_notifications_task
from notifications.models import Notification

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@example.com', 'testpass123')


@pytest.fixture
def subscriber(add_user, verify_email):
    return verify_email(add_user('subscriber', 'subscriber@example.com', 'testpass123'))


@pytest.fixture
def thread(add_forum, add_thread, author, subscriber):
    forum = add_forum(title='General', description='Everything')
    thread = add_thread(title='A thread', text='Text', forum=forum, user=author)
    Subscription.objects.create(thread=thread, user=subscriber)
    return thread


@pytest.fixture
def reply(django_capture_on_commit_callbacks):
    """A reply, committed; its mail still waits."""

    def _reply(thread, user):
        with django_capture_on_commit_callbacks(execute=True):
            return Post.objects.create(text='A reply', thread=thread, user=user)

    return _reply


def addresses(mailoutbox):
    return [message.bcc for message in mailoutbox]


# How long the mail waits

def test_the_mail_waits_five_minutes_by_default(thread, author, reply, notification_calls, mailoutbox):
    post = reply(thread, author)

    assert notification_calls == [(post.pk, 5 * 60)]
    assert mailoutbox == []


@pytest.mark.parametrize('minutes', [0, 12])
def test_the_wait_comes_from_the_site_settings(thread, author, reply, notification_calls, site_settings, minutes):
    site_settings(notification_mail_delay=minutes)

    post = reply(thread, author)

    assert notification_calls == [(post.pk, minutes * 60)]


# Who gets it

def test_unread_after_the_wait_gets_the_mail(thread, author, reply, mailoutbox):
    post = reply(thread, author)

    send_notifications_task(post.pk)

    assert addresses(mailoutbox) == [['subscriber@example.com']]


def test_no_mail_to_who_opened_the_thread(client, thread, author, subscriber, reply, mailoutbox):
    post = reply(thread, author)
    client.force_login(subscriber)
    client.get(reverse('thread_detail', args=[thread.pk]))

    send_notifications_task(post.pk)

    assert mailoutbox == []


def test_no_mail_after_mark_all_as_read(client, thread, author, subscriber, reply, mailoutbox):
    post = reply(thread, author)
    client.force_login(subscriber)
    client.post(reverse('notifications_read'))

    send_notifications_task(post.pk)

    assert mailoutbox == []


def test_only_those_who_have_not_read_it(client, thread, author, subscriber, reply, mailoutbox, add_user, verify_email):
    away = verify_email(add_user('away', 'away@example.com', 'testpass123'))
    Subscription.objects.create(thread=thread, user=away)
    post = reply(thread, author)
    client.force_login(subscriber)
    client.get(reverse('thread_detail', args=[thread.pk]))

    send_notifications_task(post.pk)

    assert addresses(mailoutbox) == [['away@example.com']]


def test_one_mail_for_all_who_get_it(thread, author, reply, mailoutbox, add_user, verify_email):
    Subscription.objects.create(
        thread=thread, user=verify_email(add_user('other', 'other@example.com', 'testpass123'))
    )
    post = reply(thread, author)

    send_notifications_task(post.pk)

    assert addresses(mailoutbox) == [['subscriber@example.com', 'other@example.com']]


def test_no_mail_after_unsubscribing_during_the_wait(thread, author, subscriber, reply, mailoutbox):
    post = reply(thread, author)
    Subscription.objects.filter(user=subscriber).delete()

    send_notifications_task(post.pk)

    assert mailoutbox == []


def test_no_mail_to_an_account_deactivated_during_the_wait(thread, author, subscriber, reply, mailoutbox):
    post = reply(thread, author)
    subscriber.is_active = False
    subscriber.save()

    send_notifications_task(post.pk)

    assert mailoutbox == []


# One mail until the member has been there

def test_the_replies_that_follow_send_no_mail(thread, author, reply, mailoutbox):
    first = reply(thread, author)
    second = reply(thread, author)
    third = reply(thread, author)

    for post in (first, second, third):
        send_notifications_task(post.pk)

    assert len(mailoutbox) == 1
    assert f'#post-{first.pk}' in mailoutbox[0].body


def test_a_reply_after_a_visit_is_mailed_again(client, thread, author, subscriber, reply, mailoutbox):
    send_notifications_task(reply(thread, author).pk)
    client.force_login(subscriber)
    client.get(reverse('thread_detail', args=[thread.pk]))

    again = reply(thread, author)
    send_notifications_task(again.pk)

    assert len(mailoutbox) == 2
    assert f'#post-{again.pk}' in mailoutbox[1].body


def test_a_visit_between_two_replies_mails_the_second_only(client, thread, author, subscriber, reply, mailoutbox):
    # Both mails still wait when the member reads the first reply
    first = reply(thread, author)
    client.force_login(subscriber)
    client.get(reverse('thread_detail', args=[thread.pk]))
    second = reply(thread, author)

    send_notifications_task(first.pk)
    send_notifications_task(second.pk)

    (message,) = mailoutbox
    assert f'#post-{second.pk}' in message.body


def test_each_member_is_mailed_about_their_own_first_unread(
    client, thread, author, subscriber, reply, mailoutbox, add_user, verify_email
):
    away = verify_email(add_user('away', 'away@example.com', 'testpass123'))
    Subscription.objects.create(thread=thread, user=away)
    first = reply(thread, author)
    client.force_login(subscriber)
    client.get(reverse('thread_detail', args=[thread.pk]))
    second = reply(thread, author)

    send_notifications_task(first.pk)
    send_notifications_task(second.pk)

    assert addresses(mailoutbox) == [['away@example.com'], ['subscriber@example.com']]


def test_the_author_of_the_reply_gets_no_mail(thread, author, subscriber, reply, mailoutbox, verify_email):
    verify_email(author)
    Subscription.objects.create(thread=thread, user=author)

    send_notifications_task(reply(thread, author).pk)

    assert addresses(mailoutbox) == [['subscriber@example.com']]


# What the mail says

def test_the_link_goes_to_the_reply_on_its_page(thread, author, reply, mailoutbox, site_settings, settings):
    settings.SITE_URL = 'https://forum.example.com'
    site_settings(posts_per_page=2)
    for n in range(4):
        reply(thread, author)
    Notification.objects.update(read=True)
    # The fifth reply is post #6: with the opening post counted, on page 3
    post = reply(thread, author)

    send_notifications_task(post.pk)

    assert f'Url: https://forum.example.com/forums/thread/{thread.pk}?page=3#post-{post.pk}' in mailoutbox[0].body


# Deleted while the mail waited

def test_no_mail_for_a_deleted_reply(thread, author, reply, mailoutbox):
    post = reply(thread, author)
    pk = post.pk
    post.delete()

    send_notifications_task(pk)

    assert mailoutbox == []


def test_no_mail_for_a_deleted_thread(thread, author, reply, mailoutbox):
    pk = reply(thread, author).pk
    thread.delete()

    send_notifications_task(pk)

    assert mailoutbox == []


def test_replies_after_a_deleted_first_one_send_no_mail(thread, author, reply, mailoutbox):
    # Known: the member's news no longer starts at a reply, so nothing is mailed until
    # they have been to the thread. The bell still shows it
    first = reply(thread, author)
    second = reply(thread, author)
    first.delete()

    send_notifications_task(second.pk)

    assert mailoutbox == []
    assert Notification.objects.get().read is False
