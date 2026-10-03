"""
The forum list is a directory: each forum with its threads, replies and latest activity.
Thread rows (forum page, home page) show their replies and who replied last.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from forums.models import Post, Thread
from forums.views import ForumDetail


@pytest.fixture
def client(client, reader):
    client.force_login(reader)
    return client


@pytest.fixture
def anna(add_user):
    return add_user('anna', 'anna@example.com', 'x')


@pytest.fixture
def bo(add_user):
    return add_user('bo', 'bo@example.com', 'x')


@pytest.fixture
def forum(add_forum):
    return add_forum('The house', 'Repairs')


def started(thread, hours_ago):
    Thread.objects.filter(pk=thread.pk).update(added=timezone.now() - timedelta(hours=hours_ago))


def replied(thread, user, hours_ago):
    post = Post.objects.create(text='A reply', thread=thread, user=user)
    Post.objects.filter(pk=post.pk).update(added=timezone.now() - timedelta(hours=hours_ago))
    return post


def block(resp, css_class):
    """The text of the first element with this class."""
    content = resp.content.decode()
    match = re.search(rf'<(\w+) class="{css_class}"[^>]*>(.*?)</\1>', content, re.DOTALL)
    assert match, f'no element with class {css_class}'
    return match.group(2)


def last_page(thread):
    return reverse('thread_detail', args=[thread.pk]) + '?page=last'


# The forum list


@pytest.mark.django_db
def test_forum_list_counts_threads_and_replies(client, forum, anna, bo, add_thread):
    first = add_thread('Roof', 'Text', forum, anna)
    add_thread('Keys', 'Text', forum, anna)
    replied(first, bo, 2)
    replied(first, anna, 1)

    resp = client.get(reverse('forum_list'))

    counts = block(resp, 'forum-row__counts')
    assert '<strong>2</strong> threads' in counts
    assert '<strong>2</strong> replies' in counts


@pytest.mark.django_db
def test_forum_list_counts_in_the_singular(client, forum, anna, bo, add_thread):
    replied(add_thread('Roof', 'Text', forum, anna), bo, 1)

    counts = block(client.get(reverse('forum_list')), 'forum-row__counts')

    assert '<strong>1</strong> thread<' in counts
    assert '<strong>1</strong> reply<' in counts


@pytest.mark.django_db
def test_forum_list_latest_is_the_newest_reply(client, forum, anna, bo, add_thread):
    roof = add_thread('Roof', 'Text', forum, anna)
    keys = add_thread('Keys', 'Text', forum, anna)
    started(roof, 10)
    started(keys, 5)
    # The older thread has the newest activity
    replied(roof, bo, 1)

    latest = block(client.get(reverse('forum_list')), 'forum-row__latest')

    assert 'Roof' in latest
    assert 'Keys' not in latest
    assert f'Member {bo.pk}' in latest
    assert f'href="{last_page(roof)}"' in latest


@pytest.mark.django_db
def test_forum_list_latest_is_a_new_thread_without_replies(client, forum, anna, bo, add_thread):
    roof = add_thread('Roof', 'Text', forum, anna)
    keys = add_thread('Keys', 'Text', forum, bo)
    started(roof, 10)
    replied(roof, anna, 5)
    started(keys, 1)

    latest = block(client.get(reverse('forum_list')), 'forum-row__latest')

    assert 'Keys' in latest
    assert f'Member {bo.pk}' in latest


@pytest.mark.django_db
def test_forum_list_forum_without_threads(client, forum):
    resp = client.get(reverse('forum_list'))

    assert 'No threads yet' in block(resp, 'forum-row__latest')


@pytest.mark.django_db
def test_forum_list_uses_three_queries_however_many_forums(
    client, anna, bo, add_forum, add_thread, django_assert_num_queries
):
    for number in range(4):
        thread = add_thread('T', 'Text', add_forum(f'Forum {number}', 'D'), anna)
        replied(thread, bo, 1)

    # The forums with their counts, their latest threads, and the members who replied
    # last, after six for the logged-in reader
    with django_assert_num_queries(6 + 3):
        client.get(reverse('forum_list'))


# Thread rows


@pytest.mark.django_db
def test_thread_row_shows_replies_and_who_replied_last(client, forum, anna, bo, add_thread):
    thread = add_thread('Roof', 'Text', forum, anna)
    replied(thread, anna, 2)
    replied(thread, bo, 1)

    resp = client.get(reverse('forum_detail', args=[forum.pk]))

    assert '<strong>2</strong> replies' in block(resp, 'thread-row__count')
    latest = block(resp, 'thread-row__latest')
    assert f'Member {bo.pk}' in latest
    assert f'Member {anna.pk}' not in latest
    assert f'href="{last_page(thread)}"' in latest


@pytest.mark.django_db
def test_thread_row_without_replies(client, forum, anna, add_thread):
    add_thread('Roof', 'Text', forum, anna)

    resp = client.get(reverse('forum_detail', args=[forum.pk]))

    assert '<strong>0</strong> replies' in block(resp, 'thread-row__count')
    assert 'No replies yet' in block(resp, 'thread-row__latest')


@pytest.mark.django_db
def test_home_rows_show_who_replied_last(client, forum, anna, bo, add_thread):
    replied(add_thread('Roof', 'Text', forum, anna), bo, 1)

    resp = client.get(reverse('home'))

    assert f'Member {bo.pk}' in block(resp, 'thread-row__latest')


@pytest.mark.django_db
def test_forum_page_has_page_links_above_and_below(client, forum, anna, add_thread, monkeypatch):
    monkeypatch.setattr(ForumDetail, 'paginate_by', 2)
    for number in range(3):
        add_thread(f'Thread {number}', 'Text', forum, anna)

    resp = client.get(reverse('forum_detail', args=[forum.pk]))

    assert resp.content.decode().count('aria-label="Pages of threads"') == 2


@pytest.mark.django_db
def test_forum_page_without_more_pages_has_no_page_links(client, forum, anna, add_thread):
    add_thread('Roof', 'Text', forum, anna)

    assertNotContains(client.get(reverse('forum_detail', args=[forum.pk])), 'Pages of threads')


@pytest.mark.django_db
def test_forum_page_query_count_does_not_grow_with_threads(
    client, forum, add_user, add_thread, django_assert_num_queries
):
    for number in range(3):
        user = add_user(f'user{number}', f'user{number}@example.com', 'x')
        replied(add_thread(f'Thread {number}', 'Text', forum, user), user, 1)

    # The forum, the number of threads, one page of threads with authors and counts, and
    # the members who replied last, after six for the logged-in reader
    with django_assert_num_queries(6 + 4):
        assertContains(client.get(reverse('forum_detail', args=[forum.pk])), 'Thread 2')
