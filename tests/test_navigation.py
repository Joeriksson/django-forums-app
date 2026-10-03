"""The header's menu: Forums, Latest and Search for members, the current section marked."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from forums.models import Forum, Thread

User = get_user_model()


@pytest.fixture
def member(db):
    return User.objects.create_user(username='member', email='member@example.com', password='x')


@pytest.fixture
def thread(member):
    forum = Forum.objects.create(title='Trips', description='Where to')
    return Thread.objects.create(title='Lake', text='Text', forum=forum, user=member)


def nav(resp):
    return re.search(r'<nav class="site-nav"[^>]*>(.*?)</nav>', resp.content.decode(), re.DOTALL).group(1)


def current(resp):
    """The text of the menu links marked as the current page."""
    return re.findall(r'<a [^>]*aria-current="page"[^>]*>([^<]+)</a>', nav(resp))


@pytest.mark.django_db
def test_members_have_forums_and_latest(client, member):
    client.force_login(member)

    menu = nav(client.get(reverse('home')))

    assert re.search(rf'href="{reverse("home")}"[^>]*>Forums</a>', menu)
    assert re.search(rf'href="{reverse("latest")}"[^>]*>Latest</a>', menu)
    assert re.search(rf'href="{reverse("search_results")}"[^>]*>Search</a>', menu)


@pytest.mark.django_db
@pytest.mark.parametrize(
    'url, section',
    [
        (lambda thread: reverse('home'), 'Forums'),
        (lambda thread: reverse('forum_detail', args=[thread.forum_id]), 'Forums'),
        (lambda thread: reverse('thread_detail', args=[thread.pk]), 'Forums'),
        (lambda thread: reverse('latest'), 'Latest'),
        (lambda thread: reverse('search_results'), 'Search'),
    ],
)
def test_menu_marks_the_current_section(client, member, thread, url, section):
    client.force_login(member)

    assert current(client.get(url(thread))) == [section]


@pytest.mark.django_db
def test_account_pages_mark_no_section(client, member):
    client.force_login(member)

    assert current(client.get(reverse('account_email'))) == []


@pytest.mark.django_db
def test_visitors_have_no_forum_links(client):
    menu = nav(client.get(reverse('home')))

    assert 'Latest' not in menu
    assert '>Forums<' not in menu
