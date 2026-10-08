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

    resp = client.get(reverse('home'))

    counts = block(resp, 'forum-row__counts')
    assert '<strong>2</strong> threads' in counts
    assert '<strong>2</strong> replies' in counts


@pytest.mark.django_db
def test_forum_list_counts_in_the_singular(client, forum, anna, bo, add_thread):
    replied(add_thread('Roof', 'Text', forum, anna), bo, 1)

    counts = block(client.get(reverse('home')), 'forum-row__counts')

    assert '<strong>1</strong> thread<' in counts
    assert '<strong>1</strong> reply<' in counts


def announce(thread):
    Thread.objects.filter(pk=thread.pk).update(announcement=True)


@pytest.mark.django_db
def test_forum_list_shows_the_two_most_active_threads(client, forum, anna, bo, add_thread):
    roof = add_thread('Roof', 'Text', forum, anna)
    keys = add_thread('Keys', 'Text', forum, anna)
    wood = add_thread('Wood', 'Text', forum, anna)
    started(roof, 10)
    started(keys, 5)
    started(wood, 3)
    # The oldest thread has the newest activity
    replied(roof, bo, 1)

    content = block(client.get(reverse('home')), 'forum-row__threads')

    assert content.index('Roof') < content.index('Wood')
    assert 'Keys' not in content
    assertContains(client.get(reverse('home')), '<p class="forum-row__label">Latest</p>')


@pytest.mark.django_db
def test_forum_list_line_names_the_last_replier_or_the_starter(client, forum, anna, bo, add_thread):
    roof = add_thread('Roof', 'Text', forum, anna)
    keys = add_thread('Keys', 'Text', forum, bo)
    started(roof, 10)
    replied(roof, bo, 1)
    started(keys, 5)

    content = block(client.get(reverse('home')), 'forum-row__threads')

    roof_line, keys_line = content.split('</li>')[:2]
    assert f'Member {bo.pk}' in roof_line
    assert f'href="{last_page(roof)}"' in roof_line
    # Keys has no replies: the member who started it
    assert f'Member {bo.pk}' in keys_line
    assert f'Member {anna.pk}' not in keys_line


@pytest.mark.django_db
def test_forum_list_puts_announcements_first(client, forum, anna, bo, add_thread):
    rules = add_thread('House rules', 'Text', forum, anna)
    announce(rules)
    started(rules, 100)
    for title in ('Roof', 'Keys'):
        replied(add_thread(title, 'Text', forum, anna), bo, 1)

    content = block(client.get(reverse('home')), 'forum-row__threads')

    first, second = content.split('</li>')[:2]
    assert 'House rules' in first
    assert 'Announcement' in first
    # Then the most active thread: both had a reply an hour ago, Keys is newer
    assert 'Keys' in second
    assert 'Announcement' not in second
    assert 'Roof' not in content


@pytest.mark.django_db
def test_forum_list_two_announcements_fill_both_lines(client, forum, anna, add_thread):
    for title in ('Rules', 'Keys policy', 'Parking'):
        announce(add_thread(title, 'Text', forum, anna))
    add_thread('Roof', 'Text', forum, anna)

    content = block(client.get(reverse('home')), 'forum-row__threads')

    assert content.count('<li>') == 2
    assert 'Roof' not in content


@pytest.mark.django_db
def test_forum_list_lines_stay_in_their_forum(client, forum, anna, add_forum, add_thread):
    add_thread('Roof', 'Text', forum, anna)
    trips = add_forum('Trips', 'Where to')
    add_thread('Lake', 'Text', trips, anna)

    resp = client.get(reverse('home'))
    rows = resp.content.decode().split('class="row forum-row"')[1:]

    # Forums in title order: The house, Trips
    assert 'Roof' in rows[0] and 'Lake' not in rows[0]
    assert 'Lake' in rows[1] and 'Roof' not in rows[1]


@pytest.mark.django_db
def test_forum_list_forum_without_threads(client, forum):
    resp = client.get(reverse('home'))

    assertContains(resp, 'No threads yet')
    assertNotContains(resp, 'forum-row__threads')


@pytest.mark.django_db
def test_forum_list_uses_five_queries_however_many_forums(
    client, anna, bo, add_forum, add_thread, django_assert_num_queries
):
    for number in range(4):
        thread = add_thread('T', 'Text', add_forum(f'Forum {number}', 'D'), anna)
        replied(thread, bo, 1)

    # The forums with their counts, their two threads each, and the members who replied
    # last, after eight for the logged-in reader; then the recent threads and their repliers
    with django_assert_num_queries(8 + 3 + 2):
        client.get(reverse('home'))


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
def test_latest_rows_show_who_replied_last(client, forum, anna, bo, add_thread):
    replied(add_thread('Roof', 'Text', forum, anna), bo, 1)

    resp = client.get(reverse('latest'))

    assert f'Member {bo.pk}' in block(resp, 'thread-row__latest')


@pytest.mark.django_db
def test_forum_page_has_page_links_above_and_below(client, forum, anna, add_thread, site_settings):
    site_settings(threads_per_page=2)
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

    # The forum, its announcements, the number of threads, one page of threads with
    # authors and counts, and the members who replied last, after eight for the reader
    with django_assert_num_queries(8 + 5):
        assertContains(client.get(reverse('forum_detail', args=[forum.pk])), 'Thread 2')


# Each list in one panel, with a header row naming the columns


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', ['home', 'latest'])
def test_lists_are_in_a_panel_with_column_names(client, forum, anna, add_thread, url_name):
    add_thread('Roof', 'Text', forum, anna)

    resp = client.get(reverse(url_name))

    assertContains(resp, '<div class="panel">')
    assertContains(resp, 'class="panel__head')


@pytest.mark.django_db
def test_forum_page_panel_names_its_columns(client, forum, anna, add_thread):
    add_thread('Roof', 'Text', forum, anna)

    head = block(client.get(reverse('forum_detail', args=[forum.pk])), 'panel__head thread-row')

    assert 'Threads' in head
    assert 'Replies' in head
    assert 'Last reply' in head
