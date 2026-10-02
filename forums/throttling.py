"""
How fast a user may create threads and posts, search, and preview Markdown.

Every post in a thread with subscribers sends them a mail, so a flood of posts is
also a flood of mail. The website and the API share the counters: they are DRF
throttles, which the web views use through `posting_allowed`.
"""

from rest_framework.throttling import UserRateThrottle


class PostingBurstThrottle(UserRateThrottle):
    scope = 'posting_burst'


class PostingHourThrottle(UserRateThrottle):
    scope = 'posting_hour'


class SearchThrottle(UserRateThrottle):
    # Per user, or per address for visitors: search scans every thread and post
    scope = 'search'


class PreviewThrottle(UserRateThrottle):
    scope = 'preview'


POSTING_THROTTLES = (PostingBurstThrottle, PostingHourThrottle)


def allowed(request, *throttles):
    """Count the request against each throttle; False when that is over a limit."""
    # Every throttle gets to count, as in DRF's own check
    return all([throttle().allow_request(request, None) for throttle in throttles])


def posting_allowed(request):
    """Count one new thread or post for the user; False when that is over a limit."""
    return allowed(request, *POSTING_THROTTLES)
