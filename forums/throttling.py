"""
How fast a user may create threads and posts.

Every post in a thread with subscribers sends them a mail, so a flood of posts is
also a flood of mail. The website and the API share the counters: they are DRF
throttles, which the web views use through `posting_allowed`.
"""

from rest_framework.throttling import UserRateThrottle


class PostingBurstThrottle(UserRateThrottle):
    scope = 'posting_burst'


class PostingHourThrottle(UserRateThrottle):
    scope = 'posting_hour'


POSTING_THROTTLES = (PostingBurstThrottle, PostingHourThrottle)


def posting_allowed(request, view=None):
    """Count one new thread or post for the user; False when that is over a limit."""
    # Every throttle gets to count, as in DRF's own check
    return all([throttle().allow_request(request, view) for throttle in POSTING_THROTTLES])
