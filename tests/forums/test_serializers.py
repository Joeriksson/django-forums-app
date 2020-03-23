import pytest

from api.serializers import ForumSerializer, ThreadSerializer, UserSerializer, PostSerializer


def test_valid_forum_serializer():
    valid_serializer_data = {
        'title': 'General Forum',
        'description': 'A General Forum',
    }
    serializer = ForumSerializer(data=valid_serializer_data)
    assert serializer.is_valid()
    assert serializer.validated_data == valid_serializer_data
    assert serializer.data == valid_serializer_data
    assert serializer.errors == {}


def test_invalid_forum_serializer():
    invalid_serializer_data = {
        'title': 'General Forum',
    }
    serializer = ForumSerializer(data=invalid_serializer_data)
    assert not serializer.is_valid()
    assert serializer.validated_data == {}
    assert serializer.data == invalid_serializer_data
    assert serializer.errors == {"description": ["This field is required."]}


@pytest.mark.django_db
def test_valid_thread_serializer(add_forum, add_user):
    forum = add_forum(title='General Forum', description='A general forum')
    user = add_user(username='testuser', email='test@email.com', password='testpass123')
    valid_serializer_data = {
        'forum': forum.id,
        'title': 'General Forum',
        'text': 'A General Forum',
        'user': user.id,
    }
    serializer = ThreadSerializer(data=valid_serializer_data)
    assert serializer.is_valid()
    assert serializer.data == valid_serializer_data
    assert serializer.errors == {}


@pytest.mark.django_db
def test_invalid_thread_serializer(add_forum, add_user):
    forum = add_forum(title='General Forum', description='A general forum')
    user = add_user(username='testuser', email='test@email.com', password='testpass123')
    invalid_serializer_data = {
        'forum': forum.id,
        'title': 'General Forum',
        'user': user.id,
    }
    serializer = ThreadSerializer(data=invalid_serializer_data)

    assert not serializer.is_valid()
    assert serializer.validated_data == {}
    assert serializer.data == invalid_serializer_data
    assert serializer.errors == {"text": ["This field is required."]}


@pytest.mark.django_db
def test_valid_post_serializer(add_thread, add_forum, add_user):
    forum = add_forum(title='General Forum', description='A general forum')
    user = add_user(username='testuser', email='test@email.com', password='testpass123')
    thread = add_thread(title='A new thread', text='text in the thread', forum=forum, user=user)
    valid_serializer_data = {
        'text': 'A General Forum',
        'thread': thread.id,
        'forum': forum.id,
        'user': user.id,
    }
    serializer = PostSerializer(data=valid_serializer_data)

    assert serializer.is_valid()
    assert serializer.errors == {}


@pytest.mark.django_db
def test_invalid_post_serializer(add_thread, add_forum, add_user):
    forum = add_forum(title='General Forum', description='A general forum')
    user = add_user(username='testuser', email='test@email.com', password='testpass123')
    thread = add_thread(title='A new thread', text='text in the thread', forum=forum, user=user)
    invalid_serializer_data = {
        'text': 'A General Forum',
        'forum': forum.id,
        'user': user.id,
    }
    serializer = PostSerializer(data=invalid_serializer_data)
    assert not serializer.is_valid()
    assert serializer.validated_data == {}
    assert serializer.errors == {"thread": ["This field is required."]}


@pytest.mark.django_db
def test_valid_user_serializer(add_user):
    valid_serializer_data = {
        'username': 'testuser',
        'email': 'test@email.com',
    }
    serializer = UserSerializer(data=valid_serializer_data)
    assert serializer.is_valid()
    # assert serializer.validated_data == valid_serializer_data
    # assert serializer.data == valid_serializer_data
    assert serializer.errors == {}


@pytest.mark.django_db
def test_invalid_user_serializer(add_user):
    invalid_serializer_data = {
        'password': 'testuser',
    }
    serializer = UserSerializer(data=invalid_serializer_data)
    assert not serializer.is_valid()
    assert serializer.validated_data == {}
    assert serializer.data == {}
    assert serializer.errors == {"username": ["This field is required."]}
