"""The Reports page: the reported messages, for the moderators, and marking one handled."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from conversations.models import Report, send

pytestmark = pytest.mark.django_db

PAGE = reverse('reports')


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
def moderator(add_totp):
    user = add_member('moderator')
    user.groups.add(Group.objects.get(name='Moderators'))
    # Whoever holds a permission needs an authenticator app to use the site
    add_totp(user)
    return user


@pytest.fixture
def as_moderator(client, moderator):
    client.force_login(moderator)
    return client


@pytest.fixture
def as_anna(anna):
    client = Client()
    client.force_login(anna)
    return client


@pytest.fixture
def report(anna, bo):
    """Anna has reported a message from Bo."""
    return Report.of(send(bo, anna, 'Something **unkind**'), anna, note='Not the first time')


def handle(report):
    return reverse('report_handled', kwargs={'pk': report.pk})


def test_the_addresses():
    assert PAGE == '/messages/reports/'
    assert reverse('report_handled', kwargs={'pk': 3}) == '/messages/reports/3/handled/'


# Who gets in


def test_a_visitor_is_sent_to_the_login_page(client, report):
    for resp in (client.get(PAGE), client.post(handle(report))):
        assert resp.status_code == 302
        assert resp.url.startswith(reverse('account_login'))
    assert Report.objects.get().handled is None


def test_a_member_is_refused(as_anna, report, security_log):
    assert as_anna.get(PAGE).status_code == 403
    assert as_anna.post(handle(report)).status_code == 403

    assert Report.objects.get().handled is None
    assert security_log()[-1].startswith('denied status=403')


def test_seeing_is_not_enough_to_mark_as_handled(client, report, add_totp):
    viewer = add_member('viewer')
    viewer.user_permissions.add(Permission.objects.get(codename='view_report'))
    add_totp(viewer)
    client.force_login(viewer)

    resp = client.get(PAGE)
    assertContains(resp, 'Not handled yet')
    assertNotContains(resp, handle(report))
    assert client.post(handle(report)).status_code == 403
    assert Report.objects.get().handled is None


# What the page shows


def test_the_page_shows_the_message_who_and_the_note(as_moderator, anna, bo, report):
    resp = as_moderator.get(PAGE)

    assertContains(resp, 'Something <strong>unkind</strong>')
    assertContains(resp, 'Not the first time')
    assertContains(resp, f'Member {anna.pk}')
    assertContains(resp, f'Member {bo.pk}')
    assertContains(resp, f'action="{handle(report)}"')
    # Never a username or an address
    for secret in ('anna@example.com', 'bo@example.com', '>anna<', '>bo<'):
        assertNotContains(resp, secret)


def test_the_page_shows_nothing_else_of_the_conversation(as_moderator, anna, bo, report):
    send(anna, bo, 'Not reported, from Anna')
    send(bo, anna, 'Not reported, from Bo')

    assertNotContains(as_moderator.get(PAGE), 'Not reported')


def test_text_and_note_are_escaped(as_moderator, anna, bo):
    Report.of(send(bo, anna, '<script>alert(1)</script>'), anna, note='<b>bold</b> & co')

    resp = as_moderator.get(PAGE)

    assertNotContains(resp, '<script>alert(1)</script>')
    assertContains(resp, '&lt;b&gt;bold&lt;/b&gt; &amp; co')


def test_a_report_about_deleted_accounts_is_still_shown(as_moderator, anna, bo, report):
    anna.delete()
    bo.delete()

    resp = as_moderator.get(PAGE)

    assertContains(resp, 'Something <strong>unkind</strong>')
    assertContains(resp, 'Deleted account', count=2)


def test_an_empty_page(as_moderator):
    assertContains(as_moderator.get(PAGE), 'No reports.')


def test_unhandled_reports_come_first_and_the_page_is_paged(
    as_moderator, moderator, anna, bo, site_settings
):
    site_settings(threads_per_page=2)
    first, second, third = (Report.of(send(bo, anna, f'Message {n}'), anna) for n in range(3))
    as_moderator.post(handle(third))

    resp = as_moderator.get(PAGE)

    assert list(resp.context['reports']) == [second, first]
    assertContains(resp, 'Page 1 of 2')
    assert list(as_moderator.get(PAGE + '?page=2').context['reports']) == [third]


def test_the_page_costs_a_fixed_number_of_queries(as_moderator, anna, bo, django_assert_num_queries):
    for n in range(4):
        Report.of(send(bo, anna, f'Message {n}'), anna)
    as_moderator.get(PAGE)

    # A logged-in page, with one more for the two-factor check of a privileged account
    # and one for the menu's number; then the count and the page of reports
    with django_assert_num_queries(8 + 2 + 2):
        as_moderator.get(PAGE)


# Marking as handled


def test_marking_as_handled_records_who_and_when(as_moderator, moderator, report, security_log):
    resp = as_moderator.post(handle(report))

    assertRedirects(resp, PAGE, fetch_redirect_response=False)
    report.refresh_from_db()
    assert report.handled is not None
    assert report.handled_by == moderator
    assert security_log()[-1].startswith(
        f'report_handled user={moderator.pk} report={report.pk} ip='
    )
    page = as_moderator.get(PAGE)
    assertContains(page, f'Handled by Member {moderator.pk}')
    assertNotContains(page, handle(report))


def test_only_the_first_to_handle_is_recorded(as_moderator, moderator, report, add_totp, security_log):
    other = add_member('other')
    other.groups.add(Group.objects.get(name='Moderators'))
    add_totp(other)
    as_other = Client()
    as_other.force_login(other)

    as_moderator.post(handle(report))
    first = Report.objects.get().handled
    as_other.post(handle(report))

    report.refresh_from_db()
    assert (report.handled, report.handled_by) == (first, moderator)
    assert len([line for line in security_log() if line.startswith('report_handled')]) == 1


def test_handling_takes_a_post_and_an_existing_report(as_moderator, report):
    assert as_moderator.get(handle(report)).status_code == 405
    assert as_moderator.post(reverse('report_handled', kwargs={'pk': 999999})).status_code == 404
    assert Report.objects.get().handled is None


# The menu


def menu(resp):
    return re.search(r'<div class="menu__items">(.*?)</div>\s*</details>', resp.content.decode(), re.DOTALL).group(1)


def test_the_menu_has_reports_with_the_number_waiting_for_moderators(as_moderator, anna, bo, report):
    Report.of(send(bo, anna, 'Another'), anna)
    assert re.search(rf'href="{PAGE}">Reports <span class="menu__count">2</span></a>', menu(as_moderator.get(reverse('home'))))

    for waiting in Report.objects.all():
        as_moderator.post(handle(waiting))

    assert re.search(rf'href="{PAGE}">Reports</a>', menu(as_moderator.get(reverse('home'))))


def test_members_have_no_reports_in_the_menu_and_pay_no_query(as_anna, report, django_assert_num_queries):
    assert 'Reports' not in menu(as_anna.get(reverse('conversation_new')))

    # Eight for a logged-in page and the member list's one
    with django_assert_num_queries(8 + 1):
        as_anna.get(reverse('conversation_new'))
