import json

import pytest
from rest_framework.test import APIClient

from forums.models import Thread


@pytest.mark.django_db
def test_add_thread(add_user, get_user_client, add_forum):
    forum = add_forum(title="General Forum", description="This is a general forum")

    user = add_user('user', 'user@email.com', 'testpass123')
    client = get_user_client(user)

    resp = client.post(
        "/api/threads/",
        json.dumps(
            {"title": "A thread in the General Forum", "text": "This is a new thread", "forum": forum.id,
             "user": user.id}),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert resp.data["title"] == "A thread in the General Forum"

    threads = Thread.objects.all()
    assert len(threads) == 1


@pytest.mark.django_db
def test_add_thread_not_logged_in(add_forum, add_user):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')

    client = APIClient()

    resp = client.post(
        "/api/threads/",
        json.dumps({"title": "A thread in the General Forum", "text": "This is a new thread", "forum": forum.id,
                    "user": user.id}),
        content_type="application/json",
    )

    assert resp.status_code == 403

    threads = Thread.objects.all()
    assert len(threads) == 0


@pytest.mark.django_db
def test_remove_thread(add_forum, add_user, add_thread, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    thread = add_thread(title='A thread in the General Forum', text='This is a new thread', forum=forum,
                        user=user)

    client = get_user_client(user)

    resp = client.get(f"/api/threads/{thread.id}/")
    assert resp.status_code == 200
    assert resp.data["title"] == "A thread in the General Forum"

    resp_two = client.delete(f"/api/threads/{thread.id}/")
    assert resp_two.status_code == 204

    forums = Thread.objects.all()
    assert len(forums) == 0


@pytest.mark.django_db
def test_remove_thread_incorrect_id(add_user, get_user_client):
    user = add_user('user', 'user@email.com', 'testpass123')
    client = get_user_client(user)

    resp = client.delete(f"/api/threads/99/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_update_thread(add_forum, add_user, add_thread, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")

    user = add_user('user', 'user@email.com', 'testpass123')
    thread = add_thread(title='A thread in the General Forum', text='This is a new thread', forum=forum,
                        user=user)

    client = get_user_client(user)

    resp = client.put(
        f"/api/threads/{thread.id}/",
        json.dumps({"title": "This is an updated title", "text": "This is an updated text", "forum": forum.id,
                    "user": user.id}),
        content_type="application/json"
    )
    assert resp.status_code == 200
    assert resp.data["title"] == "This is an updated title"
    assert resp.data["text"] == "This is an updated text"

    resp_two = client.get(f"/api/threads/{thread.id}/")
    assert resp_two.status_code == 200
    assert resp.data["title"] == "This is an updated title"
    assert resp.data["text"] == "This is an updated text"


@pytest.mark.django_db
def test_update_thread_wrong_user(add_forum, add_user, add_thread, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")

    user = add_user('user', 'user@email.com', 'testpass123')
    thread = add_thread(title='A thread in the General Forum', text='This is a new thread', forum=forum,
                        user=user)

    user_two = add_user('user2', 'user2@email.com', 'testpass123')

    client = get_user_client(user_two)

    resp = client.put(
        f"/api/threads/{thread.id}/",
        json.dumps({"title": "This is an updated title", "text": "This is an updated text", "forum": forum.id,
                    "user": user_two.id}),
        content_type="application/json"
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_update_thread_incorrect_id(add_user, get_user_client):
    user = add_user('user', 'user@email.com', 'testpass123')
    client = get_user_client(user)
    resp = client.put(f"/api/threads/99/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_update_thread_invalid_json(add_forum, add_user, add_thread, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    thread = add_thread(title='A thread in the General Forum', text='This is a new thread', forum=forum,
                        user=user)

    client = get_user_client(user)

    resp = client.put(f"/api/threads/{thread.id}/", {}, content_type="application/json")
    assert resp.status_code == 400
