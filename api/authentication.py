from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class NonStaffTokenAuthentication(TokenAuthentication):
    """
    Token authentication that refuses staff accounts while STAFF_REQUIRE_MFA is on:
    a token never passes the two-factor step. Staff log in on the site instead.
    """

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if settings.STAFF_REQUIRE_MFA and user.is_staff:
            raise AuthenticationFailed(
                'Staff accounts cannot use API tokens. Log in on the site instead.'
            )
        return user, token
