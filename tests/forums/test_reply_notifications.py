"""Rows for the notification center: made by a reply, read by opening the thread."""

import pytest
from django.db import transaction
from django.urls import reverse

from forums.models import Post, Subscription
from notifications.models import Notification

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@example.com', 'testpass123')


@pytest.fixture
def subscriber(add_user):
    return add_user('subscriber', 'subscriber@example.com', 'testpass123')


@pytest.fixture
def thread(add_forum, add_thread, author, subscriber):
    forum = add_forum(title='General', description='Everything')
    thread = add_thread(title='A thread', text='Text', forum=forum, user=author)
    Subscription.objects.create(thread=thread, user=subscriber)
    return thread


@pytest.fixture
def reply(django_capture_on_commit_callbacks):
    """A reply, with what happens once it is committed."""

    def _reply(thread, user, text='A reply'):
        with django_capture_on_commit_callbacks(execute=True):
            return Post.objects.create(text=text, thread=thread, user=user)

    return _reply


def test_a_reply_notifies_the_subscriber(thread, author, subscriber, reply):
    post = reply(thread, author)

    notification = Notification.objects.get()
    assert notification.user == subscriber
    assert notification.kind == Notification.Kind.REPLY
    assert notification.thread == thread
    assert notification.post == post
    assert notification.count == 1
    assert notification.read is False


def test_more_replies_are_counted_on_the_same_row(thread, author, subscriber, reply):
    first = reply(thread, author)
    reply(thread, author)
    reply(thread, author)

    notification = Notification.objects.get()
    assert notification.count == 3
    # Still where the reading starts
    assert notification.post == first


def test_a_reply_after_reading_starts_over(thread, author, subscriber, reply):
    reply(thread, author)
    reply(thread, author)
    Notification.objects.update(read=True)

    latest = reply(thread, author)

    notification = Notification.objects.get()
    assert notification.read is False
    assert notification.count == 1
    assert notification.post == latest


def test_the_time_follows_the_latest_reply(thread, author, subscriber, reply):
    reply(thread, author)
    first = Notification.objects.get().updated

    reply(thread, author)

    assert Notification.objects.get().updated > first


def test_the_author_of_the_reply_is_not_notified(thread, author, subscriber, reply):
    Subscription.objects.create(thread=thread, user=author)

    reply(thread, subscriber)

    assert [n.user for n in Notification.objects.all()] == [author]


def test_only_subscribers_are_notified(thread, author, subscriber, reply, add_user):
    add_user('other', 'other@example.com', 'testpass123')

    reply(thread, author)

    assert [n.user for n in Notification.objects.all()] == [subscriber]


def test_a_deactivated_subscriber_is_not_notified(thread, author, subscriber, reply):
    subscriber.is_active = False
    subscriber.save()

    reply(thread, author)

    assert not Notification.objects.exists()


def test_an_unverified_address_does_not_matter(thread, author, subscriber, reply_with_mail, mailoutbox):
    # The mail needs a confirmed address; the notification center is on the site itself
    reply_with_mail(thread, author)

    assert mailoutbox == []
    assert Notification.objects.count() == 1


def test_notified_in_ci_too(thread, author, reply, monkeypatch):
    # CI skips the mail, not the notification center
    monkeypatch.setenv('CI', 'true')

    reply(thread, author)

    assert Notification.objects.count() == 1


def test_each_thread_has_its_own_row(thread, author, subscriber, reply, add_thread):
    other = add_thread(title='Another', text='Text', forum=thread.forum, user=author)
    Subscription.objects.create(thread=other, user=subscriber)

    reply(thread, author)
    reply(other, author)
    reply(other, author)

    counts = dict(Notification.objects.values_list('thread_id', 'count'))
    assert counts == {thread.pk: 1, other.pk: 2}


