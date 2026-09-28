import pytest
from rest_framework import status
from rest_framework.test import APIClient

from forums.models import Post


@pytest.mark.django_db
def test_add_post(add_user, get_user_client, add_forum, add_thread):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=user,
    )

    client = get_user_client(user)

    resp = client.post(
        "/api/posts/",
        {
            "text": "This is a new reply in a thread",
            "thread": thread.id,
            "user": user.id,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["text"] == "This is a new reply in a thread"

    assert Post.objects.filter(thread=thread).count() == 1


@pytest.mark.django_db
def test_add_post_not_logged_in(add_forum, add_thread, add_user):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=user,
    )

    client = APIClient()

    resp = client.post(
        "/api/posts/",
        {
            "text": "This is a new reply in a thread",
            "thread": thread.id,
            "user": user.id,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN

    assert Post.objects.filter(thread=thread).count() == 0
