import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from forums.models import Forum, Thread, Post
from users.security import is_privileged


@pytest.fixture(scope="function")
def add_forum():
    def _add_forum(title, description):
        forum = Forum.objects.create(
            title=title,
            description=description,
        )
        return forum

    return _add_forum


@pytest.fixture(scope="function")
def add_thread():
    def _add_thread(title, text, forum, user):
        thread = Thread.objects.create(title=title, text=text, forum=forum, user=user)
        return thread

    return _add_thread


@pytest.fixture(scope="function")
def add_post():
    def _add_post(text, thread, user):
        post = Post.objects.create(text=text, thread=thread, user=user)
        return post

    return _add_post


@pytest.fixture(scope="function")
def add_user():
    def _add_user(username, email, password):
        user = get_user_model().objects.create_user(
            username=username,
            email=email,
            password=password,
        )
        return user

    return _add_user


@pytest.fixture
def reader(db):
    """A plain member: reading the forum needs a login."""
    return get_user_model().objects.create_user(
        username='reader', email='reader@example.com', password='testpass123'
    )


@pytest.fixture(scope="function")
def add_super_user():
    def _add_super_user(username, email, password):
        super_user = get_user_model().objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        return super_user

    return _add_super_user


@pytest.fixture(scope="function")
def get_user_client(add_totp):
    def _get_user_client(user):
        client = APIClient()

        # Staff and moderator tokens are refused: they use a session, with an authenticator app
        if is_privileged(user):
            add_totp(user)
            client.force_login(user)
            return client

        token = Token.objects.create(
            user=user,
        )
        client.credentials(HTTP_AUTHORIZATION=f'TOKEN {token.key}')

        return client

    return _get_user_client


@pytest.fixture
def rates(monkeypatch):
    """Lower a throttle rate for the test: DRF reads the rates when it is imported."""

    def _rates(**rates):
        for scope, rate in rates.items():
            monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, rate)

    return _rates
