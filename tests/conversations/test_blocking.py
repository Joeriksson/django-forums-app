"""Blocking a member: the buttons on the conversation page, and what a block stops."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects
from rest_framework.throttling import SimpleRateThrottle

from conversations.models import Block, Blocked, Message, send
from notifications.models import Notification

pytestmark = pytest.mark.django_db


def add_member(name):
    return get_user_model().objects.create_user(
        username=name, email=f'{name}@example.com', password='testpass123'
    )


@pytest.fixture
def anna():
    return add_member('anna')


@pytest.fixture
def bo():
    return add_member('bo')


@pytest.fixture
def as_anna(client, anna):
    client.force_login(anna)
    return client


def page(user):
    return reverse('conversation', kwargs={'pk': user.pk})


def block(user):
    return reverse('conversation_block', kwargs={'pk': user.pk})


def unblock(user):
    return reverse('conversation_unblock', kwargs={'pk': user.pk})


def test_the_addresses():
    assert reverse('conversation_block', kwargs={'pk': 7}) == '/messages/7/block/'
    assert reverse('conversation_unblock', kwargs={'pk': 7}) == '/messages/7/unblock/'


# The buttons


def test_the_page_offers_block_and_after_that_unblock(as_anna, bo):
    resp = as_anna.get(page(bo))
    assertContains(resp, f'action="{block(bo)}"')
    assertNotContains(resp, f'action="{unblock(bo)}"')

    as_anna.post(block(bo))

    resp = as_anna.get(page(bo))
    assertContains(resp, f'action="{unblock(bo)}"')
    assertNotContains(resp, f'action="{block(bo)}"')


def test_blocking_saves_the_block_and_returns_to_the_conversation(as_anna, anna, bo, security_log):
    resp = as_anna.post(block(bo))

    assertRedirects(resp, page(bo), fetch_redirect_response=False)
    saved = Block.objects.get()
    assert (saved.blocker, saved.blocked) == (anna, bo)
    assert security_log()[-1].startswith(f'block user={anna.pk} blocked={bo.pk} ip=')


def test_blocking_twice_is_one_block_and_one_log_line(as_anna, bo, security_log):
    as_anna.post(block(bo))
    as_anna.post(block(bo))

    assert Block.objects.count() == 1
    assert len([line for line in security_log() if line.startswith('block ')]) == 1


def test_unblocking_removes_the_block(as_anna, anna, bo, security_log):
    as_anna.post(block(bo))

    resp = as_anna.post(unblock(bo))

    assertRedirects(resp, page(bo), fetch_redirect_response=False)
    assert not Block.objects.exists()
    assert security_log()[-1].startswith(f'unblock user={anna.pk} blocked={bo.pk} ip=')


def test_unblocking_without_a_block_does_and_logs_nothing(as_anna, bo, security_log):
    assert as_anna.post(unblock(bo)).status_code == 302

    assert not [line for line in security_log() if line.startswith('unblock')]


def test_unblocking_leaves_the_other_members_block(as_anna, anna, bo):
    Block.objects.create(blocker=bo, blocked=anna)
    as_anna.post(block(bo))

    as_anna.post(unblock(bo))

    assert [(b.blocker, b.blocked) for b in Block.objects.all()] == [(bo, anna)]


def test_the_other_members_block_does_not_show_as_ones_own(as_anna, anna, bo):
    Block.objects.create(blocker=bo, blocked=anna)

    resp = as_anna.get(page(bo))

    assertContains(resp, f'action="{block(bo)}"')
    assertNotContains(resp, f'action="{unblock(bo)}"')


@pytest.mark.parametrize('address', [block, unblock])
def test_the_buttons_take_a_post_only(as_anna, bo, address):
    assert as_anna.get(address(bo)).status_code == 405
    assert not Block.objects.exists()


@pytest.mark.parametrize('address', [block, unblock])
def test_a_visitor_is_sent_to_the_login_page(client, bo, address):
    resp = client.post(address(bo))

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))
    assert not Block.objects.exists()


@pytest.mark.parametrize('who', ['oneself', 'nobody', 'deactivated'])
def test_no_blocking_oneself_a_missing_or_a_deactivated_member(as_anna, anna, bo, who):
    bo.is_active = False
    bo.save()
    pk = {'oneself': anna.pk, 'nobody': 999999, 'deactivated': bo.pk}[who]

    resp = as_anna.post(reverse('conversation_block', kwargs={'pk': pk}))

    assert resp.status_code == 404
    assert not Block.objects.exists()


# What a block stops


@pytest.fixture
def as_bo(bo):
    client = Client()
    client.force_login(bo)
    return client


def test_send_refuses_both_ways(anna, bo):
    Block.objects.create(blocker=anna, blocked=bo)

    for sender, receiver in ((bo, anna), (anna, bo)):
        with pytest.raises(Blocked):
            send(sender, receiver, 'Hello')
    assert not Message.objects.exists()


def test_a_block_of_someone_else_stops_nothing(anna, bo):
    cia = add_member('cia')
    Block.objects.create(blocker=anna, blocked=cia)

    send(bo, anna, 'Hello')
    send(cia, bo, 'Hello')

    assert Message.objects.count() == 2


def test_the_blocked_member_cannot_send(as_bo, anna, bo, security_log, django_capture_on_commit_callbacks):
    Block.objects.create(blocker=anna, blocked=bo)

    with django_capture_on_commit_callbacks(execute=True):
        resp = as_bo.post(page(anna), {'text': 'Let me in'})

    assert resp.status_code == 403
    assert not Message.objects.exists()
    assert not Notification.objects.exists()
    assert security_log()[-1].startswith(f'denied status=403 user={bo.pk} method=POST')


def test_the_blocker_cannot_send_either(as_anna, anna, bo):
    as_anna.post(block(bo))

    assert as_anna.post(page(bo), {'text': 'One last word'}).status_code == 403
    assert not Message.objects.exists()


def test_the_blocked_member_sees_a_note_instead_of_the_form(as_bo, anna, bo):
    send(anna, bo, 'Written earlier')
    Block.objects.create(blocker=anna, blocked=bo)

    resp = as_bo.get(page(anna))

    assertContains(resp, 'You can\'t send messages to this member.')
    assertNotContains(resp, '<textarea')
    # Not in so many words
    assertNotContains(resp, 'blocked')
    # What was written before stays readable, and their own Block button is there
    assertContains(resp, 'Written earlier')
    assertContains(resp, f'action="{block(anna)}"')


def test_the_blocker_sees_what_they_did_and_the_way_back(as_anna, anna, bo):
    send(bo, anna, 'Written earlier')
    as_anna.post(block(bo))

    resp = as_anna.get(page(bo))

    assertContains(resp, f'You have blocked Member {bo.pk}.')
    assertNotContains(resp, '<textarea')
    assertContains(resp, 'Written earlier')
    assertContains(resp, f'action="{unblock(bo)}"')


def test_unblocking_brings_the_form_back(as_anna, as_bo, anna, bo):
    as_anna.post(block(bo))
    as_anna.post(unblock(bo))

    assertContains(as_anna.get(page(bo)), '<textarea')
    assert as_bo.post(page(anna), {'text': 'Hello again'}).status_code == 302
    assert Message.objects.count() == 1


def test_with_two_blocks_one_unblock_is_not_enough(as_anna, as_bo, anna, bo):
    as_anna.post(block(bo))
    as_bo.post(block(anna))

    as_anna.post(unblock(bo))

    resp = as_anna.get(page(bo))
    assertContains(resp, 'You can\'t send messages to this member.')
    assert as_anna.post(page(bo), {'text': 'Hello'}).status_code == 403


def test_a_refused_message_does_not_count_against_the_limit(as_bo, anna, bo, monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, 'message_burst', '1/min')
    saved = Block.objects.create(blocker=anna, blocked=bo)
    assert as_bo.post(page(anna), {'text': 'Refused'}).status_code == 403
    saved.delete()

    assert as_bo.post(page(anna), {'text': 'Allowed'}).status_code == 302


def test_a_block_keeps_the_unread_notification(anna, bo, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        send(bo, anna, 'Hello')

    Block.objects.create(blocker=anna, blocked=bo)

    assert Notification.objects.get().read is False
