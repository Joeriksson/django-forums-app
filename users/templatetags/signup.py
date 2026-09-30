from allauth.account.adapter import get_adapter
from django import template

from users.models import Invitation

register = template.Library()


@register.simple_tag(takes_context=True)
def signup_is_open(context):
    """Whether the signup page lets people sign up, e.g. to show or hide its link."""
    request = context.get('request')
    if request is None:
        # Django renders 500.html without a request: leave the link out there
        return False
    return get_adapter(request).is_open_for_signup(request)


@register.simple_tag(takes_context=True)
def invited_email(context):
    """The address of the invitation this visitor opened, or None."""
    request = context.get('request')
    invitation = Invitation.from_session(request) if request is not None else None
    return invitation.email if invitation else None
