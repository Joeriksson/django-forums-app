from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

from forums.models import Forum, Post, Thread
from pages.views import HomePageView

User = get_user_model()


@pytest.fixture
def member(db):
    return User.objects.create_user(username='member', email='member@example.com', password='x')


@pytest.fixture
def forum(db):
    return Forum.objects.create(title='Trips', description='Where to next')


def add_thread(forum, user, title, days_ago=0):
    thread = Thread.objects.create(title=title, text='Text', forum=forum, user=user)
    Thread.objects.filter(pk=thread.pk).update(added=timezone.now() - timedelta(days=days_ago))
    return thread


def add_reply(thread, user, days_ago=0):
    post = Post.objects.create(text='A reply', thread=thread, user=user)
    Post.objects.filter(pk=post.pk).update(added=timezone.now() - timedelta(days=days_ago))
    return post


def test_homepage_url_resolves_homepageview():
    # as_view() functions are all named 'view', so compare the view class
    assert resolve('/').func.view_class is HomePageView


# Visitors


def test_home_for_a_visitor_offers_login_and_nothing_else(client, member, forum):
    add_thread(forum, member, 'Midsummer at the lake')

    resp = client.get(reverse('home'))

    assert resp.status_code == 200
    assertTemplateUsed(resp, 'home.html')
    assertContains(resp, f'href="{reverse("account_login")}"')
    assertNotContains(resp, 'Midsummer at the lake')
    assertNotContains(resp, 'Trips')


def test_home_for_a_visitor_runs_no_forum_query(client, member, forum, django_assert_num_queries):
    add_thread(forum, member, 'Midsummer at the lake')

    with django_assert_num_queries(0):
        client.get(reverse('home'))


def test_home_offers_signup_only_while_it_is_open(client, db, settings):
    settings.SIGNUP_OPEN = False
    assertNotContains(client.get(reverse('home')), reverse('account_signup'))

    settings.SIGNUP_OPEN = True
    assertContains(client.get(reverse('home')), reverse('account_signup'))


# Members: the latest conversations


def test_home_for_a_member_lists_threads_with_their_forum(client, member, forum):
    thread = add_thread(forum, member, 'Midsummer at the lake')
    client.force_login(member)

    resp = client.get(reverse('home'))

    assertContains(resp, 'Midsummer at the lake')
    assertContains(resp, f'href="{reverse("thread_detail", args=[thread.pk])}"')
    assertContains(resp, 'Trips')
    assertContains(resp, f'Member {member.pk}')
    assertNotContains(resp, 'member@example.com</a>')


def test_home_orders_threads_by_latest_activity(client, member, forum):
    old_but_active = add_thread(forum, member, 'Old but active', days_ago=30)
    newer_quiet = add_thread(forum, member, 'Newer and quiet', days_ago=3)
    oldest = add_thread(forum, member, 'Oldest', days_ago=40)
    add_reply(old_but_active, member, days_ago=1)
    client.force_login(member)

    threads = list(client.get(reverse('home')).context['threads'])

    assert threads == [old_but_active, newer_quiet, oldest]
    assert threads[0].post_count == 1
    assert threads[1].post_count == 0


def test_home_shows_at_most_fifteen_threads(client, member, forum):
    for number in range(17):
        add_thread(forum, member, f'Thread {number}', days_ago=number)
    client.force_login(member)

    resp = client.get(reverse('home'))

    assert len(resp.context['threads']) == 15
    assertContains(resp, 'Thread 0')
    assertNotContains(resp, 'Thread 16')
    assertContains(resp, f'href="{reverse("forum_list")}"')


def test_home_without_threads_says_so(client, member):
    client.force_login(member)

    assertContains(client.get(reverse('home')), 'No conversations yet')


def test_home_query_count_does_not_grow_with_threads(client, member, forum, django_assert_max_num_queries):
    for number in range(10):
        thread = add_thread(forum, User.objects.create_user(username=f'u{number}', email=f'u{number}@example.com'), f'Thread {number}')
        add_reply(thread, member)
    client.force_login(member)

    # Six for the logged-in member, one for the threads
    with django_assert_max_num_queries(7):
        client.get(reverse('home'))
