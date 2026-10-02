import pytest
from rest_framework.test import APIClient

from tests.forums.clients import reader_client

from forums.models import Forum


@pytest.mark.django_db
def test_user_without_forum_permission_cannot_create_forum(add_user, get_user_client):
    user = add_user('user', 'user@email.com', 'testpass123')

    resp = get_user_client(user).post(
        '/api/forums/', {'title': 'New', 'description': 'New forum'}, format='json'
    )

    assert resp.status_code == 403
    assert not Forum.objects.filter(title='New').exists()


@pytest.mark.django_db
def test_anonymous_user_cannot_create_forum():
    resp = APIClient().post(
        '/api/forums/', {'title': 'New', 'description': 'New forum'}, format='json'
    )

    assert resp.status_code in (401, 403)
    assert not Forum.objects.filter(title='New').exists()


@pytest.mark.django_db
def test_posts_are_listed_oldest_first(add_user, add_forum, add_thread, add_post):
    user = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title='Forum', description='Forum')
    thread = add_thread(title='Thread', text='Text', forum=forum, user=user)
    posts = [add_post(text=f'Post {i}', thread=thread, user=user) for i in range(3)]

    resp = reader_client().get(f'/api/posts/?thread={thread.id}')

    assert resp.status_code == 200
    assert [row['id'] for row in resp.data['results']] == [p.id for p in posts]


@pytest.mark.django_db
def test_forums_are_listed_by_title(add_forum):
    # Created out of order, so insertion order doesn't pass by accident
    for title in ('Charlie', 'Alpha', 'Bravo'):
        add_forum(title=title, description='Forum')

    resp = reader_client().get('/api/forums/')

    assert resp.status_code == 200
    assert [row['title'] for row in resp.data['results']] == ['Alpha', 'Bravo', 'Charlie']


@pytest.mark.django_db
def test_threads_are_listed_newest_first(add_user, add_forum, add_thread):
    user = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title='Forum', description='Forum')
    threads = [
        add_thread(title=f'Thread {i}', text='Text', forum=forum, user=user)
        for i in range(3)
    ]

    resp = reader_client().get('/api/threads/')

    assert resp.status_code == 200
    assert [row['id'] for row in resp.data['results']] == [t.id for t in reversed(threads)]
