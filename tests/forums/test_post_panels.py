"""
The thread page: each post in a panel headed by its author, time and number. The opening
post is #1, replies are numbered on across pages, and the page ends with the actions and
the way back to the forum.
"""

import re

import pytest
from django.urls import reverse



@pytest.fixture
def client(client, reader):
    client.force_login(reader)
    return client


@pytest.fixture
def forum(add_forum):
    return add_forum('The house', 'Repairs')


@pytest.fixture
def thread(forum, reader, add_thread):
    return add_thread('Greenhouse', 'Text', forum, reader)


@pytest.fixture
def five_replies(thread, reader, add_post, site_settings):
    """Five replies on pages of two."""
    site_settings(posts_per_page=2)
    return [add_post(f'Reply {n}', thread, reader) for n in range(5)]


def page(client, thread, number=None):
    url = reverse('thread_detail', args=[thread.pk])
    resp = client.get(f'{url}?page={number}' if number else url)
    assert resp.status_code == 200
    return resp.content.decode()


def numbers(content):
    """The post numbers on the page, with the link of each."""
    return re.findall(r'<a class="post__number" href="([^"]+)">#(\d+)</a>', content)


@pytest.mark.django_db
def test_opening_post_is_number_one_and_marked(client, thread):
    content = page(client, thread)

    assert numbers(content) == [('#opening', '1')]
    assert 'class="post post--opening" id="opening"' in content
    assert 'Opening post' in content


@pytest.mark.django_db
def test_replies_are_numbered_from_two(client, thread, five_replies):
    content = page(client, thread)

    assert numbers(content) == [
        ('#opening', '1'),
        (f'?page=1#post-{five_replies[0].pk}', '2'),
        (f'?page=1#post-{five_replies[1].pk}', '3'),
    ]


@pytest.mark.django_db
def test_numbers_go_on_across_pages(client, thread, five_replies):
    content = page(client, thread, 3)

    # Two replies a page: the fifth reply is the sixth post
    assert numbers(content)[1:] == [(f'?page=3#post-{five_replies[4].pk}', '6')]


@pytest.mark.django_db
def test_each_reply_is_a_panel(client, thread, five_replies):
    content = page(client, thread)

    assert content.count('<article class="post" id="post-') == 2


@pytest.mark.django_db
def test_actions_and_page_links_at_both_ends(client, thread, five_replies):
    content = page(client, thread, 2)

    assert content.count(f'href="{reverse("post_add", args=[thread.pk])}"') == 2
    assert content.count(f'action="{reverse("thread_subscription", args=[thread.pk])}"') == 2
    assert content.count('aria-label="Pages of replies"') == 2


@pytest.mark.django_db
def test_without_replies_the_actions_show_once(client, thread):
    content = page(client, thread)

    assert content.count(f'href="{reverse("post_add", args=[thread.pk])}"') == 1
    assert 'Pages of replies' not in content


@pytest.mark.django_db
def test_page_ends_with_the_way_back_to_the_forum(client, forum, thread):
    content = page(client, thread)

    assert f'<a href="{reverse("forum_detail", args=[forum.pk])}">Back to The house</a>' in content
