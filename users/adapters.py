from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # allauth's social adapter asks this too, so it also covers GitHub signups.
        # Existing users can still log in, with a password or GitHub.
        return settings.SIGNUP_OPEN
