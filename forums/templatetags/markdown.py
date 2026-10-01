from django import template

from forums.markdown import render

register = template.Library()


@register.filter()
def render_markdown(value):
    return render(value)
