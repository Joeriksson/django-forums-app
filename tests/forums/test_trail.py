"""
Where am I: every forum page below the forum list shows the way up (Forums › forum ›
thread), and the forum and thread pages say which kind of page they are.
"""

import re

import pytest
from django.urls import reverse

TRAIL = re.compile(r'<nav class="trail"[^>]*>(.*?)</nav>', re.DOTALL)
HREF = re.compile(r'href="([^"]+)"')


def trail_links(resp):
    found = TRAIL.findall(resp.content.decode())
    assert len(found) == 1, 'expected one trail on the page'
    return HREF.findall(found[0])


@pytest.fixture
def forum(add_forum):
    return add_forum('The house', 'Repairs')


@pytest.fixture
def thread(forum, reader, add_thread):
    return add_thread('Greenhouse', 'Text', forum, reader)


@pytest.fixture
def post(thread, reader, add_post):
    return add_post('A reply', thread, reader)


@pytest.fixture
def staff_client(admin_client, admin_user, add_totp):
    # Staff need an authenticator app to use the site
    add_totp(admin_user)
    return admin_client


@pytest.fixture
def member_client(client, reader):
    client.force_login(reader)
    return client


def forums():
    return reverse('home')


def forum_page(forum):
    return reverse('forum_detail', args=[forum.id])


def thread_page(thread):
    return reverse('thread_detail', args=[thread.id])


def test_forum_page_trail_and_label(member_client, forum):
    resp = member_client.get(forum_page(forum))

    assert trail_links(resp) == [forums()]
    assert '<p class="kicker">Forum</p>' in resp.content.decode()


def test_thread_page_trail_and_label(member_client, forum, thread):
    resp = member_client.get(thread_page(thread))

    assert trail_links(resp) == [forums(), forum_page(forum)]
    assert '<p class="kicker">Thread</p>' in resp.content.decode()


def test_new_thread_form_trail(member_client, forum):
    resp = member_client.get(reverse('thread_add', args=[forum.id]))

    assert trail_links(resp) == [forums(), forum_page(forum)]


def test_reply_form_trail(member_client, forum, thread):
    resp = member_client.get(reverse('post_add', args=[thread.id]))

    assert trail_links(resp) == [forums(), forum_page(forum), thread_page(thread)]


def test_thread_edit_trail(member_client, forum, thread):
    resp = member_client.get(reverse('thread_update', args=[thread.id]))

    assert trail_links(resp) == [forums(), forum_page(forum), thread_page(thread)]


def test_thread_delete_trail(member_client, forum, thread):
    resp = member_client.get(reverse('thread_delete', args=[forum.id, thread.id]))

    assert trail_links(resp) == [forums(), forum_page(forum), thread_page(thread)]


def test_reply_delete_trail(member_client, forum, thread, post):
    resp = member_client.get(reverse('post_delete', args=[thread.id, post.id]))

    assert trail_links(resp) == [forums(), forum_page(forum), thread_page(thread)]


def test_forum_edit_trail(staff_client, forum):
    resp = staff_client.get(reverse('forum_update', args=[forum.id]))

    assert trail_links(resp) == [forums(), forum_page(forum)]


def test_new_forum_trail(staff_client):
    resp = staff_client.get(reverse('forum_add'))

    assert trail_links(resp) == [forums()]
