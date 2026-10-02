import nh3
from django.utils.html import escape
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

# Raw HTML in the text is not passed through: it is shown as text.
_parser = MarkdownIt(
    'commonmark',
    {'html': False, 'breaks': True, 'linkify': True, 'typographer': True},
).enable(['table', 'strikethrough', 'linkify', 'replacements', 'smartquotes'])


def is_allowed_image(url):
    # Only https: an image is fetched by every reader's browser, and over http anyone
    # on the way could read or replace it. Not relative addresses either.
    return url.lower().startswith('https://')


def render_image(renderer, tokens, idx, options, env):
    """An image that may not be loaded becomes a link to it, so nothing is fetched unasked."""
    token = tokens[idx]
    url = token.attrGet('src') or ''
    if is_allowed_image(url):
        return renderer.image(tokens, idx, options, env)
    description = renderer.renderInlineAsText(token.children or [], options, env) or url
    return f'<a href="{escape(url)}">{escape(description)}</a>'


_parser.add_render_rule('image', render_image)

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


def filter_attribute(tag, attribute, value):
    # url_schemes below is for links and images alike; images are stricter
    if tag == 'img' and attribute == 'src' and not is_allowed_image(value):
        return None
    return value


def sanitize(html):
    """Second line of defence: keep only the tags and attributes the parser should produce."""
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=filter_attribute,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel='nofollow noopener noreferrer',
    )


def render(text):
    """Turn a user's Markdown into HTML that is safe to put on a page."""
    if not text:
        return ''
    return mark_safe(sanitize(_parser.render(text)))
