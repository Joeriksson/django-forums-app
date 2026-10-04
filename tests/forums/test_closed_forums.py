"""
Closed forums: a forum's `posting` setting says who may add to it. Open (the default):
every member. Moderators start threads: members may only reply. Moderators only: members
may read. A moderator is anyone with forums.change_thread, as for announcements.

The setting and its rule first, then the website. Closing stops new threads or replies:
members still edit and delete what they wrote there.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from forums.models import Forum, Post, Posting, Thread

pytestmark = pytest.mark.django_db


@pytest.fixture
def forum(add_forum):
    return add_forum('Notices', 'From the board')


@pytest.fixture
def member(add_user):
    return add_user('member', 'member@example.com', 'x')


@pytest.fixture
def moderator(add_user):
    moderator = add_user('moderator', 'moderator@example.com', 'x')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    return moderator


@pytest.fixture
def admin_client(add_super_user, get_user_client):
    return get_user_client(add_super_user('admin', 'admin@example.com', 'x'))


def test_a_new_forum_is_open(forum):
    assert forum.posting == Posting.OPEN
    assert not forum.is_closed


@pytest.mark.parametrize(
    'posting, may_start, may_reply',
    [
        (Posting.OPEN, True, True),
        (Posting.MODERATORS_START, False, True),
        (Posting.MODERATORS_ONLY, False, False),
    ],
)
def test_what_a_member_may_do(forum, member, posting, may_start, may_reply):
    forum.posting = posting

    assert forum.can_start_thread(member) is may_start
    assert forum.can_reply(member) is may_reply


@pytest.mark.parametrize('posting', Posting.values)
def test_a_moderator_may_always_post(forum, moderator, posting):
    forum.posting = posting

    assert forum.can_start_thread(moderator)
    assert forum.can_reply(moderator)


@pytest.mark.parametrize('posting', [Posting.MODERATORS_START, Posting.MODERATORS_ONLY])
def test_closed_forum_says_so(forum, posting):
    forum.posting = posting

    assert forum.is_closed


def test_edit_form_changes_the_setting(admin_client, forum):
    url = reverse('forum_update', kwargs={'pk': forum.pk})

    assertContains(admin_client.get(url), 'name="posting"')
    resp = admin_client.post(
        url,
        {'title': forum.title, 'description': forum.description, 'posting': Posting.MODERATORS_ONLY},
    )

    assert resp.status_code == 302
    forum.refresh_from_db()
    assert forum.posting == Posting.MODERATORS_ONLY


def test_new_forum_form_offers_the_setting(admin_client):
    resp = admin_client.post(
        reverse('forum_add'),
        {'title': 'Rules', 'description': 'Read first', 'posting': Posting.MODERATORS_START},
    )

    assert resp.status_code == 302
    assert Forum.objects.get(title='Rules').posting == Posting.MODERATORS_START


def test_form_refuses_an_unknown_value(admin_client, forum):
    resp = admin_client.post(
        reverse('forum_update', kwargs={'pk': forum.pk}),
        {'title': forum.title, 'description': forum.description, 'posting': 'nobody'},
    )

    assert resp.status_code == 200
    forum.refresh_from_db()
    assert forum.posting == Posting.OPEN


# The website: the forms refuse, and the pages don't offer what would be refused


@pytest.fixture
def thread(forum, moderator, add_thread):
    return add_thread('Spring meeting', 'On the 4th', forum, moderator)


@pytest.fixture
def member_client(client, member):
    client.force_login(member)
    return client


@pytest.fixture
def moderator_client(moderator, get_user_client):
    return get_user_client(moderator)


def close(forum, posting):
    forum.posting = posting
    forum.save()


CLOSED = [Posting.MODERATORS_START, Posting.MODERATORS_ONLY]


@pytest.mark.parametrize('posting', CLOSED)
def test_member_cannot_start_a_thread_in_a_closed_forum(member_client, forum, posting):
    close(forum, posting)
    url = reverse('thread_add', args=[forum.pk])

    assert member_client.get(url).status_code == 403
    assert member_client.post(url, {'title': 'Mine', 'text': 'Hello'}).status_code == 403
    assert not Thread.objects.filter(title='Mine').exists()


@pytest.mark.parametrize('posting', CLOSED)
def test_moderator_starts_a_thread_in_a_closed_forum(moderator_client, forum, posting):
    close(forum, posting)
    url = reverse('thread_add', args=[forum.pk])

    assert moderator_client.get(url).status_code == 200
    assert moderator_client.post(url, {'title': 'Notice', 'text': 'Hello'}).status_code == 302
    assert Thread.objects.filter(title='Notice', forum=forum).exists()


def test_member_replies_where_only_starting_threads_is_closed(member_client, forum, thread):
    close(forum, Posting.MODERATORS_START)
    url = reverse('post_add', args=[thread.pk])

    assert member_client.get(url).status_code == 200
    assert member_client.post(url, {'text': 'I will come'}).status_code == 302
    assert Post.objects.filter(thread=thread, text='I will come').exists()


def test_member_cannot_reply_in_a_moderators_only_forum(member_client, forum, thread):
    close(forum, Posting.MODERATORS_ONLY)
    url = reverse('post_add', args=[thread.pk])

    assert member_client.get(url).status_code == 403
    assert member_client.post(url, {'text': 'I will come'}).status_code == 403
    assert not Post.objects.filter(thread=thread).exists()


def test_moderator_replies_in_a_moderators_only_forum(moderator_client, forum, thread):
    close(forum, Posting.MODERATORS_ONLY)

    resp = moderator_client.post(reverse('post_add', args=[thread.pk]), {'text': 'Moved to the 5th'})

    assert resp.status_code == 302
    assert Post.objects.filter(thread=thread, text='Moved to the 5th').exists()


def test_refused_post_does_not_count_against_the_posting_limit(member_client, forum, rates):
    rates(posting_burst='1/min')
    close(forum, Posting.MODERATORS_START)
    member_client.post(reverse('thread_add', args=[forum.pk]), {'title': 'Mine', 'text': 'Hello'})
    close(forum, Posting.OPEN)

    resp = member_client.post(
        reverse('thread_add', args=[forum.pk]), {'title': 'Mine', 'text': 'Hello'}
    )

    assert resp.status_code == 302


def test_visitor_is_sent_to_the_login_page_not_refused(client, forum):
    close(forum, Posting.MODERATORS_ONLY)

    resp = client.get(reverse('thread_add', args=[forum.pk]))

    assert resp.status_code == 302
    assert reverse('account_login') in resp.url


def test_open_forum_page_offers_a_new_thread(member_client, forum):
    resp = member_client.get(reverse('forum_detail', args=[forum.pk]))

    assertContains(resp, reverse('thread_add', args=[forum.pk]))
    assertNotContains(resp, 'Closed')


@pytest.mark.parametrize(
    'posting, note',
    [
        (Posting.MODERATORS_START, 'Only moderators can start threads here. Everyone can reply.'),
        (Posting.MODERATORS_ONLY, 'Only moderators can post here.'),
    ],
)
def test_closed_forum_page_says_so_and_offers_no_new_thread(
    member_client, forum, thread, posting, note
):
    close(forum, posting)

    resp = member_client.get(reverse('forum_detail', args=[forum.pk]))

    assertContains(resp, 'Closed')
    assertContains(resp, note)
    assertNotContains(resp, reverse('thread_add', args=[forum.pk]))


def test_empty_closed_forum_offers_no_first_thread(member_client, forum):
    close(forum, Posting.MODERATORS_START)

    resp = member_client.get(reverse('forum_detail', args=[forum.pk]))

    assertContains(resp, 'No threads here yet.')
    assertNotContains(resp, 'Start the first one')


def test_closed_forum_page_offers_a_moderator_a_new_thread(moderator_client, forum):
    close(forum, Posting.MODERATORS_ONLY)

    resp = moderator_client.get(reverse('forum_detail', args=[forum.pk]))

    assertContains(resp, 'Closed')
    assertContains(resp, reverse('thread_add', args=[forum.pk]))


def test_thread_page_offers_no_reply_in_a_moderators_only_forum(member_client, forum, thread):
    close(forum, Posting.MODERATORS_ONLY)

    resp = member_client.get(reverse('thread_detail', args=[thread.pk]))

    assertNotContains(resp, reverse('post_add', args=[thread.pk]))
    assertContains(resp, 'This forum is closed for replies.')
    # Moderators' replies still send notifications
    assertContains(resp, reverse('thread_notification', args=[thread.pk]))


@pytest.mark.parametrize('posting', [Posting.OPEN, Posting.MODERATORS_START])
def test_thread_page_offers_a_reply_where_members_may(member_client, forum, thread, posting):
    close(forum, posting)

    resp = member_client.get(reverse('thread_detail', args=[thread.pk]))

    assertContains(resp, reverse('post_add', args=[thread.pk]))
    assertNotContains(resp, 'This forum is closed for replies.')


def test_thread_page_offers_a_moderator_a_reply(moderator_client, forum, thread):
    close(forum, Posting.MODERATORS_ONLY)

    resp = moderator_client.get(reverse('thread_detail', args=[thread.pk]))

    assertContains(resp, reverse('post_add', args=[thread.pk]))


def test_forum_list_marks_closed_forums(member_client, forum, add_forum):
    add_forum('The house', 'Repairs')
    close(forum, Posting.MODERATORS_START)

    resp = member_client.get(reverse('home'))

    assertContains(resp, '<span class="tag">Closed</span>', count=1)


@pytest.mark.parametrize('posting', CLOSED)
def test_member_still_edits_and_deletes_own_thread_in_a_closed_forum(
    member_client, member, forum, add_thread, posting
):
    own = add_thread('Mine', 'From before', forum, member)
    close(forum, posting)

    edit = member_client.post(
        reverse('thread_update', args=[own.pk]), {'title': 'Mine, edited', 'text': 'From before'}
    )
    assert edit.status_code == 302
    own.refresh_from_db()
    assert own.title == 'Mine, edited'

    delete = member_client.post(reverse('thread_delete', args=[forum.pk, own.pk]))
    assert delete.status_code == 302
    assert not Thread.objects.filter(pk=own.pk).exists()
