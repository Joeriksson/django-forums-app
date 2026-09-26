import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from forums.models import Forum, Thread, UserProfile, Post, Notification, UpVote, Gender


@pytest.mark.django_db
def test_forum_model(add_forum):
    forum = Forum(title='Test Forum', description='This is a Test Forum')
    forum.save()
    assert forum.title == 'Test Forum'
    assert forum.description == 'This is a Test Forum'
    assert str(forum) == f'Forum: {forum.title}'


@pytest.mark.django_db
def test_thread_model():
    forum = Forum(title='Test Forum', description='This is a Test Forum')
    forum.save()
    user = get_user_model().objects.create_user(
        username='forumuser',
        email='forumuser@email.com',
        password='testpass123',
    )
    thread = Thread(
        title='A new thread', text='The text of the thread', forum=forum, user=user
    )
    thread.save()
    assert thread.title == 'A new thread'
    assert thread.text == 'The text of the thread'
    assert thread.forum == forum
    assert thread.user == user
    assert thread.added
    assert thread.edited
    assert str(thread) == f'Thread: {thread.title} - (started by {thread.user})'


'''
Test User model and User Profile model
'''


@pytest.fixture
def test_password():
    return 'strong-test-pass'


@pytest.fixture
def test_email():
    return 'test@email.com'


@pytest.fixture
def create_user(db, django_user_model, test_password, test_email):
    def make_user(**kwargs):
        kwargs['password'] = test_password
        kwargs['email'] = test_email
        if 'username' not in kwargs:
            kwargs['username'] = 'testuser'
        return django_user_model.objects.create_user(**kwargs)

    return make_user


@pytest.mark.django_db
def test_user_model(create_user):
    user = create_user(username='palle')
    assert not user.is_superuser
    assert not user.is_staff


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
def test_notify_subscribers_excludes_post_author(add_forum, add_user, add_thread, monkeypatch):
    """Post author should not receive a notification for their own post."""
    forum = add_forum('Test Forum', 'Description')
    author = add_user('author', 'author@example.com', 'pass123')
    subscriber = add_user('subscriber', 'subscriber@example.com', 'pass123')
    thread = add_thread('Test Thread', 'Thread text', forum, author)

    Notification.objects.create(thread=thread, user=author)
    Notification.objects.create(thread=thread, user=subscriber)

    captured = {}

    def fake_delay(thread_id, thread_title, username, full_url, email_addresses):
        captured['email_addresses'] = email_addresses

    monkeypatch.delenv('CI', raising=False)
    monkeypatch.setattr('forums.tasks.send_notifications_task.delay', fake_delay)

    Post.objects.create(text='A reply', thread=thread, user=author)

    assert 'author@example.com' not in captured.get('email_addresses', [])
    assert 'subscriber@example.com' in captured.get('email_addresses', [])


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
