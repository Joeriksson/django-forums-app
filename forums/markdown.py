import nh3
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

# Raw HTML in the text is not passed through: it is shown as text.
_parser = MarkdownIt(
    'commonmark',
    {'html': False, 'breaks': True, 'linkify': True, 'typographer': True},
).enable(['table', 'strikethrough', 'linkify', 'replacements', 'smartquotes'])

ALLOWED_TAGS = {
    'a', 'blockquote', 'br', 'code', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'hr', 'img', 'li', 'ol', 'p', 'pre', 's', 'strong', 'table', 'tbody', 'td',
    'th', 'thead', 'tr', 'ul',
}
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
    'code': {'class'},  # language-<name> on fenced code, for highlight.js
    'img': {'src', 'alt', 'title'},
    'ol': {'start'},
}
ALLOWED_URL_SCHEMES = {'http', 'https', 'mailto'}


def sanitize(html):
    """Second line of defence: keep only the tags and attributes the parser should produce."""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel='nofollow noopener noreferrer',
    )


def render(text):
    """Turn a user's Markdown into HTML that is safe to put on a page."""
    if not text:
        return ''
    return mark_safe(sanitize(_parser.render(text)))
