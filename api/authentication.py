from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.security import is_privileged


class NonStaffTokenAuthentication(TokenAuthentication):
    """
    Token authentication that refuses staff and moderator accounts while
    STAFF_REQUIRE_MFA is on: a token never passes the two-factor step. They log
    in on the site instead.
    """

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if settings.STAFF_REQUIRE_MFA and is_privileged(user):
            raise AuthenticationFailed(
                'Staff and moderator accounts cannot use API tokens. Log in on the site instead.'
            )
        return user, token
