import pytest
from django.urls import reverse

from forums.models import Notification, UpVote


@pytest.fixture
def thread_with_post(add_user, add_forum, add_thread, add_post):
    author = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title="General Forum", description="This is a general forum")
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=author,
    )
    post = add_post(text='A reply', thread=thread, user=author)
    return thread, post


def upvote_url(post):
    return reverse('post_upvote', kwargs={'tpk': post.thread.id, 'pk': post.id})


def notify_url(thread):
    return reverse('thread_notification', kwargs={'pk': thread.id})


# Upvote


@pytest.mark.django_db
def test_upvote_get_not_allowed(client, add_user, thread_with_post):
    _, post = thread_with_post
    voter = add_user('voter', 'voter@email.com', 'testpass123')
    client.force_login(voter)

    resp = client.get(upvote_url(post))

    assert resp.status_code == 405
    post.refresh_from_db()
    assert post.upvotes == 0
    assert not UpVote.objects.filter(post=post).exists()


@pytest.mark.django_db
def test_upvote_post(client, add_user, thread_with_post):
    thread, post = thread_with_post
    voter = add_user('voter', 'voter@email.com', 'testpass123')
    client.force_login(voter)

    resp = client.post(upvote_url(post))

    assert resp.status_code == 302
    assert resp.url == reverse('thread_detail', kwargs={'pk': thread.id})
    post.refresh_from_db()
    assert post.upvotes == 1
    assert UpVote.objects.filter(post=post, user=voter).count() == 1


@pytest.mark.django_db
def test_upvote_twice_counts_once(client, add_user, thread_with_post):
    _, post = thread_with_post
    voter = add_user('voter', 'voter@email.com', 'testpass123')
    client.force_login(voter)

    client.post(upvote_url(post))
    resp = client.post(upvote_url(post))

    assert resp.status_code == 302
    post.refresh_from_db()
    assert post.upvotes == 1
    assert UpVote.objects.filter(post=post, user=voter).count() == 1


@pytest.mark.django_db
def test_upvote_own_post_forbidden(client, thread_with_post):
    _, post = thread_with_post
    client.force_login(post.user)

    resp = client.post(upvote_url(post))

    assert resp.status_code == 403
    post.refresh_from_db()
    assert post.upvotes == 0
    assert not UpVote.objects.filter(post=post).exists()


@pytest.mark.django_db
def test_upvote_missing_post_returns_404(client, add_user, thread_with_post):
    thread, _ = thread_with_post
    voter = add_user('voter', 'voter@email.com', 'testpass123')
    client.force_login(voter)

    resp = client.post(
        reverse('post_upvote', kwargs={'tpk': thread.id, 'pk': 99999})
    )

    assert resp.status_code == 404


@pytest.mark.django_db
def test_upvote_anonymous_redirects_to_login(client, thread_with_post):
    _, post = thread_with_post

    resp = client.post(upvote_url(post))

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))
    post.refresh_from_db()
    assert post.upvotes == 0


# Subscribe


@pytest.mark.django_db
def test_subscribe_get_not_allowed(client, add_user, thread_with_post):
    thread, _ = thread_with_post
    reader = add_user('reader', 'reader@email.com', 'testpass123')
    client.force_login(reader)

    resp = client.get(notify_url(thread))

    assert resp.status_code == 405
    assert not Notification.objects.filter(thread=thread, user=reader).exists()


@pytest.mark.django_db
def test_subscribe_post_toggles(client, add_user, thread_with_post):
    thread, _ = thread_with_post
    reader = add_user('reader', 'reader@email.com', 'testpass123')
    client.force_login(reader)

    resp = client.post(notify_url(thread))

    assert resp.status_code == 302
    assert resp.url == reverse('thread_detail', kwargs={'pk': thread.id})
    assert Notification.objects.filter(thread=thread, user=reader).count() == 1

    client.post(notify_url(thread))

    assert not Notification.objects.filter(thread=thread, user=reader).exists()


@pytest.mark.django_db
def test_subscribe_missing_thread_returns_404(client, add_user):
    reader = add_user('reader', 'reader@email.com', 'testpass123')
    client.force_login(reader)

    resp = client.post(reverse('thread_notification', kwargs={'pk': 99999}))

    assert resp.status_code == 404


@pytest.mark.django_db
def test_subscribe_anonymous_redirects_to_login(client, thread_with_post):
    thread, _ = thread_with_post

    resp = client.post(notify_url(thread))

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))
    assert not Notification.objects.filter(thread=thread).exists()
