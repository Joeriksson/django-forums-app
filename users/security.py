"""
Staff accounts must use two-factor authentication.

The admin can change every account and forum, so a stolen staff password alone
mustn't be enough. Staff who haven't set up an authenticator app are sent to do
that before they reach a staff page. The admin's own login form is replaced by
allauth's (see project/urls.py), which asks for the code.
"""

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


def has_second_factor(user):
    # Recovery codes only back the authenticator app up; alone they don't count
    return Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()


class StaffMFAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def staff_paths(self):
        return (reverse('admin:index'), reverse('customuser-list'))

    def __call__(self, request):
        user = request.user
        if (
            settings.STAFF_REQUIRE_MFA
            and user.is_authenticated
            and user.is_staff
            and request.path.startswith(self.staff_paths())
            and not has_second_factor(user)
        ):
            messages.warning(
                request,
                'Staff accounts need two-factor authentication. Set up an authenticator app to continue.',
            )
            return redirect('mfa_index')
        return self.get_response(request)
