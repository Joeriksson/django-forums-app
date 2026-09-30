from allauth.account.adapter import get_adapter
from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def signup_is_open(context):
    """Whether the signup page lets people sign up, e.g. to show or hide its link."""
    request = context.get('request')
    if request is None:
        # Django renders 500.html without a request: leave the link out there
        return False
    return get_adapter(request).is_open_for_signup(request)
