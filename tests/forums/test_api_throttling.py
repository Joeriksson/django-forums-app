import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

URL = '/api/forums/'


@pytest.fixture
def rates(monkeypatch):
    """Lower a throttle rate for the test: DRF reads the rates when it is imported."""

    def _rates(**rates):
        for scope, rate in rates.items():
            monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, scope, rate)

    return _rates


def statuses(client, count, **extra):
    return [client.get(URL, **extra).status_code for _ in range(count)]


def test_default_rates():
    assert SimpleRateThrottle.THROTTLE_RATES['anon'] == '60/min'
    assert SimpleRateThrottle.THROTTLE_RATES['user'] == '120/min'


@pytest.mark.django_db
def test_anonymous_client_is_limited_per_address(rates, security_log):
    rates(anon='2/min')
    client = APIClient()

    assert statuses(client, 3, REMOTE_ADDR='203.0.113.7') == [200, 200, 429]
    # Another address has its own count
    assert statuses(client, 1, REMOTE_ADDR='203.0.113.8') == [200]
    assert security_log() == [f"denied status=429 method=GET path='{URL}' ip=203.0.113.7"]


@pytest.mark.django_db
def test_logged_in_user_is_limited_per_user(rates, add_user, get_user_client):
    rates(user='2/min', anon='1/min')
    anna = get_user_client(add_user('anna', 'anna@example.com', 'testpass123'))
    bo = get_user_client(add_user('bo', 'bo@example.com', 'testpass123'))

    assert statuses(anna, 3) == [200, 200, 429]
    # Same address, other user
    assert statuses(bo, 1) == [200]


@pytest.mark.django_db
def test_a_made_up_forwarded_header_does_not_reset_the_count(rates):
    rates(anon='2/min')
    client = APIClient()

    responses = [
        client.get(URL, REMOTE_ADDR='203.0.113.7', HTTP_X_FORWARDED_FOR=f'198.51.100.{n}').status_code
        for n in range(3)
    ]

    assert responses == [200, 200, 429]


@pytest.mark.django_db
def test_behind_a_proxy_the_visitor_is_the_last_forwarded_address(rates, settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}
    rates(anon='2/min')
    client = APIClient()
    proxy = {'REMOTE_ADDR': '10.0.0.2'}

    # The first entry is whatever the client sent; the proxy adds the last one
    assert statuses(client, 3, HTTP_X_FORWARDED_FOR='1.1.1.1, 203.0.113.7', **proxy) == [200, 200, 429]
    assert statuses(client, 1, HTTP_X_FORWARDED_FOR='1.1.1.1, 203.0.113.8', **proxy) == [200]
