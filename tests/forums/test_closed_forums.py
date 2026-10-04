"""
Closed forums: a forum's `posting` setting says who may add to it. Open (the default):
every member. Moderators start threads: members may only reply. Moderators only: members
may read. A moderator is anyone with forums.change_thread, as for announcements.

This file covers the setting and its rule; the views that enforce it have their own tests.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from pytest_django.asserts import assertContains

from forums.models import Forum, Posting

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
