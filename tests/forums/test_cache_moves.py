import pytest
from django.core.cache import cache
from django.urls import reverse


@pytest.fixture
def client(client, reader):
    """Reading needs a login: the pages are requested by a member."""
    client.force_login(reader)
    return client


@pytest.mark.parametrize('run', [1, 2])
def test_cache_starts_empty_in_every_test(run):
    # Each run leaves a key behind; the shared clear_cache fixture must remove it
    assert cache.get('leftover_from_earlier_test') is None
    cache.set('leftover_from_earlier_test', run)


@pytest.mark.django_db
def test_moved_thread_shows_on_its_new_forum_page(
    client, add_forum, add_thread, add_user
):
    user = add_user('mover', 'mover@example.com', 'pass1234')
    old_forum = add_forum('Old forum', 'Old')
    new_forum = add_forum('New forum', 'New')
    thread = add_thread('Moving thread', 'Text', old_forum, user)

    # Load both forum pages first: an earlier version cached their threads
    resp = client.get(reverse('forum_detail', args=(old_forum.id,)))
    assert thread in resp.context['threads']
    resp = client.get(reverse('forum_detail', args=(new_forum.id,)))
    assert thread not in resp.context['threads']

    thread.forum = new_forum
    thread.save()

    resp = client.get(reverse('forum_detail', args=(old_forum.id,)))
    assert thread not in resp.context['threads']
    resp = client.get(reverse('forum_detail', args=(new_forum.id,)))
    assert thread in resp.context['threads']


@pytest.mark.django_db
def test_moved_post_shows_on_its_new_thread_page(
    client, add_forum, add_thread, add_post, add_user
):
    user = add_user('mover', 'mover@example.com', 'pass1234')
    forum = add_forum('Forum', 'Forum')
    old_thread = add_thread('Old thread', 'Text', forum, user)
    new_thread = add_thread('New thread', 'Text', forum, user)
    post = add_post('Moving post', old_thread, user)

    # Load both thread pages first: an earlier version cached their posts
    resp = client.get(reverse('thread_detail', args=(old_thread.id,)))
    assert post in resp.context['posts']
    resp = client.get(reverse('thread_detail', args=(new_thread.id,)))
    assert post not in resp.context['posts']

    post.thread = new_thread
    post.save()

    resp = client.get(reverse('thread_detail', args=(old_thread.id,)))
    assert post not in resp.context['posts']
    resp = client.get(reverse('thread_detail', args=(new_thread.id,)))
    assert post in resp.context['posts']
