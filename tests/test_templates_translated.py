"""
Every text in a template is marked for translation: inside {% translate %} or
{% blocktranslate %}. What is left of a template without its tags must have no words.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / 'templates'
# Pages and mails
PATTERNS = ('*.html', '*.txt')

# Blocks that hold something other than text: main_class is a class name on <main>
NOT_TEXT_BLOCKS = ('main_class',)

# Attributes whose value a member reads or hears
TEXT_ATTRIBUTES = ('title', 'aria-label', 'placeholder', 'alt')


def template_files():
    return sorted(
        str(path.relative_to(TEMPLATES))
        for pattern in PATTERNS
        for path in TEMPLATES.rglob(pattern)
    )


def without_template_code(source):
    """The template with its comments, translated blocks, tags and variables taken out."""
    source = re.sub(r'\{% comment %\}.*?\{% endcomment %\}', '', source, flags=re.S)
    source = re.sub(r'\{#.*?#\}', '', source)
    for block in NOT_TEXT_BLOCKS:
        source = re.sub(rf'\{{% block {block} %\}}.*?\{{% endblock {block} %\}}', '', source, flags=re.S)
    source = re.sub(r'\{% blocktrans(late)?\b.*?\{% endblocktrans(late)? %\}', '', source, flags=re.S)
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
        ('{% block main_class %} site-main--account{% endblock main_class %}', []),
        ('{% blocktrans with name=user.name %}Hi {{ name }}{% endblocktrans %}', []),
    ],
)
def test_unmarked_texts(source, expected):
    assert unmarked_texts(source) == expected
