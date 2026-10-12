"""Blocking a member: the buttons on the conversation page, and what a block stops."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from conversations.models import Block

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
