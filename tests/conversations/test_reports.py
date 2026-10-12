"""Reporting a message to the moderators: the copy that is kept, and who may see it."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects
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


# Reporting on the site


@pytest.fixture
def as_anna(client, anna):
    client.force_login(anna)
    return client


@pytest.fixture
def as_bo(bo):
    client = Client()
    client.force_login(bo)
    return client


@pytest.fixture
def unkind(anna, bo):
    """A message from Bo to Anna."""
    return send(bo, anna, 'Something **unkind**')


def page(user):
    return reverse('conversation', kwargs={'pk': user.pk})


def report_page(message):
    return reverse('message_report', kwargs={'pk': message.sender_id, 'message_pk': message.pk})


def test_the_address():
    assert reverse('message_report', kwargs={'pk': 7, 'message_pk': 3}) == '/messages/7/report/3/'


def test_report_stands_under_received_messages_only(as_anna, anna, bo, unkind):
    mine = send(anna, bo, 'My answer')

    resp = as_anna.get(page(bo))

    assertContains(resp, f'href="{report_page(unkind)}"', count=1)
    assertNotContains(resp, f'/report/{mine.pk}/')


def test_the_confirmation_page_shows_the_message_and_what_happens(as_anna, bo, unkind):
    resp = as_anna.get(report_page(unkind))

    assertContains(resp, 'Something unkind')
    assertContains(resp, f'Member {bo.pk}')
    assertContains(resp, 'The moderators will see this message')
    assertContains(resp, 'Note to the moderators')
    assert not Report.objects.exists()


def test_reporting_saves_the_copy_and_returns_to_the_message(as_anna, anna, bo, unkind, security_log):
    resp = as_anna.post(report_page(unkind), {'note': 'Not the first time'})

    assertRedirects(resp, f'{page(bo)}#message-{unkind.pk}', fetch_redirect_response=False)
    report = Report.objects.get()
    assert (report.reporter, report.sender, report.message) == (anna, bo, unkind)
    assert (report.text, report.note) == ('Something **unkind**', 'Not the first time')
    line = security_log()[-1]
    assert line.startswith(f'report user={anna.pk} sender={bo.pk} report={report.pk} ip=')
    assert 'unkind' not in line and 'first time' not in line


def test_the_note_is_optional_and_at_most_500_characters(as_anna, unkind):
    resp = as_anna.post(report_page(unkind), {'note': 'x' * 501})
    assert resp.status_code == 200
    assert resp.context['form'].errors['note']
    assert not Report.objects.exists()

    assert as_anna.post(report_page(unkind), {'note': ''}).status_code == 302
    assert Report.objects.get().note == ''


def test_the_reporter_is_told_and_sees_reported_instead_of_the_link(as_anna, bo, unkind):
    resp = as_anna.post(report_page(unkind), follow=True)

    assertContains(resp, 'The message was reported to the moderators.')
    assertContains(resp, 'Reported')
    assertNotContains(resp, f'href="{report_page(unkind)}"')


def test_the_sender_sees_nothing_of_the_report(as_anna, as_bo, anna, unkind):
    as_anna.post(report_page(unkind), {'note': 'A note'})

    resp = as_bo.get(page(anna))

    assertNotContains(resp, 'Reported')
    assertNotContains(resp, 'A note')


def test_a_message_reported_already_leads_back_without_a_second_report(as_anna, bo, unkind):
    as_anna.post(report_page(unkind))

    for resp in (as_anna.get(report_page(unkind)), as_anna.post(report_page(unkind))):
        assertRedirects(resp, f'{page(bo)}#message-{unkind.pk}', fetch_redirect_response=False)
    assert Report.objects.count() == 1


def test_one_cannot_report_ones_own_message(as_bo, anna, bo, unkind):
    # Neither as the conversation with the receiver, nor with oneself
    for pk in (anna.pk, bo.pk):
        url = reverse('message_report', kwargs={'pk': pk, 'message_pk': unkind.pk})

        assert as_bo.get(url).status_code == 404
        assert as_bo.post(url).status_code == 404
    assert not Report.objects.exists()


def test_one_cannot_report_a_message_of_someone_elses_conversation(as_anna, anna, bo):
    cia = add_member('cia')
    theirs = send(bo, cia, 'Between Bo and Cia')
    send(bo, anna, 'So that Anna and Bo have a conversation')

    for pk in (bo.pk, cia.pk):
        url = reverse('message_report', kwargs={'pk': pk, 'message_pk': theirs.pk})

        resp = as_anna.get(url)
        assert resp.status_code == 404
        assert as_anna.post(url).status_code == 404
    assert not Report.objects.exists()


def test_a_missing_message_is_a_404(as_anna, bo, unkind):
    url = reverse('message_report', kwargs={'pk': bo.pk, 'message_pk': 999999})

    assert as_anna.get(url).status_code == 404


def test_a_visitor_is_sent_to_the_login_page(client, unkind):
    for resp in (client.get(report_page(unkind)), client.post(report_page(unkind))):
        assert resp.status_code == 302
        assert resp.url.startswith(reverse('account_login'))
    assert not Report.objects.exists()


def test_a_blocked_pair_can_still_report(as_anna, anna, bo, unkind):
    as_anna.post(reverse('conversation_block', kwargs={'pk': bo.pk}))

    assertContains(as_anna.get(page(bo)), f'href="{report_page(unkind)}"')
    assert as_anna.post(report_page(unkind)).status_code == 302
    assert Report.objects.count() == 1


def test_the_conversation_page_costs_no_more_queries_with_reports(
    as_anna, anna, bo, django_assert_num_queries
):
    for n in range(4):
        Report.of(send(bo, anna, f'Message {n}'), anna)
    as_anna.get(page(bo))

    with django_assert_num_queries(8 + 6):
        as_anna.get(page(bo))
