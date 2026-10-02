import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from tests.forums.clients import reader_client


@pytest.fixture
def content(add_user, add_forum, add_thread, add_post):
    author = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title='General Forum', description='A general forum')
    other_forum = add_forum(title='Other Forum', description='Another forum')
    thread = add_thread(
        title='First thread', text='Thread text', forum=forum, user=author
    )
    other_thread = add_thread(
        title='Second thread', text='Thread text', forum=forum, user=author
    )
    post = add_post(text='First post', thread=thread, user=author)
    add_post(text='Second post', thread=thread, user=author)
    return author, forum, other_forum, thread, other_thread, post


def list_query_count(url):
    client = reader_client()
    with CaptureQueriesContext(connection) as queries:
        resp = client.get(url)
    assert resp.status_code == 200
    return len(queries)


# Forums: a thread count, not the threads


@pytest.mark.django_db
def test_forum_list_has_thread_count_not_threads(content):
    _, forum, other_forum, *_ = content

    resp = reader_client().get('/api/forums/')

    assert resp.status_code == 200
    counts = {row['id']: row['thread_count'] for row in resp.data['results']}
    assert counts == {forum.id: 2, other_forum.id: 0}
    assert all('threads' not in row for row in resp.data['results'])


@pytest.mark.django_db
def test_forum_detail_has_thread_count_not_threads(content):
    _, forum, *_ = content

    resp = reader_client().get(f'/api/forums/{forum.id}/')

    assert resp.status_code == 200
    assert resp.data['thread_count'] == 2
    assert 'threads' not in resp.data


@pytest.mark.django_db
def test_created_forum_has_thread_count(add_super_user, get_user_client):
    admin = add_super_user('admin', 'admin@email.com', 'testpass123')

    resp = get_user_client(admin).post(
        '/api/forums/', {'title': 'New', 'description': 'New forum'}, format='json'
    )

    assert resp.status_code == 201
    assert resp.data['thread_count'] == 0


# Threads: a post count, not the posts


@pytest.mark.django_db
def test_thread_list_has_post_count_not_posts(content):
    *_, thread, other_thread, _ = content

    resp = reader_client().get('/api/threads/')

    assert resp.status_code == 200
    counts = {row['id']: row['post_count'] for row in resp.data['results']}
    assert counts == {thread.id: 2, other_thread.id: 0}
    assert all('posts' not in row for row in resp.data['results'])


@pytest.mark.django_db
def test_thread_detail_has_post_count_not_posts(content):
    *_, thread, _, _ = content

    resp = reader_client().get(f'/api/threads/{thread.id}/')

    assert resp.status_code == 200
    assert resp.data['post_count'] == 2
    assert 'posts' not in resp.data


@pytest.mark.django_db
def test_created_thread_has_post_count(content, get_user_client):
    author, forum, *_ = content

    resp = get_user_client(author).post(
        '/api/threads/',
        {'title': 'New', 'text': 'New thread', 'forum': forum.id},
        format='json',
    )

    assert resp.status_code == 201
    assert resp.data['post_count'] == 0


@pytest.mark.django_db
def test_updated_thread_keeps_post_count(content, get_user_client):
    author, *_, thread, _, _ = content

    resp = get_user_client(author).patch(
        f'/api/threads/{thread.id}/', {'title': 'Edited'}, format='json'
    )

    assert resp.status_code == 200
    assert resp.data['post_count'] == 2


# Filters


@pytest.mark.django_db
def test_threads_can_be_filtered_by_forum(content, add_thread):
    author, forum, other_forum, thread, other_thread, _ = content
    add_thread(title='Elsewhere', text='Text', forum=other_forum, user=author)

    resp = reader_client().get(f'/api/threads/?forum={forum.id}')

    assert resp.status_code == 200
    assert {row['id'] for row in resp.data['results']} == {thread.id, other_thread.id}


@pytest.mark.django_db
def test_posts_can_be_filtered_by_thread(content, add_post):
    author, *_, thread, other_thread, _ = content
    add_post(text='Elsewhere', thread=other_thread, user=author)

    resp = reader_client().get(f'/api/posts/?thread={thread.id}')

    assert resp.status_code == 200
    assert len(resp.data['results']) == 2
    assert all(row['thread'] == thread.id for row in resp.data['results'])


@pytest.mark.django_db
@pytest.mark.parametrize('endpoint', ['/api/threads/?forum=', '/api/posts/?thread='])
@pytest.mark.parametrize('value', ['abc', '-1', '\u00b2', '99999999999'])
def test_invalid_filter_id_is_rejected(content, endpoint, value):
    resp = reader_client().get(endpoint + value)

    assert resp.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/api/threads/?forum=99999', '/api/posts/?thread=99999'])
def test_unknown_filter_id_returns_empty_page(content, url):
    resp = reader_client().get(url)

    assert resp.status_code == 200
    assert resp.data['count'] == 0


# Query counts don't grow with the number of rows


@pytest.mark.django_db
def test_forum_list_query_count_does_not_grow(content, add_forum, add_thread, add_post):
    author, *_ = content
    before = list_query_count('/api/forums/')

    for i in range(5):
        forum = add_forum(title=f'Forum {i}', description='More')
        thread = add_thread(title=f'Thread {i}', text='Text', forum=forum, user=author)
        add_post(text='Post', thread=thread, user=author)

    assert list_query_count('/api/forums/') == before


@pytest.mark.django_db
def test_thread_list_query_count_does_not_grow(content, add_thread, add_post):
    author, forum, *_ = content
    before = list_query_count('/api/threads/')

    for i in range(5):
        thread = add_thread(title=f'Thread {i}', text='Text', forum=forum, user=author)
        add_post(text='Post', thread=thread, user=author)

    assert list_query_count('/api/threads/') == before
