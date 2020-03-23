import pytest
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from forums.models import Forum, Thread, Post


@pytest.fixture(scope="function")
def add_forum():
    def _add_forum(title, description):
        forum = Forum.objects.create(title=title, description=description,)
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


@pytest.fixture(scope="function")
def add_super_user():
    def _add_super_user(username, email, password):
        super_user = get_user_model().objects.create_user(
            username=username,
            email=email,
            password=password,
            is_superuser=True,
        )
        return super_user

    return _add_super_user


@pytest.fixture(scope="function")
def get_user_client():
    def _get_user_client(user):

        token = Token.objects.create(user=user, )

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='TOKEN ' + token.key)

        return client

    return _get_user_client
