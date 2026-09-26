import pytest
from django.contrib.auth.models import Group

from forums.models import Post, Thread


@pytest.fixture
def content(add_user, add_forum, add_thread, add_post):
    author = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title="General Forum", description="This is a general forum")
    other_forum = add_forum(title="Other Forum", description="Another forum")
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=author,
    )
    other_thread = add_thread(
        title='Another thread',
        text='This is another thread',
        forum=forum,
        user=author,
    )
    post = add_post(text='A post by the author', thread=thread, user=author)
    return {
        'thread': thread,
        'post': post,
        'other_forum': other_forum,
        'other_thread': other_thread,
    }


# Moves are rejected


@pytest.mark.django_db
def test_owner_cannot_move_thread_to_another_forum(get_user_client, content):
    thread = content['thread']
    client = get_user_client(thread.user)

    resp = client.patch(
        f'/api/threads/{thread.id}/',
        {'forum': content['other_forum'].id},
        format='json',
    )

    assert resp.status_code == 400
    assert 'forum' in resp.data
    thread.refresh_from_db()
    assert thread.forum != content['other_forum']


@pytest.mark.django_db
def test_moderator_cannot_move_thread_to_another_forum(
    add_user, get_user_client, content
):
    thread = content['thread']
    moderator = add_user('moderator', 'moderator@email.com', 'testpass123')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    client = get_user_client(moderator)

    resp = client.patch(
        f'/api/threads/{thread.id}/',
        {'forum': content['other_forum'].id},
        format='json',
    )

    assert resp.status_code == 400
    thread.refresh_from_db()
    assert thread.forum != content['other_forum']


@pytest.mark.django_db
def test_owner_cannot_move_post_to_another_thread(get_user_client, content):
    post = content['post']
    client = get_user_client(post.user)

    resp = client.patch(
        f'/api/posts/{post.id}/',
        {'thread': content['other_thread'].id},
        format='json',
    )

    assert resp.status_code == 400
    assert 'thread' in resp.data
    post.refresh_from_db()
    assert post.thread != content['other_thread']


# Updates that keep the same forum or thread still work


@pytest.mark.django_db
def test_put_thread_with_same_forum_succeeds(get_user_client, content):
    thread = content['thread']
    client = get_user_client(thread.user)

    resp = client.put(
        f'/api/threads/{thread.id}/',
        {'title': 'Edited title', 'text': 'Edited text', 'forum': thread.forum_id},
        format='json',
    )

    assert resp.status_code == 200
    thread.refresh_from_db()
    assert thread.title == 'Edited title'


@pytest.mark.django_db
def test_put_post_with_same_thread_succeeds(get_user_client, content):
    post = content['post']
    client = get_user_client(post.user)

    resp = client.put(
        f'/api/posts/{post.id}/',
        {'text': 'Edited text', 'thread': post.thread_id},
        format='json',
    )

    assert resp.status_code == 200
    post.refresh_from_db()
    assert post.text == 'Edited text'


# Creating still sets the forum or thread


@pytest.mark.django_db
def test_create_sets_forum_and_thread(get_user_client, content):
    client = get_user_client(content['thread'].user)

    thread_resp = client.post(
        '/api/threads/',
        {'title': 'New', 'text': 'New thread', 'forum': content['other_forum'].id},
        format='json',
    )
    post_resp = client.post(
        '/api/posts/',
        {'text': 'New post', 'thread': content['other_thread'].id},
        format='json',
    )

    assert thread_resp.status_code == 201
    assert Thread.objects.get(id=thread_resp.data['id']).forum == content['other_forum']
    assert post_resp.status_code == 201
    assert Post.objects.get(id=post_resp.data['id']).thread == content['other_thread']
