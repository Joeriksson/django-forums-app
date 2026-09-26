import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from forums.models import Post, Thread


@pytest.fixture
def content(add_user, add_forum, add_thread, add_post):
    author = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title="General Forum", description="This is a general forum")
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=author,
    )
    post = add_post(text='A post by the author', thread=thread, user=author)
    return thread, post


@pytest.fixture
def moderator_client(add_user, get_user_client):
    moderator = add_user('moderator', 'moderator@email.com', 'testpass123')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    return get_user_client(moderator)


@pytest.fixture
def user_client(add_user, get_user_client):
    user = add_user('user', 'user@email.com', 'testpass123')
    return get_user_client(user)


# Moderators


@pytest.mark.django_db
def test_moderator_can_update_other_users_thread(moderator_client, content):
    thread, _ = content

    resp = moderator_client.patch(
        f'/api/threads/{thread.id}/', {'title': 'Edited by moderator'}, format='json'
    )

    assert resp.status_code == 200
    thread.refresh_from_db()
    assert thread.title == 'Edited by moderator'


@pytest.mark.django_db
def test_moderator_can_delete_other_users_thread(moderator_client, content):
    thread, _ = content

    resp = moderator_client.delete(f'/api/threads/{thread.id}/')

    assert resp.status_code == 204
    assert not Thread.objects.filter(id=thread.id).exists()


@pytest.mark.django_db
def test_moderator_can_delete_other_users_post(moderator_client, content):
    _, post = content

    resp = moderator_client.delete(f'/api/posts/{post.id}/')

    assert resp.status_code == 204
    assert not Post.objects.filter(id=post.id).exists()


@pytest.mark.django_db
def test_moderator_cannot_update_other_users_post(moderator_client, content):
    """Moderators have no change_post, like the website has no post edit."""
    _, post = content

    resp = moderator_client.patch(
        f'/api/posts/{post.id}/', {'text': 'Edited by moderator'}, format='json'
    )

    assert resp.status_code == 403
    post.refresh_from_db()
    assert post.text == 'A post by the author'


# Regular users and anonymous


@pytest.mark.django_db
def test_user_cannot_change_other_users_content(user_client, content):
    thread, post = content

    responses = (
        user_client.patch(f'/api/threads/{thread.id}/', {'title': 'x'}, format='json'),
        user_client.delete(f'/api/threads/{thread.id}/'),
        user_client.patch(f'/api/posts/{post.id}/', {'text': 'x'}, format='json'),
        user_client.delete(f'/api/posts/{post.id}/'),
    )

    assert [resp.status_code for resp in responses] == [403] * 4
    assert Thread.objects.filter(id=thread.id, title=thread.title).exists()
    assert Post.objects.filter(id=post.id, text=post.text).exists()


@pytest.mark.django_db
def test_anonymous_cannot_change_content(content):
    thread, post = content
    client = APIClient()

    responses = (
        client.patch(f'/api/threads/{thread.id}/', {'title': 'x'}, format='json'),
        client.delete(f'/api/threads/{thread.id}/'),
        client.patch(f'/api/posts/{post.id}/', {'text': 'x'}, format='json'),
        client.delete(f'/api/posts/{post.id}/'),
    )

    assert all(resp.status_code in (401, 403) for resp in responses)
    assert Thread.objects.filter(id=thread.id, title=thread.title).exists()
    assert Post.objects.filter(id=post.id, text=post.text).exists()


# Owners


@pytest.mark.django_db
def test_author_can_update_and_delete_own_content(get_user_client, content):
    thread, post = content
    client = get_user_client(thread.user)

    assert client.patch(
        f'/api/posts/{post.id}/', {'text': 'Edited'}, format='json'
    ).status_code == 200
    assert client.patch(
        f'/api/threads/{thread.id}/', {'title': 'Edited'}, format='json'
    ).status_code == 200
    assert client.delete(f'/api/posts/{post.id}/').status_code == 204
    assert client.delete(f'/api/threads/{thread.id}/').status_code == 204
