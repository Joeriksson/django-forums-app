"""
Accounts that can do more than a member must use two-factor authentication.

Staff can change every account and forum, and moderators can delete other
people's threads and posts, so a stolen password alone mustn't be enough. Such
users who haven't set up an authenticator app are sent to do that before they
reach any other page. The admin's own login form is replaced by allauth's (see
project/urls.py), which asks for the code.
"""

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy

MFA_REQUIRED_MESSAGE = gettext_lazy(
    'Staff and moderator accounts need two-factor authentication. '
    'Set up an authenticator app to continue.'
)
# Login, logout, address confirmation and the two-factor pages: needed to set it up
OPEN_PATH = '/accounts/'
# Where project/urls.py mounts the API, when it is enabled
API_PATH = '/api/'


def has_second_factor(user):
    # Recovery codes only back the authenticator app up; alone they don't count
    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


def is_privileged(user):
    """Staff, superusers, and anyone with a permission, directly or through a group (moderators)."""
    # Members have no permissions at all, so any permission means extra rights
    return user.is_staff or user.is_superuser or bool(user.get_all_permissions())


class StaffMFAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            settings.STAFF_REQUIRE_MFA
            and user.is_authenticated
            and not request.path.startswith(OPEN_PATH)
            and is_privileged(user)
            and not has_second_factor(user)
        ):
            if request.path.startswith(API_PATH):
                return JsonResponse({'detail': MFA_REQUIRED_MESSAGE}, status=403)
            messages.warning(request, MFA_REQUIRED_MESSAGE)
            return redirect('mfa_index')
        return self.get_response(request)
