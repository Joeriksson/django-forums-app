"""The ways in to direct messages: the list, the members to write to, the menu, the thread page."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from conversations.models import Conversation, send
from forums.models import Forum, Post, Thread

pytestmark = pytest.mark.django_db


def add_member(name, first_name=''):
    user = get_user_model().objects.create_user(
        username=name, email=f'{name}@example.com', password='testpass123'
    )
    if first_name:
        user.profile.first_name = first_name
        user.profile.save()
    return user


@pytest.fixture
def anna():
    return add_member('anna', 'Anna')


@pytest.fixture
def bo():
    return add_member('bo', 'Bo')


@pytest.fixture
def as_anna(client, anna):
    client.force_login(anna)
    return client


@pytest.fixture
def write(django_capture_on_commit_callbacks):
    def _write(sender, receiver, text='Hello'):
        with django_capture_on_commit_callbacks(execute=True):
            return send(sender, receiver, text)

    return _write


def link(user):
    return f'href="{reverse("conversation", kwargs={"pk": user.pk})}"'


def test_the_addresses():
    assert reverse('conversations') == '/messages/'
    assert reverse('conversation_new') == '/messages/new/'


@pytest.mark.parametrize('name', ['conversations', 'conversation_new'])
def test_visitors_are_sent_to_the_login_page(client, name):
    resp = client.get(reverse(name))

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))


# The list


def test_the_list_is_empty_at_first(as_anna):
    resp = as_anna.get(reverse('conversations'))

    assertContains(resp, 'No messages yet.')
    assertContains(resp, f'href="{reverse("conversation_new")}"')


def test_the_list_has_the_members_conversations_newest_first(as_anna, anna, bo, write):
    cia = add_member('cia', 'Cia')
    dan = add_member('dan', 'Dan')
    write(anna, bo)
    write(cia, anna)
    write(bo, anna)
    write(cia, dan, 'Not for Anna')

    resp = as_anna.get(reverse('conversations'))

    assert [c.other for c in resp.context['conversations']] == [bo, cia]
    assertContains(resp, link(bo))
    assertContains(resp, link(cia))
    assertNotContains(resp, 'Dan')
    # The texts are on the conversation's page only
    assertNotContains(resp, 'Hello')


def test_the_list_counts_the_messages_not_yet_seen(as_anna, anna, bo, write):
    cia = add_member('cia', 'Cia')
    write(bo, anna)
    write(bo, anna)
    write(cia, anna)
    write(anna, cia)
    as_anna.get(reverse('conversation', kwargs={'pk': cia.pk}))

    resp = as_anna.get(reverse('conversations'))

    assert {c.other: c.unread for c in resp.context['conversations']} == {bo: 2, cia: 0}
    assertContains(resp, '<strong>2</strong> new messages')
    assertNotContains(resp, 'new message<')


def test_the_list_never_shows_a_username_or_address(as_anna, anna, write):
    dan = add_member('dan.dahl')
    write(dan, anna)

    resp = as_anna.get(reverse('conversations'))

    assertContains(resp, f'Member {dan.pk}')
    assertNotContains(resp, 'dan.dahl')


def test_the_list_is_paged(as_anna, anna, write, site_settings):
    site_settings(threads_per_page=2)
    for n in range(3):
        write(add_member(f'member{n}'), anna)

    resp = as_anna.get(reverse('conversations'))

    assert len(resp.context['conversations']) == 2
    assertContains(resp, 'Page 1 of 2')


def test_the_list_costs_a_fixed_number_of_queries(as_anna, anna, write, django_assert_num_queries):
    for n in range(4):
        write(add_member(f'member{n}'), anna)
    as_anna.get(reverse('conversations'))

    # Eight for a logged-in page, then: the count, the page of conversations with both
    # members, the unread numbers
    with django_assert_num_queries(8 + 3):
        as_anna.get(reverse('conversations'))


# The menu


def nav(resp):
    return re.search(r'<nav class="site-nav"[^>]*>(.*?)</nav>', resp.content.decode(), re.DOTALL).group(1)


def test_the_menu_has_messages_for_members_only(client, anna):
    assert 'Messages' not in nav(client.get(reverse('home')))

    client.force_login(anna)

    # An envelope, named for screen readers and on hover
    assert re.search(
        rf'<a class="envelope" href="{reverse("conversations")}" title="Messages"[^>]*>\s*'
        r'<span class="visually-hidden">Messages</span>',
        nav(client.get(reverse('home'))),
    )


def test_the_envelope_stands_with_the_icons(as_anna):
    """Next to the bell, after the user menu: not among the text links."""
    menu = nav(as_anna.get(reverse('home')))

    assert menu.index('class="menu"') < menu.index('class="envelope"') < menu.index('class="bell"')


def test_the_menu_marks_messages_on_its_pages(as_anna, bo):
    pages = [
        reverse('conversations'),
        reverse('conversation_new'),
        reverse('conversation', kwargs={'pk': bo.pk}),
    ]
    for url in pages:
        menu = nav(as_anna.get(url))

        marked = re.findall(r'<a [^>]*aria-current="page"[^>]*>', menu)
        assert len(marked) == 1
        assert 'class="envelope"' in marked[0]


def test_the_conversation_page_leads_back_to_the_list(as_anna, bo):
    resp = as_anna.get(reverse('conversation', kwargs={'pk': bo.pk}))

    assertContains(resp, f'href="{reverse("conversations")}">Back to messages')


# The thread page


@pytest.fixture
def thread(bo):
    forum = Forum.objects.create(title='General', description='Everything')
    return Thread.objects.create(title='A thread', text='Text', forum=forum, user=bo)


def test_the_thread_page_has_a_message_link_by_other_authors(as_anna, anna, bo, thread):
    cia = add_member('cia', 'Cia')
    Post.objects.create(text='A reply', thread=thread, user=cia)
    Post.objects.create(text='My reply', thread=thread, user=anna)

    resp = as_anna.get(reverse('thread_detail', kwargs={'pk': thread.pk}))

    assertContains(resp, f'class="post__message" {link(bo)}', count=1)
    assertContains(resp, f'class="post__message" {link(cia)}', count=1)
    assertNotContains(resp, f'class="post__message" {link(anna)}')


def test_no_message_link_by_ones_own_thread_or_a_deactivated_author(client, bo, thread):
    cia = add_member('cia', 'Cia')
    Post.objects.create(text='A reply', thread=thread, user=cia)
    cia.is_active = False
    cia.save()
    client.force_login(bo)

    resp = client.get(reverse('thread_detail', kwargs={'pk': thread.pk}))

    assertNotContains(resp, 'post__message')


def test_looking_at_the_lists_starts_no_conversation(as_anna, bo):
    as_anna.get(reverse('conversations'))
    as_anna.get(reverse('conversation_new'))

    assert not Conversation.objects.exists()
