"""Direct messages: one conversation per pair of members, its messages, and blocks."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from conversations.models import Block, Conversation, Message, send

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


def test_a_pair_has_one_conversation_whoever_starts(anna, bo):
    conversation = Conversation.between(anna, bo)

    assert Conversation.between(bo, anna) == conversation
    assert Conversation.objects.count() == 1
    assert {conversation.user_low, conversation.user_high} == {anna, bo}
    assert conversation.user_low_id < conversation.user_high_id


def test_no_conversation_with_oneself(anna):
    with pytest.raises(ValueError):
        Conversation.between(anna, anna)

    assert not Conversation.objects.exists()


def test_the_database_refuses_a_pair_in_the_wrong_order(anna, bo):
    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create(user_low=bo, user_high=anna)


def test_the_database_refuses_a_second_conversation_for_a_pair(anna, bo):
    Conversation.between(anna, bo)

    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create(user_low=anna, user_high=bo)


def test_a_third_member_gets_another_conversation(anna, bo):
    cia = add_member('cia')

    assert Conversation.between(anna, bo) != Conversation.between(anna, cia)


def test_send_adds_the_message_to_the_pairs_conversation(anna, bo):
    first = send(anna, bo, 'Hello')
    second = send(bo, anna, 'Hello yourself')

    conversation = Conversation.objects.get()
    assert list(conversation.messages.all()) == [first, second]
    assert (first.sender, first.text) == (anna, 'Hello')
    assert second.sender == bo
    assert conversation.updated == second.added


def test_conversations_are_listed_by_their_latest_message(anna, bo):
    cia = add_member('cia')
    send(anna, bo, 'First')
    send(anna, cia, 'Second')
    send(bo, anna, 'Third')

    assert list(Conversation.objects.all()) == [
        Conversation.between(anna, bo),
        Conversation.between(anna, cia),
    ]


def test_deleting_an_account_deletes_its_conversations(anna, bo):
    cia = add_member('cia')
    send(anna, bo, 'Hello')
    kept = send(bo, cia, 'Hello')

    anna.delete()

    assert list(Conversation.objects.all()) == [kept.conversation]
    assert list(Message.objects.all()) == [kept]


def test_a_message_does_not_show_its_text_as_a_string(anna, bo):
    message = send(anna, bo, 'A secret')

    assert 'A secret' not in str(message)


def test_between_tells_who_blocked_whom(anna, bo):
    assert Block.between(anna, bo) == set()

    Block.objects.create(blocker=anna, blocked=bo)
    assert Block.between(anna, bo) == Block.between(bo, anna) == {anna.pk}

    Block.objects.create(blocker=bo, blocked=anna)
    assert Block.between(anna, bo) == {anna.pk, bo.pk}


def test_the_database_refuses_a_second_block_and_blocking_oneself(anna, bo):
    Block.objects.create(blocker=anna, blocked=bo)

    with pytest.raises(IntegrityError), transaction.atomic():
        Block.objects.create(blocker=anna, blocked=bo)
    with pytest.raises(IntegrityError), transaction.atomic():
        Block.objects.create(blocker=anna, blocked=anna)
