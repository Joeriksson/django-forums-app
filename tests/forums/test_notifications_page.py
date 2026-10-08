"""The notifications page: what is new in the member's subscribed threads."""

import re

import pytest
from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from forums.models import Post, Subscription
from notifications.models import Notification

pytestmark = pytest.mark.django_db

PAGE = reverse('notifications')
READ = reverse('notifications_read')


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@example.com', 'testpass123')


@pytest.fixture
def member(add_user):
    return add_user('member', 'member@example.com', 'testpass123')


@pytest.fixture
def client(client, member):
    client.force_login(member)
    return client


@pytest.fixture
def forum(add_forum):
    return add_forum(title='General', description='Everything')


@pytest.fixture
def subscribed(add_thread, forum, author, member):
    """A thread the member subscribes to."""

    def _subscribed(title='A thread'):
        thread = add_thread(title=title, text='Text', forum=forum, user=author)
        Subscription.objects.create(thread=thread, user=member)
        return thread

    return _subscribed


@pytest.fixture
def reply(author, django_capture_on_commit_callbacks):
    def _reply(thread, user=None):
        with django_capture_on_commit_callbacks(execute=True):
            return Post.objects.create(text='A reply', thread=thread, user=user or author)

    return _reply


def rows(resp):
    return re.findall(r'<li class="row notification-row.*?</li>', resp.content.decode(), re.DOTALL)


def test_a_visitor_is_sent_to_the_login_page(member):
    from django.test import Client

    resp = Client().get(PAGE)

    assertRedirects(resp, f'{reverse("account_login")}?next={PAGE}')


def test_nothing_new(client):
    resp = client.get(PAGE)

    assertContains(resp, '<h1>Notifications</h1>', html=True)
    assertContains(resp, 'Nothing new.')
    assertNotContains(resp, 'Mark all as read')


def test_a_new_reply_is_listed(client, subscribed, reply, forum):
    thread = subscribed('Cabin trip')
    post = reply(thread)

    resp = client.get(PAGE)

    (row,) = rows(resp)
    assert 'Cabin trip' in row
    assert '<strong>1</strong> new reply' in row
    assert f'href="{reverse("forum_detail", args=[forum.pk])}">General</a>' in row
    assert f'href="{reverse("thread_detail", args=[thread.pk])}?page=1#post-{post.pk}"' in row
    assertNotContains(resp, 'Nothing new.')


def test_several_replies_are_one_row(client, subscribed, reply):
    thread = subscribed()
    for n in range(3):
        reply(thread)

    (row,) = rows(client.get(PAGE))

    assert '<strong>3</strong> new replies' in row


def test_the_link_goes_to_the_first_unread_reply_on_its_page(client, subscribed, reply, site_settings):
    site_settings(posts_per_page=2)
    thread = subscribed()
    for n in range(4):
        reply(thread)
    Notification.objects.update(read=True)
    # The fifth reply is post #6: with the opening post counted, on page 3
    first_unread = reply(thread)
    reply(thread)

    (row,) = rows(client.get(PAGE))

    assert f'?page=3#post-{first_unread.pk}"' in row


def test_the_link_marks_the_row_read(client, subscribed, reply):
    thread = subscribed()
    reply(thread)
    (row,) = rows(client.get(PAGE))
    link = re.search(r'class="row__title" href="([^"]+)"', row).group(1)

    assert client.get(link.replace('&amp;', '&')).status_code == 200

    (row,) = rows(client.get(PAGE))
    assert 'notification-row--read' in row
    assert 'Read' in row
    assert 'new reply' not in row


def test_a_deleted_first_reply_links_to_the_last_page(client, subscribed, reply):
    thread = subscribed()
    first = reply(thread)
    reply(thread)
    first.delete()

    (row,) = rows(client.get(PAGE))

    assert f'href="{reverse("thread_detail", args=[thread.pk])}?page=last"' in row
    assert '<strong>2</strong> new replies' in row


