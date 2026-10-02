"""The forum is for its members: reading needs a login, on the site and through the API."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertRedirects
from rest_framework.test import APIClient

from forums.models import Forum, Post, Thread

User = get_user_model()


@pytest.fixture
def member(db):
    return User.objects.create_user(username='member', email='member@example.com', password='x')


@pytest.fixture
def thread(member):
    forum = Forum.objects.create(title='Forum', description='Description')
    thread = Thread.objects.create(title='A thread', text='secret words', forum=forum, user=member)
    Post.objects.create(text='secret reply', thread=thread, user=member)
    return thread


def reading_pages(thread):
    return [
        reverse('forum_list'),
        reverse('forum_detail', args=[thread.forum_id]),
        reverse('thread_detail', args=[thread.pk]),
        reverse('search_results') + '?q=secret',
    ]


def test_visitors_are_sent_to_the_login_page(client, thread):
    for url in reading_pages(thread):
        resp = client.get(url)

        assertRedirects(resp, f"{reverse('account_login')}?next={url.replace('?', '%3F').replace('=', '%3D')}", fetch_redirect_response=False)
        assert b'secret' not in resp.content


def test_members_can_read(client, member, thread):
    client.force_login(member)

    for url in reading_pages(thread):
        assert client.get(url).status_code == 200


def test_login_leads_back_to_the_page(client, member, thread, verify_email):
    verify_email(member)
    member.set_password('a-long-test-pass-123')
    member.save()
    url = reverse('thread_detail', args=[thread.pk])
    login_url = client.get(url)['Location']

    resp = client.post(login_url, {'login': member.email, 'password': 'a-long-test-pass-123'})

    assertRedirects(resp, url, fetch_redirect_response=False)


def test_home_page_is_open_to_visitors(client, db):
    assert client.get(reverse('home')).status_code == 200


def test_search_by_a_visitor_runs_no_query(client, thread, django_assert_num_queries):
    with django_assert_num_queries(0):
        client.get(reverse('search_results') + '?q=secret')


# The API


API_READS = ['/api/', '/api/forums/', '/api/threads/', '/api/posts/', '/api/schema/']


@pytest.mark.parametrize('url', API_READS)
def test_api_refuses_visitors(thread, url):
    resp = APIClient().get(url)

    assert resp.status_code in (401, 403)
    assert b'secret' not in resp.content


def test_api_refuses_visitors_on_single_objects(thread):
    client = APIClient()

    for url in (f'/api/forums/{thread.forum_id}/', f'/api/threads/{thread.pk}/', '/api/posts/1/'):
        assert client.get(url).status_code in (401, 403)


@pytest.mark.parametrize('url', API_READS)
def test_api_answers_members(member, thread, url):
    client = APIClient()
    client.force_login(member)

    assert client.get(url).status_code == 200


def test_api_member_still_cannot_create_a_forum(member, db):
    client = APIClient()
    client.force_login(member)

    resp = client.post('/api/forums/', {'title': 'Mine', 'description': 'x'})

    assert resp.status_code == 403
    assert not Forum.objects.filter(title='Mine').exists()
