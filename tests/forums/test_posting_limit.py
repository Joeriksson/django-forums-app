import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from pytest_django.asserts import assertContains
from rest_framework.throttling import SimpleRateThrottle

from forums.models import Post, Thread


@pytest.fixture
def rates(monkeypatch):
    """Lower a throttle rate for the test: DRF reads the rates when it is imported."""

    def _rates(**rates):
        for scope, rate in rates.items():
            monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, rate)

    return _rates


@pytest.fixture
def anna(add_user):
    return add_user('anna', 'anna@example.com', 'testpass123')


@pytest.fixture
def thread(anna, add_forum, add_thread):
    forum = add_forum(title='General Forum', description='This is a general forum')
    return add_thread(title='A thread', text='Thread text', forum=forum, user=anna)


def site_post(client, thread, text='A reply'):
    return client.post(reverse('post_add', kwargs={'pk': thread.pk}), {'text': text})


def site_thread(client, thread, title='New thread'):
    return client.post(
        reverse('thread_add', kwargs={'pk': thread.forum_id}), {'title': title, 'text': 'Text'}
    )


def api_post(client, thread, text='A reply'):
    return client.post('/api/posts/', {'text': text, 'thread': thread.pk}, format='json')


def test_default_rates():
    assert SimpleRateThrottle.THROTTLE_RATES['posting_burst'] == '5/min'
    assert SimpleRateThrottle.THROTTLE_RATES['posting_hour'] == '30/hour'


@pytest.mark.django_db
def test_site_refuses_posts_over_the_limit_and_keeps_the_text(client, anna, thread, rates, security_log):
    rates(posting_burst='2/min')
    client.force_login(anna)

    assert [site_post(client, thread).status_code for _ in range(2)] == [302, 302]
    resp = site_post(client, thread, text='My long reply')

    assert resp.status_code == 429
    assertContains(resp, 'posting too fast', status_code=429)
    # The text is still in the form, to send again later
    assertContains(resp, 'My long reply', status_code=429)
    assert Post.objects.filter(thread=thread).count() == 2
    assert security_log()[-1].startswith(f'denied status=429 user={anna.pk} method=POST')


@pytest.mark.django_db
def test_threads_and_posts_share_the_limit(client, anna, thread, rates):
    rates(posting_burst='2/min')
    client.force_login(anna)

    assert site_post(client, thread).status_code == 302
    assert site_thread(client, thread).status_code == 302

    assert site_thread(client, thread, title='One too many').status_code == 429
    assert not Thread.objects.filter(title='One too many').exists()


@pytest.mark.django_db
def test_site_and_api_share_the_limit(client, anna, thread, rates, get_user_client):
    rates(posting_burst='2/min')
    client.force_login(anna)
    api = get_user_client(anna)

    assert site_post(client, thread).status_code == 302
    assert api_post(api, thread).status_code == 201

    assert api_post(api, thread).status_code == 429
    assert site_post(client, thread).status_code == 429
    assert Post.objects.filter(thread=thread).count() == 2


@pytest.mark.django_db
def test_hourly_limit_applies_too(client, anna, thread, rates):
    rates(posting_burst='10/min', posting_hour='2/hour')
    client.force_login(anna)

    assert [site_post(client, thread).status_code for _ in range(3)] == [302, 302, 429]


@pytest.mark.django_db
def test_each_user_has_their_own_count(client, anna, thread, rates, add_user):
    rates(posting_burst='1/min')
    client.force_login(anna)
    assert [site_post(client, thread).status_code for _ in range(2)] == [302, 429]

    client.force_login(add_user('bo', 'bo@example.com', 'testpass123'))

    assert site_post(client, thread).status_code == 302


@pytest.mark.django_db
def test_rejected_forms_do_not_count(client, anna, thread, rates):
    rates(posting_burst='1/min')
    client.force_login(anna)

    assert [site_post(client, thread, text='').status_code for _ in range(3)] == [200, 200, 200]
    assert site_post(client, thread).status_code == 302


@pytest.mark.django_db
def test_moderators_are_limited_too(thread, rates, add_user, get_user_client):
    rates(posting_burst='1/min')
    moderator = add_user('moderator', 'moderator@example.com', 'testpass123')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    client = get_user_client(moderator)

    assert [site_post(client, thread).status_code for _ in range(2)] == [302, 429]


@pytest.mark.django_db
def test_reading_and_editing_are_not_counted_as_posting(anna, thread, rates, get_user_client):
    rates(posting_burst='1/min')
    api = get_user_client(anna)
    assert api_post(api, thread).status_code == 201

    assert api.get('/api/posts/').status_code == 200
    assert api.patch(f'/api/threads/{thread.pk}/', {'title': 'Edited'}, format='json').status_code == 200
    assert api.post('/api/threads/', {'title': 'x', 'text': 'x', 'forum': thread.forum_id}, format='json').status_code == 429
