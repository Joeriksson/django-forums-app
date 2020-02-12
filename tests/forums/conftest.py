import pytest
from django.contrib.auth import get_user_model
from forums.models import Forum, Thread


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
