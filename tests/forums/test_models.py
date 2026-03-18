import pytest
from django.contrib.auth import get_user_model

from forums.models import Forum, Thread, UserProfile, Post, Notification


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


def test_user_profile_model(create_user):
    user = create_user(username='palle')
    user_profile = UserProfile(user=user, gender='F')

    assert user_profile
    assert user_profile.gender == 'F'


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
