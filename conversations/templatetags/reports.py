from django import template

from conversations.models import Report

register = template.Library()


@register.simple_tag
def unhandled_reports():
    """The number by Reports in the user menu, for those who may see them. One query."""
    return Report.objects.filter(handled__isnull=True).count()
