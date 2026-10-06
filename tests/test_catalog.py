"""
The Swedish catalog (locale/sv/LC_MESSAGES): django.po holds the texts, django.mo is what
Django reads. Both are committed, so these tests keep them complete and in step:
`make messages` after a new text, `make compile_messages` after a change to django.po.
"""

import ast
import gettext
import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import templatize

from forums.templatetags.when import when

BASE = Path(settings.BASE_DIR)
CATALOG = BASE / 'locale' / 'sv' / 'LC_MESSAGES'
# Where texts are marked: our apps' code and the templates
CODE = ['api', 'forums', 'pages', 'project', 'users']
MARKERS = {'gettext', 'gettext_lazy', 'ngettext', 'ngettext_lazy', '_'}


def read_po():
    """The entries of django.po: msgid (a pair for a plural), the translations, fuzzy or not."""
    entries, entry, field = [], None, None
    for line in (CATALOG / 'django.po').read_text().splitlines() + ['']:
        if not line.strip():
            if entry and 'msgid' in entry:
                entries.append(entry)
            entry, field = None, None
            continue
        entry = entry if entry is not None else {'fuzzy': False, 'obsolete': False, 'msgstr': {}}
        if line.startswith('#~'):
            entry['obsolete'] = True
        elif line.startswith('#,'):
            entry['fuzzy'] = 'fuzzy' in line
        elif line.startswith('#'):
            continue
        elif line.startswith('"'):
            add(entry, field, json.loads(line))
        else:
            field, text = line.split(' ', 1)
            add(entry, field, json.loads(text))
    return [entry for entry in entries if entry['msgid'] != '']


def add(entry, field, text):
    index = re.fullmatch(r'msgstr(?:\[(\d+)\])?', field)
    if index:
        number = int(index.group(1) or 0)
        entry['msgstr'][number] = entry['msgstr'].get(number, '') + text
    else:
        entry[field] = entry.get(field, '') + text


def key(entry):
    return (entry['msgid'], entry['msgid_plural']) if 'msgid_plural' in entry else entry['msgid']


def texts_in_code():
    """The texts marked in Python: the literal arguments of the gettext functions."""
    found = set()
    for folder in CODE:
        for path in (BASE / folder).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, 'id', getattr(node.func, 'attr', None))
                if name not in MARKERS or not node.args:
                    continue
                texts = [arg.value for arg in node.args[:2] if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
                if name.startswith('ngettext') and len(texts) == 2:
                    found.add(tuple(texts))
                elif texts:
                    found.add(texts[0])
    return found


# A Python string in either kind of quotes, as templatize writes them
QUOTED = r"""u?('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""


def texts_in_templates():
    """The texts marked in templates, as Django's makemessages sees them."""
    found = set()
    for pattern in ('*.html', '*.txt'):
        for path in (BASE / 'templates').rglob(pattern):
            source = templatize(path.read_text())
            for singular, plural in re.findall(rf'\bngettext\({QUOTED}, {QUOTED}', source):
                found.add((ast.literal_eval(singular), ast.literal_eval(plural)))
            for text in re.findall(rf'(?<![n\w])gettext\({QUOTED}\)', source):
                found.add(ast.literal_eval(text))
    return found


def test_every_marked_text_is_in_the_catalog():
    marked = texts_in_code() | texts_in_templates()
    catalog = {key(entry) for entry in read_po() if not entry['obsolete']}

    assert len(marked) > 150
    assert marked - catalog == set(), 'run make messages, translate, then make compile_messages'
    assert catalog - marked == set(), 'texts no longer used: run make messages'


def test_every_text_is_translated():
    entries = read_po()

    assert [key(entry) for entry in entries if entry['obsolete']] == []
    assert [key(entry) for entry in entries if entry['fuzzy']] == []
    assert [key(entry) for entry in entries if not all(entry['msgstr'].values())] == []
    assert [key(entry) for entry in entries if 'msgid_plural' in entry and len(entry['msgstr']) != 2] == []


def parts(text, pattern):
    return sorted(re.findall(pattern, text))


@pytest.mark.parametrize(
    'what, pattern',
    [
        # A missing or misspelt value makes the page fail when the text is shown
        ('values', r'%\(\w+\)s'),
        ('tags', r'</?\w+[^>]*>'),
        ('line breaks at the ends', r'^\n|\n$'),
    ],
)
def test_translations_keep_the_parts_of_the_text(what, pattern):
    wrong = []
    for entry in read_po():
        sources = [entry['msgid'], entry.get('msgid_plural', entry['msgid'])]
        for number, translation_ in entry['msgstr'].items():
            if parts(translation_, pattern) != parts(sources[min(number, 1)], pattern):
                wrong.append(translation_)

    assert wrong == [], what


def test_compiled_catalog_matches_the_texts():
    with open(CATALOG / 'django.mo', 'rb') as file:
        compiled = dict(gettext.GNUTranslations(file)._catalog)
    compiled.pop('')

    expected = {}
    for entry in read_po():
        if 'msgid_plural' in entry:
            expected.update({(entry['msgid'], number): text for number, text in entry['msgstr'].items()})
        else:
            expected[entry['msgid']] = entry['msgstr'][0]

    assert compiled == expected, 'run make compile_messages'


@pytest.mark.django_db
def test_visitors_home_page_in_swedish(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'

    html = client.get(reverse('home')).content.decode()

    assert '<html lang="sv">' in html
    assert '>Logga in</a>' in html
    # The tagline is the site's own text (Site settings), not ours to translate
    assert '>Sign in</a>' not in html


@pytest.mark.django_db
def test_forum_list_in_swedish(client, django_user_model):
    from forums.models import Forum, Thread

    member = django_user_model.objects.create_user(username='member', email='member@example.com', password='pass12345')
    forum = Forum.objects.create(title='General', description='Everything')
    Thread.objects.create(title='A thread', text='Text', forum=forum, user=member)
    client.force_login(member)
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'

    html = client.get(reverse('home')).content.decode()

    assert '<strong>1</strong> tråd' in html
    assert '<strong>0</strong> svar' in html
    assert f'Medlem {member.pk}' in html
    assert 'Senaste aktivitet' in html


@pytest.mark.parametrize(
    'minutes, expected',
    [(0, 'nyss'), (1, 'för 1 minut sedan'), (5, 'för 5 minuter sedan'), (60, 'för 1 timme sedan'),
     (180, 'för 3 timmar sedan'), (60 * 24, 'i går'), (60 * 24 * 4, 'för 4 dagar sedan')],
)
def test_when_in_swedish(minutes, expected):
    now = timezone.now()

    with translation.override('sv'):
        assert when(now - timezone.timedelta(minutes=minutes), now) == expected


@pytest.mark.django_db
def test_site_language_swedish_without_a_cookie(client, settings):
    settings.LANGUAGE_CODE = 'sv'

    html = client.get(reverse('home')).content.decode()

    assert 'Logga in' in html
