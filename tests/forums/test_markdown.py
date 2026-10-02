import pytest
from django.template import Context, Template
from django.utils.safestring import SafeString

from forums.markdown import render, sanitize


# Markdown features


@pytest.mark.parametrize(
    'text, expected',
    [
        ('**bold**', '<strong>bold</strong>'),
        ('*italic*', '<em>italic</em>'),
        ('~~gone~~', '<s>gone</s>'),
        ('first line\nsecond line', 'first line<br>'),
        ('> quoted', '<blockquote>'),
        ('- item', '<li>item</li>'),
        ('`inline`', '<code>inline</code>'),
        ('| a | b |\n|---|---|\n| 1 | 2 |', '<table>'),
        ('```python\nprint(1)\n```', '<pre><code class="language-python">'),
        ('![alt text](https://example.com/a.png)', '<img src="https://example.com/a.png"'),
    ],
)
def test_render_markdown_features(text, expected):
    assert expected in render(text)


@pytest.mark.parametrize(
    'text',
    ['See https://example.com/page for more', '[a link](https://example.com/page)'],
)
def test_render_links(text):
    html = render(text)

    assert '<a href="https://example.com/page"' in html
    assert 'nofollow' in html
    assert 'noopener' in html


def test_render_empty_text():
    assert render('') == ''
    assert render(None) == ''


# Unsafe input


@pytest.mark.parametrize(
    'text, forbidden',
    [
        ('<script>alert(1)</script>', '<script'),
        ('<img src=x onerror=alert(1)>', '<img'),
        ('<b style="color: red">red</b>', '<b'),
        ('<iframe src="https://example.com"></iframe>', '<iframe'),
        ('[click](javascript:alert(1))', '<a'),
        ('[click](data:text/html;base64,PHNjcmlwdD4=)', '<a'),
        ('![x](javascript:alert(1))', '<img'),
        ('![x](data:image/png;base64,AAAA)', 'data:'),
        ('```"><script>alert(1)</script>\ncode\n```', '<script'),
    ],
)
def test_render_refuses_unsafe_input(text, forbidden):
    assert forbidden not in render(text)


@pytest.mark.parametrize(
    'html, forbidden',
    [
        ('<p>hi</p><script>alert(1)</script>', 'script'),
        ('<p onclick="alert(1)">hi</p>', 'onclick'),
        ('<p style="position: fixed">hi</p>', 'style'),
        ('<a href="javascript:alert(1)">x</a>', 'javascript'),
        ('<img src="x" onerror="alert(1)">', 'onerror'),
        ('<iframe src="https://example.com"></iframe>', 'iframe'),
        ('<form action="/x"><input name="a"></form>', 'form'),
    ],
)
def test_sanitize_cleans_html_even_if_the_parser_lets_it_through(html, forbidden):
    assert forbidden not in sanitize(html)


# Template filter


def test_render_markdown_filter_returns_safe_html():
    template = Template('{% load markdown %}{{ text|render_markdown }}')

    html = template.render(Context({'text': '**bold** <script>alert(1)</script>'}))

    assert '<strong>bold</strong>' in html
    assert '<script' not in html


def test_render_returns_safe_string():
    assert isinstance(render('**bold**'), SafeString)


# Images: only over https


def test_https_image_is_shown():
    html = render('![a cat](https://example.com/cat.png "Title")')

    assert '<img src="https://example.com/cat.png"' in html
    assert 'alt="a cat"' in html


@pytest.mark.parametrize(
    'url',
    [
        'http://example.com/cat.png',
        'HTTP://example.com/cat.png',
        '//example.com/cat.png',
        '/static/cat.png',
        'cat.png',
    ],
)
def test_other_images_are_not_loaded(url):
    """No <img>: the browser must not fetch anything that isn't https."""
    html = render(f'![a cat]({url})')

    assert '<img' not in html
    # The description stays readable
    assert 'a cat' in html


def test_http_image_becomes_a_link():
    html = render('![a cat](http://example.com/cat.png)')

    assert '<a href="http://example.com/cat.png"' in html
    assert '>a cat</a>' in html
    assert 'nofollow' in html


def test_http_image_without_description_shows_its_address():
    html = render('![](http://example.com/cat.png)')

    assert '>http://example.com/cat.png</a>' in html


def test_image_description_is_escaped_in_the_link():
    html = render('![<b>x</b> & "y"](http://example.com/cat.png)')

    assert '<b>' not in html
    assert '&lt;b&gt;x&lt;/b&gt; &amp; "y"' in html or '&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;' in html


def test_https_image_inside_a_link_still_works():
    html = render('[![a cat](https://example.com/cat.png)](https://example.com/page)')

    assert '<a href="https://example.com/page"' in html
    assert '<img src="https://example.com/cat.png"' in html


@pytest.mark.parametrize(
    'html',
    [
        '<img src="http://example.com/cat.png" alt="a cat">',
        '<img src="//example.com/cat.png">',
        '<img src="/local.png">',
        '<img src=" https://example.com/cat.png">',
    ],
)
def test_sanitize_drops_the_source_of_images_that_are_not_https(html):
    """Second line: even if the parser produced such an <img>, it loads nothing."""
    assert 'src=' not in sanitize(html)


def test_sanitize_keeps_https_images_and_http_links():
    assert 'src="https://example.com/cat.png"' in sanitize('<img src="https://example.com/cat.png">')
    assert 'href="http://example.com/"' in sanitize('<a href="http://example.com/">x</a>')
