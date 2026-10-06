from django import template
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext, ngettext

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
            return gettext('just now')
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return ngettext('%(count)s minute ago', '%(count)s minutes ago', minutes) % {'count': minutes}
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return ngettext('%(count)s hour ago', '%(count)s hours ago', hours) % {'count': hours}
    elif seconds < 2 * 86400:
        return gettext('yesterday')
    elif seconds < 7 * 86400:
        days = int(seconds // 86400)
        return ngettext('%(count)s day ago', '%(count)s days ago', days) % {'count': days}
    return date_format(timezone.localtime(value), 'j F Y')
