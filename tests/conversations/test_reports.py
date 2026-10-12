"""Reporting a message to the moderators: the copy that is kept, and who may see it."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.utils import timezone

from conversations.models import Conversation, Message, Report, send

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


# The report


def test_a_report_copies_the_message(anna, bo):
    message = send(bo, anna, 'Something unkind')

    report = Report.of(message, anna, note='Third time this week')

    assert (report.reporter, report.sender, report.message) == (anna, bo, message)
    assert (report.text, report.sent) == ('Something unkind', message.added)
    assert report.note == 'Third time this week'
    assert (report.handled, report.handled_by) == (None, None)


def test_a_message_is_reported_once(anna, bo):
    message = send(bo, anna, 'Something unkind')
    Report.of(message, anna)

    with pytest.raises(IntegrityError), transaction.atomic():
        Report.of(message, anna)


def test_a_report_does_not_show_its_text_as_a_string(anna, bo):
    report = Report.of(send(bo, anna, 'A secret'), anna, note='Private note')

    assert 'A secret' not in str(report)
    assert 'Private note' not in str(report)


@pytest.mark.parametrize('deleted', ['message', 'conversation', 'sender', 'reporter'])
def test_a_report_is_kept_when_what_it_is_about_is_deleted(anna, bo, deleted):
    message = send(bo, anna, 'Something unkind')
    Report.of(message, anna, note='A note')

    {
        'message': message,
        'conversation': message.conversation,
        'sender': bo,
        'reporter': anna,
    }[deleted].delete()

    report = Report.objects.get()
    assert (report.text, report.note) == ('Something unkind', 'A note')
    assert report.sent == message.added
    assert report.message is None
    assert report.sender == (None if deleted == 'sender' else bo)
    assert report.reporter == (None if deleted == 'reporter' else anna)
    if deleted != 'message':
        assert not Message.objects.exists()
        assert not Conversation.objects.exists()


def test_reports_not_yet_handled_come_first_then_the_newest(anna, bo):
    first, second, third = (Report.of(send(bo, anna, f'Message {n}'), anna) for n in range(3))
    second.handled = timezone.now()
    second.save()

    assert list(Report.objects.all()) == [third, first, second]


# Who may see them


def test_the_moderators_group_may_see_and_handle_reports():
    group = Group.objects.get(name='Moderators')

    codenames = set(group.permissions.values_list('codename', flat=True))
    assert codenames == {
        'change_thread',
        'delete_thread',
        'delete_post',
        'view_report',
        'change_report',
    }


def test_a_moderator_has_the_permissions_and_a_member_does_not(anna, bo):
    anna.groups.add(Group.objects.get(name='Moderators'))

    assert anna.has_perms(['conversations.view_report', 'conversations.change_report'])
    assert not anna.has_perm('conversations.delete_report')
    assert not bo.has_perm('conversations.view_report')


def test_nothing_of_the_messages_is_in_the_admin():
    registered = {model._meta.label for model in admin.site._registry}

    assert not {label for label in registered if label.startswith('conversations.')}
