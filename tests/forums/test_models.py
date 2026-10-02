import pytest
from django.db import IntegrityError

from forums.models import UserProfile, Post, Notification, UpVote, Gender


@pytest.mark.django_db
def test_forum_model(add_forum):
    forum = add_forum('Test Forum', 'This is a Test Forum')
    assert forum.title == 'Test Forum'
    assert forum.description == 'This is a Test Forum'
    assert str(forum) == f'Forum: {forum.title}'


@pytest.mark.django_db
def test_thread_model(add_forum, add_user, add_thread):
    forum = add_forum('Test Forum', 'This is a Test Forum')
    user = add_user('forumuser', 'forumuser@email.com', 'testpass123')
    thread = add_thread('A new thread', 'The text of the thread', forum, user)
    assert thread.title == 'A new thread'
    assert thread.text == 'The text of the thread'
    assert thread.forum == forum
    assert thread.user == user
    assert thread.added
    assert thread.edited
    assert str(thread) == f'Thread: {thread.title} - (started by {thread.user})'


@pytest.mark.django_db
def test_profile_created_for_new_user(add_user):
    user = add_user('palle', 'palle@example.com', 'pass123')

    profiles = UserProfile.objects.filter(user=user)
    assert profiles.count() == 1
    assert profiles.get().gender == Gender.NOTPROVIDED


@pytest.mark.django_db
def test_saving_user_again_does_not_duplicate_profile(add_user):
    user = add_user('palle', 'palle@example.com', 'pass123')

    user.first_name = 'Palle'
    user.save()

    assert UserProfile.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_notify_subscribers_excludes_post_author(
    add_forum, add_user, add_thread, notification_calls, settings, django_capture_on_commit_callbacks,
    verify_email,
):
    """Post author should not receive a notification for their own post."""
    settings.SITE_URL = 'https://forum.example.com'
    forum = add_forum('Test Forum', 'Description')
    author = verify_email(add_user('author', 'author@example.com', 'pass123'))
    subscriber = verify_email(add_user('subscriber', 'subscriber@example.com', 'pass123'))
    thread = add_thread('Test Thread', 'Thread text', forum, author)

    Notification.objects.create(thread=thread, user=author)
    Notification.objects.create(thread=thread, user=subscriber)

    # The hook runs once the post is committed
    with django_capture_on_commit_callbacks(execute=True):
        Post.objects.create(text='A reply', thread=thread, user=author)

    assert len(notification_calls) == 1
    thread_id, thread_title, username, full_url, email_addresses = notification_calls[0]
    assert thread_id == thread.id
    assert thread_title == 'Test Thread'
    # The name others see, not the username (derived from the email address)
    assert username == f'Member {author.pk}'
    # Built from DJANGO_SITE_URL, like invitation links
    assert full_url == f'https://forum.example.com/forums/thread/{thread.id}'
    # Exact list: no author, no duplicates
    assert email_addresses == ['subscriber@example.com']


@pytest.mark.django_db
@pytest.mark.parametrize('author_subscribed', [True, False], ids=['author-only', 'nobody'])
def test_no_notification_task_without_recipients(
    add_forum, add_user, add_thread, notification_calls, author_subscribed,
    django_capture_on_commit_callbacks,
):
    """No task is queued when nobody besides the author would get the email."""
    forum = add_forum('Test Forum', 'Description')
    author = add_user('author', 'author@example.com', 'pass123')
    thread = add_thread('Test Thread', 'Thread text', forum, author)

    if author_subscribed:
        Notification.objects.create(thread=thread, user=author)

    # The hook runs once the post is committed
    with django_capture_on_commit_callbacks(execute=True):
        Post.objects.create(text='A reply', thread=thread, user=author)

    assert notification_calls == []


@pytest.mark.django_db
def test_no_notification_task_in_ci(
    add_forum, add_user, add_thread, notification_calls, monkeypatch, django_capture_on_commit_callbacks
):
    """No task is queued in CI, even when another user is subscribed."""
    forum = add_forum('Test Forum', 'Description')
    author = add_user('author', 'author@example.com', 'pass123')
    subscriber = add_user('subscriber', 'subscriber@example.com', 'pass123')
    thread = add_thread('Test Thread', 'Thread text', forum, author)

    Notification.objects.create(thread=thread, user=subscriber)

    monkeypatch.setenv('CI', 'true')

    # The hook runs once the post is committed
    with django_capture_on_commit_callbacks(execute=True):
        Post.objects.create(text='A reply', thread=thread, user=author)

    assert notification_calls == []


@pytest.mark.django_db
def test_upvote_unique_per_user(add_forum, add_user, add_thread, add_post):
    forum = add_forum('Test Forum', 'Description')
    author = add_user('author', 'author@example.com', 'pass123')
    voter = add_user('voter', 'voter@example.com', 'pass123')
    thread = add_thread('Test Thread', 'Thread text', forum, author)
    post = add_post('A reply', thread, author)

    UpVote.objects.create(post=post, user=voter)

    with pytest.raises(IntegrityError):
        UpVote.objects.create(post=post, user=voter)


@pytest.mark.django_db
def test_notification_unique_per_user(add_forum, add_user, add_thread):
    forum = add_forum('Test Forum', 'Description')
    author = add_user('author', 'author@example.com', 'pass123')
    subscriber = add_user('subscriber', 'subscriber@example.com', 'pass123')
    thread = add_thread('Test Thread', 'Thread text', forum, author)

    Notification.objects.create(thread=thread, user=subscriber)

    with pytest.raises(IntegrityError):
        Notification.objects.create(thread=thread, user=subscriber)
