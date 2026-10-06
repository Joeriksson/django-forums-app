"""
Every text in a template is marked for translation: inside {% translate %} or
{% blocktranslate %}. What is left of a template without its tags must have no words.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / 'templates'
# The folders done so far; the rest follow
FOLDERS = ['forums']

# Attributes whose value a member reads or hears
TEXT_ATTRIBUTES = ('title', 'aria-label', 'placeholder', 'alt')


def template_files():
    return sorted(
        str(path.relative_to(TEMPLATES))
        for folder in FOLDERS
        for path in (TEMPLATES / folder).rglob('*.html')
    )


def without_template_code(source):
    """The template with its comments, translated blocks, tags and variables taken out."""
    source = re.sub(r'\{% comment %\}.*?\{% endcomment %\}', '', source, flags=re.S)
    source = re.sub(r'\{#.*?#\}', '', source)
    source = re.sub(r'\{% blocktranslate\b.*?\{% endblocktranslate %\}', '', source, flags=re.S)
    source = re.sub(r'\{%.*?%\}', '', source, flags=re.S)
    return re.sub(r'\{\{.*?\}\}', '', source, flags=re.S)


def unmarked_texts(source):
    html = without_template_code(source)
    found = []
    for attribute in TEXT_ATTRIBUTES:
        found += re.findall(rf'\s{attribute}="([^"]*[^\W\d_][^"]*)"', html)
    text = re.sub(r'<[^>]*>', '\n', html)
    found += [line.strip() for line in text.splitlines() if re.search(r'[^\W\d_]', line)]
    return found


@pytest.mark.parametrize('name', template_files())
def test_template_has_no_unmarked_text(name):
    assert unmarked_texts((TEMPLATES / name).read_text()) == []


@pytest.mark.parametrize(
    'source, expected',
    [
        ('<p>Hello</p>', ['Hello']),
        ('<p>{% translate "Hello" %}</p>', []),
        ('<p>{% blocktranslate %}Hello {{ name }}{% endblocktranslate %}</p>', []),
        ('<a title="Open it" href="/x/">{{ title }}</a>', ['Open it']),
        ('<nav aria-label="{% translate \'Pages\' %}"></nav>', []),
        ('<button class="button" type="submit">+1</button> · #{{ number }}', []),
        ('{# A note #}{% comment %}More notes{% endcomment %}<p>{{ text }}</p>', []),
    ],
)
def test_unmarked_texts(source, expected):
    assert unmarked_texts(source) == expected
