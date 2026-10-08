"""The bell in the header: a link to the notifications with the number of unread ones."""

import re

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from notifications.models import Notification

pytestmark = pytest.mark.django_db

COUNT = reverse('notifications_count')


@pytest.fixture
def member():
    return get_user_model().objects.create_user(
        username='member', email='member@example.com', password='testpass123'
    )


@pytest.fixture
def client(client, member):
    client.force_login(member)
    return client


def notify(user, unread=0, read=0):
    Notification.objects.bulk_create(
        [Notification(user=user) for n in range(unread)]
        + [Notification(user=user, read=True) for n in range(read)]
    )


def bell(html):
    return re.search(r'<a class="bell".*?</a>', html, re.DOTALL).group(0)


def number(html):
    return re.search(r'<span class="bell__number">([^<]*)</span>', bell(html)).group(1)


def test_the_bell_links_to_the_notifications(client):
    html = client.get(reverse('home')).content.decode()

    assert f'href="{reverse("notifications")}"' in bell(html)
    # Its name for screen readers, and the tooltip
    assert '<span class="visually-hidden">Notifications</span>' in bell(html)
    assert 'title="Notifications"' in bell(html)


def test_nothing_unread_shows_no_number(client, member):
    notify(member, read=2)

    html = client.get(reverse('home')).content.decode()

    assert '<span class="bell__count" hidden>' in bell(html)
    assert 'data-count="0"' in bell(html)
    assert '<title>Forums</title>' in html


def test_the_number_of_unread(client, member):
    notify(member, unread=3, read=1)

    html = client.get(reverse('home')).content.decode()

    assert '<span class="bell__count">' in bell(html)
    assert number(html) == '3'
    assert 'data-count="3"' in bell(html)
    assert '<span class="visually-hidden">Unread:</span>' in bell(html)


def test_more_than_nine_is_shown_as_nine_plus(client, member):
    notify(member, unread=12)

    html = client.get(reverse('home')).content.decode()

    assert number(html) == '9+'
    # The script and the title use the real number
    assert 'data-count="12"' in bell(html)
    assert '<title>(12) Forums</title>' in html


def test_the_number_comes_first_in_the_title_of_every_page(client, member):
    notify(member, unread=2)

    html = client.get(reverse('latest')).content.decode()

    assert '<title>(2) Latest conversations</title>' in html


def test_other_members_notifications_do_not_count(client, member):
    other = get_user_model().objects.create_user(
        username='other', email='other@example.com', password='testpass123'
    )
    notify(other, unread=4)

    html = client.get(reverse('home')).content.decode()

    assert 'data-count="0"' in bell(html)


def test_the_bell_marks_its_own_page(client):
    assert 'aria-current="page"' in bell(client.get(reverse('notifications')).content.decode())
    assert 'aria-current' not in bell(client.get(reverse('home')).content.decode())


def test_a_visitor_has_no_bell_and_no_script(member):
    notify(member, unread=1)

    html = Client().get(reverse('home')).content.decode()

    assert 'class="bell"' not in html
    assert 'notifications.js' not in html
    assert '<title>Wildvasa</title>' in html


def test_the_script_gets_the_address_to_ask(client):
    html = client.get(reverse('home')).content.decode()

    assert re.search(rf'<script defer src="[^"]*js/notifications.js" data-url="{COUNT}"></script>', html)


def test_the_bell_is_on_the_account_pages_too(client):
    html = client.get(reverse('account_email')).content.decode()

    assert 'class="bell"' in html
    assert 'notifications.js' in html


# The address the script asks

def test_count(client, member):
    notify(member, unread=3, read=2)

    resp = client.get(COUNT)

    assert resp.status_code == 200
    assert resp.json() == {'unread': 3}
    assert resp['Cache-Control'] == 'no-store'


def test_count_is_the_members_own(client):
    other = get_user_model().objects.create_user(
        username='other', email='other@example.com', password='testpass123'
    )
    notify(other, unread=4)

    assert client.get(COUNT).json() == {'unread': 0}


def test_count_for_a_visitor_redirects_to_the_login_page(security_log):
    resp = Client().get(COUNT)

    # A redirect, which the script doesn't follow: it stops asking. Not a 403, which
    # would put a line in the security log every half minute
    assert resp.status_code == 302
    assert resp['Location'].startswith(reverse('account_login'))
    assert security_log() == []


def test_count_uses_five_queries(client, member, django_assert_num_queries):
    notify(member, unread=1)

    # The session, the user, two for permissions (who must have two-factor), the number
    with django_assert_num_queries(5):
        client.get(COUNT)


def test_count_follows_reading(client, member):
    notify(member, unread=2)

    client.post(reverse('notifications_read'))

    assert client.get(COUNT).json() == {'unread': 0}
