import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains
from rest_framework.throttling import SimpleRateThrottle

SEARCH_URL = reverse('search_results')
PREVIEW_URL = reverse('markdown_preview')
IP = '203.0.113.7'


@pytest.fixture
def anna(add_user):
    return add_user('anna', 'anna@example.com', 'testpass123')


def search(client, query='hello', **extra):
    return client.get(SEARCH_URL, {'q': query}, **extra)


def preview(client, text='**bold**'):
    return client.post(PREVIEW_URL, {'text': text})


def test_default_rates():
    assert SimpleRateThrottle.THROTTLE_RATES['search'] == '20/min'
    assert SimpleRateThrottle.THROTTLE_RATES['preview'] == '30/min'


# Search


@pytest.mark.django_db
def test_anonymous_search_is_limited_per_address(client, rates, security_log):
    rates(search='2/min')

    assert [search(client, REMOTE_ADDR=IP).status_code for _ in range(2)] == [200, 200]
    resp = search(client, REMOTE_ADDR=IP)

    assert resp.status_code == 429
    assertContains(resp, 'Too many searches', status_code=429)
    assert list(resp.context['object_list']) == []
    assert security_log() == [f"denied status=429 method=GET path='{SEARCH_URL}' ip={IP}"]
    # Another address has its own count
    assert search(client, REMOTE_ADDR='203.0.113.8').status_code == 200


@pytest.mark.django_db
def test_refused_search_does_not_query_threads_and_posts(
    client, rates, django_assert_num_queries
):
    rates(search='1/min')
    search(client)

    with django_assert_num_queries(0):
        assert search(client).status_code == 429


@pytest.mark.django_db
def test_logged_in_search_is_limited_per_user(client, rates, anna, add_user):
    rates(search='1/min')
    client.force_login(anna)
    assert [search(client).status_code for _ in range(2)] == [200, 429]

    # Same address, other user
    client.force_login(add_user('bo', 'bo@example.com', 'testpass123'))

    assert search(client).status_code == 200


@pytest.mark.django_db
def test_too_short_searches_do_not_count(client, rates):
    rates(search='1/min')

    assert [search(client, query='ab').status_code for _ in range(3)] == [200, 200, 200]
    assert search(client).status_code == 200


# Preview


@pytest.mark.django_db
def test_preview_is_limited_per_user(client, rates, anna, add_user, security_log):
    rates(preview='2/min')
    client.force_login(anna)

    assert [preview(client).status_code for _ in range(3)] == [200, 200, 429]
    assert security_log()[-1].startswith(f'denied status=429 user={anna.pk} method=POST')

    client.force_login(add_user('bo', 'bo@example.com', 'testpass123'))

    assert preview(client).status_code == 200


@pytest.mark.django_db
def test_preview_does_not_use_up_the_posting_limit(client, rates, anna, add_forum, add_thread):
    rates(posting_burst='1/min')
    forum = add_forum(title='General Forum', description='This is a general forum')
    thread = add_thread(title='A thread', text='Thread text', forum=forum, user=anna)
    client.force_login(anna)

    assert [preview(client).status_code for _ in range(3)] == [200, 200, 200]

    resp = client.post(reverse('post_add', kwargs={'pk': thread.pk}), {'text': 'A reply'})
    assert resp.status_code == 302
