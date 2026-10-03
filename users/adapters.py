from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from allauth.mfa.adapter import DefaultMFAAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from copy import copy

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import ValidationError

from pages.models import SiteSettings

from .encryption import decrypt_secret, encrypt_secret
from .models import Invitation

def user_display(user):
    """How allauth names a user (ACCOUNT_USER_DISPLAY): never the username."""
    return user.display_name


# allauth also calls clean_email for e.g. password resets; only these pages sign up
SIGNUP_URL_NAMES = {'account_signup', 'socialaccount_signup'}


class AccountAdapter(DefaultAccountAdapter):
    # allauth names the site in its emails from Sites, which each process caches: a
    # renamed site would keep its old name until a restart. Take it from SiteSettings.

    def send_mail(self, template_prefix, email, context):
        site = copy(get_current_site(allauth_context.request))
        site.name = SiteSettings.load().title
        super().send_mail(template_prefix, email, {'current_site': site, **context})

    def format_email_subject(self, subject):
        return f'[{SiteSettings.load().title}] {subject}'

    def is_open_for_signup(self, request):
        # Existing users can always log in, with a password or GitHub.
        # A valid invitation link opens signup for its address only (see clean_email).
        return settings.SIGNUP_OPEN or Invitation.from_session(request) is not None

    def clean_email(self, email):
        email = super().clean_email(email)
        invitation = self._signup_invitation()
        if invitation and email.lower() != invitation.email.lower():
            raise ValidationError(f'Sign up with the invited address: {invitation.email}')
        return email

    def _signup_invitation(self):
        """The invitation that signup depends on right now, if any."""
        request = self.request
        if (
            request is None
            or settings.SIGNUP_OPEN
            or getattr(request.resolver_match, 'url_name', None) not in SIGNUP_URL_NAMES
        ):
            return None
        return Invitation.from_session(request)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        if settings.SIGNUP_OPEN:
            return True
        invitation = Invitation.from_session(request)
        if invitation is None:
            return False
        # GitHub must have verified the invited address, as primary or secondary address
        verified = {
            address.email.lower() for address in sociallogin.email_addresses if address.verified
        }
        return invitation.email.lower() in verified


class MFAAdapter(DefaultMFAAdapter):
    def get_totp_issuer(self):
        # The name authenticator apps show for this site
        return SiteSettings.load().title

    # allauth stores authenticator secrets and recovery-code seeds as they are unless
    # these two are overridden

    def encrypt(self, text):
        return encrypt_secret(text)

    def decrypt(self, encrypted_text):
        return decrypt_secret(encrypted_text)
