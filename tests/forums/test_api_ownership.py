import json

import pytest

from forums.models import Post, Thread


@pytest.mark.django_db
def test_add_thread_ignores_user_in_payload(add_user, get_user_client, add_forum):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    other_user = add_user('other', 'other@email.com', 'testpass123')

    client = get_user_client(user)

    resp = client.post(
        "/api/threads/",
        json.dumps(
            {
                "title": "Impersonated thread",
                "text": "Posted as someone else",
                "forum": forum.id,
                "user": other_user.id,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert resp.data["user"] == user.id
    assert Thread.objects.get(id=resp.data["id"]).user == user


@pytest.mark.django_db
def test_add_post_ignores_user_in_payload(
    add_user, get_user_client, add_forum, add_thread
):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    other_user = add_user('other', 'other@email.com', 'testpass123')
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=other_user,
    )

    client = get_user_client(user)

    resp = client.post(
        "/api/posts/",
        json.dumps(
            {
                "text": "Posted as someone else",
                "thread": thread.id,
                "user": other_user.id,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert resp.data["user"] == user.id
    assert Post.objects.get(id=resp.data["id"]).user == user


@pytest.mark.django_db
def test_add_post_ignores_upvotes_in_payload(
    add_user, get_user_client, add_forum, add_thread
):
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
        json.dumps(
            {
                "text": "A post with inflated upvotes",
                "thread": thread.id,
                "user": user.id,
                "upvotes": 999,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert Post.objects.get(id=resp.data["id"]).upvotes == 0


@pytest.mark.django_db
def test_owner_cannot_reassign_thread(
    add_user, get_user_client, add_forum, add_thread
):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    other_user = add_user('other', 'other@email.com', 'testpass123')
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=user,
    )

    client = get_user_client(user)

    resp = client.patch(
        f"/api/threads/{thread.id}/",
        json.dumps({"user": other_user.id}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    thread.refresh_from_db()
    assert thread.user == user


@pytest.mark.django_db
def test_owner_cannot_reassign_post_or_set_upvotes(
    add_user, get_user_client, add_forum, add_thread, add_post
):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')
    other_user = add_user('other', 'other@email.com', 'testpass123')
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=user,
    )
    post = add_post(text='A reply', thread=thread, user=user)

    client = get_user_client(user)

    resp = client.patch(
        f"/api/posts/{post.id}/",
        json.dumps({"user": other_user.id, "upvotes": 999}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    post.refresh_from_db()
    assert post.user == user
    assert post.upvotes == 0


@pytest.mark.django_db
def test_add_thread_without_user_field(add_user, get_user_client, add_forum):
    forum = add_forum(title="General Forum", description="This is a general forum")
    user = add_user('user', 'user@email.com', 'testpass123')

    client = get_user_client(user)

    resp = client.post(
        "/api/threads/",
        json.dumps(
            {
                "title": "A thread",
                "text": "No user field sent",
                "forum": forum.id,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert Thread.objects.get(id=resp.data["id"]).user == user


@pytest.mark.django_db
def test_add_post_without_user_field(
    add_user, get_user_client, add_forum, add_thread
):
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
        json.dumps({"text": "No user field sent", "thread": thread.id}),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert Post.objects.get(id=resp.data["id"]).user == user
