from django import template

from notifications.models import Notification

register = template.Library()


@register.simple_tag
def unread_notifications(user):
    """The numbers on the header's bell and envelope: replies and messages not yet read. One query."""
    return Notification.unread_counts(user)
