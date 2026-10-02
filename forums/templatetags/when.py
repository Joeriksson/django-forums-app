from django import template
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()


@register.filter
def when(value, now=None):
    """'5 minutes ago', 'yesterday', '4 days ago', and a date from a week back."""
    if not value:
        return ''
    now = now or timezone.now()
    seconds = (now - value).total_seconds()
    if seconds < 60:
        # A clock that is a little off must not print a negative time
        if seconds > -60:
            return 'just now'
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f'{minutes} minute{"" if minutes == 1 else "s"} ago'
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours} hour{"" if hours == 1 else "s"} ago'
    elif seconds < 2 * 86400:
        return 'yesterday'
    elif seconds < 7 * 86400:
        return f'{int(seconds // 86400)} days ago'
    return date_format(timezone.localtime(value), 'j F Y')