def test_unread_rows_come_first_then_the_newest(client, subscribed, reply):
    old, read, new = subscribed('Old news'), subscribed('Read news'), subscribed('New news')
    reply(read)
    Notification.objects.update(read=True)
    reply(old)
    reply(new)

    titles = [re.search(r'class="row__title"[^>]*>([^<]+)<', row).group(1) for row in rows(client.get(PAGE))]

    assert titles == ['New news', 'Old news', 'Read news']


def test_only_the_members_own_rows(client, subscribed, reply, add_user, add_thread, forum, author):
    other = add_user('other', 'other@example.com', 'testpass123')
    thread = add_thread(title='Not mine', text='Text', forum=forum, user=author)
    Subscription.objects.create(thread=thread, user=other)
    reply(thread)

    resp = client.get(PAGE)

    assertNotContains(resp, 'Not mine')
    assertContains(resp, 'Nothing new.')


def test_the_title_is_escaped(client, subscribed, reply):
    reply(subscribed('<b>Bold</b> & co'))

    assertContains(client.get(PAGE), '&lt;b&gt;Bold&lt;/b&gt; &amp; co')


def test_at_most_fifty_rows(client, member, add_thread, forum, author):
    threads = [add_thread(title=f'Thread {n}', text='Text', forum=forum, user=author) for n in range(52)]
    Notification.objects.bulk_create(Notification(user=member, thread=thread) for thread in threads)

    assert len(rows(client.get(PAGE))) == 50


def test_the_page_uses_one_query_however_many_rows(client, subscribed, reply, django_assert_num_queries):
    for n in range(4):
        thread = subscribed(f'Thread {n}')
        reply(thread)
        reply(thread)

    # Seven for the logged-in member, then the rows with thread, forum and reply position
    with django_assert_num_queries(7 + 1):
        client.get(PAGE)


def test_the_user_menu_links_to_the_page(client):
    resp = client.get(reverse('home'))

    assertContains(resp, f'<a href="{PAGE}">Notifications</a>', html=True)


# Mark all as read

def test_mark_all_as_read(client, subscribed, reply):
    for title in ('One', 'Two'):
        reply(subscribed(title))
    assertContains(client.get(PAGE), 'Mark all as read')

    resp = client.post(READ)

    assertRedirects(resp, PAGE)
    assert not Notification.objects.filter(read=False).exists()
    resp = client.get(PAGE)
    assert len(rows(resp)) == 2
    assertNotContains(resp, 'Mark all as read')


def test_mark_all_leaves_other_members_rows(client, add_user, add_thread, forum, author, reply):
    other = add_user('other', 'other@example.com', 'testpass123')
    thread = add_thread(title='Not mine', text='Text', forum=forum, user=author)
    Subscription.objects.create(thread=thread, user=other)
    reply(thread)

    client.post(READ)

    assert Notification.objects.get().read is False


def test_mark_all_needs_a_post(client, subscribed, reply):
    reply(subscribed())

    assert client.get(READ).status_code == 405
    assert Notification.objects.get().read is False


def test_mark_all_needs_the_csrf_token(member, subscribed, reply):
    from django.test import Client

    reply(subscribed())
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(member)

    assert strict.post(READ).status_code == 403
    assert Notification.objects.get().read is False


def test_mark_all_by_a_visitor_is_sent_to_the_login_page(subscribed, reply):
    from django.test import Client

    reply(subscribed())

    assert Client().post(READ).status_code == 302
    assert Notification.objects.get().read is False


# A reply made in the admin

def test_a_reply_added_in_the_admin_notifies(subscribed, author, add_super_user, django_capture_on_commit_callbacks):
    thread = subscribed()
    admin_user = add_super_user('admin', 'admin@example.com', 'testpass123')
    request = RequestFactory().post('/')
    request.user = admin_user
    post = Post(text='From the admin', thread=thread, user=author)

    with django_capture_on_commit_callbacks(execute=True):
        admin_site._registry[Post].save_model(request, post, form=None, change=False)

    assert Notification.objects.get().post == post
