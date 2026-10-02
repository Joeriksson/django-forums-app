"""
The project templates hold no inline scripts or styles: a Content Security Policy
can then refuse all inline code, which is what an injected script would be.
Scripts and styles go into files under static/.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

# Never rendered, so they may say anything
COMMENT = re.compile(r'{#.*?#}|{%\s*comment\b.*?%}.*?{%\s*endcomment\s*%}|<!--.*?-->', re.DOTALL)

INLINE_CODE = {
    'a <script> without src': re.compile(r'<script\b(?![^>]*\bsrc=)[^>]*>', re.IGNORECASE),
    'a <style> block': re.compile(r'<style\b', re.IGNORECASE),
    'a style attribute': re.compile(r'<[^>]*\sstyle\s*=', re.IGNORECASE),
    'an event handler attribute': re.compile(r'<[^>]*\son[a-z]+\s*=', re.IGNORECASE),
    'a javascript: link': re.compile(r'javascript:', re.IGNORECASE),
}


def project_templates():
    for template_dir in settings.TEMPLATES[0]['DIRS']:
        for template in sorted(Path(template_dir).rglob('*.html')):
            yield template.relative_to(template_dir), COMMENT.sub('', template.read_text())


def test_there_are_templates_to_check():
    assert len(list(project_templates())) > 10


@pytest.mark.parametrize('what', INLINE_CODE)
def test_templates_have_no_inline_code(what):
    found = [str(name) for name, text in project_templates() if INLINE_CODE[what].search(text)]

    assert found == [], f'{what} in: {", ".join(found)}'


@pytest.mark.parametrize(
    'html, what',
    [
        ('<script>alert(1)</script>', 'a <script> without src'),
        ('<script type="module">x</script>', 'a <script> without src'),
        ('<style>p {}</style>', 'a <style> block'),
        ('<p style="color: red">', 'a style attribute'),
        ('<a href="#" onclick="x()">', 'an event handler attribute'),
        ('<a href="javascript:x()">', 'a javascript: link'),
    ],
)
def test_the_patterns_find_inline_code(html, what):
    assert INLINE_CODE[what].search(html)


@pytest.mark.parametrize(
    'html',
    [
        '<script src="/static/js/a.js"></script>',
        '<script defer src="/static/js/a.js" data-preview-url="/x/"></script>',
        '<link rel="stylesheet" href="/static/css/a.css">',
        '<p class="style-guide" data-one="1">only = signs</p>',
    ],
)
def test_the_patterns_accept_files(html):
    assert not any(pattern.search(html) for pattern in INLINE_CODE.values())


def test_template_comments_do_not_span_lines():
    """{# #} only works on one line: a longer one is printed on the page. Use {% comment %}."""
    found = [
        f'{name}:{number}'
        for template_dir in settings.TEMPLATES[0]['DIRS']
        for name in sorted(Path(template_dir).rglob('*.html'))
        for number, line in enumerate(name.read_text().splitlines(), 1)
        if line.count('{#') != line.count('#}')
    ]

    assert found == []
