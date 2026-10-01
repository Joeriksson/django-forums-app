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
