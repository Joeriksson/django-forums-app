import pytest
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

URL = '/api/forums/'


def statuses(client, count, **extra):
    return [client.get(URL, **extra).status_code for _ in range(count)]


def test_default_rates():
    assert SimpleRateThrottle.THROTTLE_RATES['anon'] == '60/min'
    assert SimpleRateThrottle.THROTTLE_RATES['user'] == '120/min'


@pytest.mark.django_db
def test_visitors_are_refused_before_anything_is_counted(rates):
    """Reading needs a login, so the limit per address never comes into play."""
    rates(anon='2/min')

    assert statuses(APIClient(), 4) == [403, 403, 403, 403]


@pytest.mark.django_db
def test_logged_in_user_is_limited_per_user(rates, add_user, get_user_client):
    rates(user='2/min', anon='1/min')
    anna = get_user_client(add_user('anna', 'anna@example.com', 'testpass123'))
    bo = get_user_client(add_user('bo', 'bo@example.com', 'testpass123'))

    assert statuses(anna, 3) == [200, 200, 429]
    # Same address, other user
    assert statuses(bo, 1) == [200]