def test_nothing_for_a_reply_that_is_rolled_back(thread, author, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                Post.objects.create(text='A reply', thread=thread, user=author)
                raise RuntimeError
        except RuntimeError:
            pass

    assert not Notification.objects.exists()


def test_the_queries_do_not_grow_with_the_subscribers(
    thread, author, add_user, django_assert_num_queries, django_capture_on_commit_callbacks
):
    for n in range(5):
        user = add_user(f'user{n}', f'user{n}@example.com', 'testpass123')
        Subscription.objects.create(thread=thread, user=user)
    with django_capture_on_commit_callbacks() as callbacks:
        Post.objects.create(text='A reply', thread=thread, user=author)

    # The subscribers, then inside a savepoint: unread rows, read rows, new rows.
    # Then the site settings, for how long the mail waits
    with django_assert_num_queries(1 + 3 + 2 + 1):
        for callback in callbacks:
            callback()

    assert Notification.objects.count() == 6


def test_a_reply_through_the_api_notifies(thread, author, subscriber, get_user_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = get_user_client(author).post(
            reverse('post-list'), {'text': 'A reply', 'thread': thread.pk}
        )

    assert resp.status_code == 201
    assert Notification.objects.get().user == subscriber


# Reading

def test_opening_the_thread_marks_it_read(client, thread, author, subscriber, reply):
    reply(thread, author)
    client.force_login(subscriber)

    resp = client.get(reverse('thread_detail', args=[thread.pk]))

    assert resp.status_code == 200
    assert Notification.objects.get().read is True


def test_any_page_of_the_thread_marks_it_read(client, thread, author, subscriber, reply, site_settings):
    site_settings(posts_per_page=2)
    for n in range(5):
        reply(thread, author)
    client.force_login(subscriber)

    client.get(reverse('thread_detail', args=[thread.pk]) + '?page=1')

    assert Notification.objects.get().read is True


def test_someone_else_opening_the_thread_changes_nothing(client, thread, author, reply):
    reply(thread, author)
    client.force_login(author)

    client.get(reverse('thread_detail', args=[thread.pk]))

    assert Notification.objects.get().read is False


def test_another_thread_stays_unread(client, thread, author, subscriber, reply, add_thread):
    other = add_thread(title='Another', text='Text', forum=thread.forum, user=author)
    Subscription.objects.create(thread=other, user=subscriber)
    reply(thread, author)
    reply(other, author)
    client.force_login(subscriber)

    client.get(reverse('thread_detail', args=[thread.pk]))

    assert Notification.objects.get(thread=other).read is False
    assert Notification.objects.get(thread=thread).read is True


def test_a_visitor_is_sent_to_the_login_page(client, thread, author, reply):
    reply(thread, author)

    resp = client.get(reverse('thread_detail', args=[thread.pk]))

    assert resp.status_code == 302
    assert Notification.objects.get().read is False


# Deleted content and accounts

def test_deleting_the_first_unread_reply_keeps_the_notification(thread, author, subscriber, reply):
    first = reply(thread, author)
    reply(thread, author)

    first.delete()

    notification = Notification.objects.get()
    assert notification.post is None
    assert notification.count == 2
    assert notification.read is False


def test_a_reply_after_that_is_still_counted(thread, author, subscriber, reply):
    reply(thread, author).delete()

    reply(thread, author)

    notification = Notification.objects.get()
    assert notification.count == 2
    assert notification.post is None


def test_deleting_the_thread_removes_its_notifications(thread, author, reply):
    reply(thread, author)

    thread.delete()

    assert not Notification.objects.exists()


def test_deleting_the_account_removes_its_notifications(thread, author, subscriber, reply):
    reply(thread, author)

    subscriber.delete()

    assert not Notification.objects.exists()


def test_unsubscribing_stops_new_notifications_but_keeps_the_row(thread, author, subscriber, reply):
    reply(thread, author)
    Subscription.objects.filter(user=subscriber).delete()

    reply(thread, author)

    assert Notification.objects.get().count == 1
