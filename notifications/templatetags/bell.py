from django import template

from notifications.models import Notification

register = template.Library()


@register.simple_tag
def unread_notifications(user):
    """The number on the header's bell: the member's notifications not yet read. One query."""
    return Notification.unread_count(user)
