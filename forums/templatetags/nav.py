from django import template

register = template.Library()

# Which item of the header's menu each page belongs to, by URL name
SECTIONS = {
    'forums': {
        'home',
        'forum_detail',
        'forum_add',
        'forum_update',
        'thread_detail',
        'thread_add',
        'thread_update',
        'thread_delete',
        'post_add',
        'post_update',
        'post_delete',
    },
    'latest': {'latest'},
    'search': {'search_results'},
}


@register.simple_tag(takes_context=True)
def nav_section(context):
    """The menu item of the current page ('forums', 'latest', 'search'), or None."""
    request = context.get('request')
    # Django renders 500.html without a request
    match = getattr(request, 'resolver_match', None)
    name = match.url_name if match else None
    return next((section for section, names in SECTIONS.items() if name in names), None)
