from datetime import timedelta

import pytest
from django.utils import timezone

from forums.templatetags.when import when

NOW = timezone.now().replace(year=2026, month=10, day=20, hour=15, minute=0, second=0, microsecond=0)


@pytest.mark.parametrize(
    'delta, expected',
    [
        (timedelta(seconds=20), 'just now'),
        (timedelta(minutes=1), '1 minute ago'),
        (timedelta(minutes=45), '45 minutes ago'),
        (timedelta(hours=1), '1 hour ago'),
        (timedelta(hours=5), '5 hours ago'),
        (timedelta(days=1), 'yesterday'),
        (timedelta(days=4), '4 days ago'),
        (timedelta(days=6, hours=23), '6 days ago'),
        (timedelta(days=7), '13 October 2026'),
        (timedelta(days=400), '15 September 2025'),
    ],
)
def test_when(delta, expected):
    assert when(NOW - delta, now=NOW) == expected


def test_when_in_the_future_is_a_date():
    """A clock that is slightly off must not print a negative time."""
    assert when(NOW + timedelta(seconds=30), now=NOW) == 'just now'
    assert when(NOW + timedelta(days=2), now=NOW) == '22 October 2026'


def test_when_without_a_value():
    assert when(None) == ''
