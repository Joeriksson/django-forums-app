"""
The texts our scripts show are translated by the template that loads the script and passed
as data- attributes on its tag. The tests don't run JavaScript: they check that every
text a script reads is passed, so a button can't end up without its label.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

SCRIPTS = Path(settings.BASE_DIR) / 'static' / 'js'


def texts_read_by(script):
    """The data- attributes a script reads from its tag: text.notCopied -> data-not-copied."""
    source = (SCRIPTS / script).read_text()
    keys = set(re.findall(r'\btext\.(\w+)', source))
    return {'data-' + re.sub(r'[A-Z]', lambda match: '-' + match.group(0).lower(), key) for key in keys}


def texts_passed_to(script, html):
    """The data- attributes with a value on the tag that loads the script."""
    tag = re.search(rf'<script src="[^"]*{re.escape(script)}"[^>]*>', html).group(0)
    return set(re.findall(r'(data-[a-z-]+)="[^"]+"', tag))


@pytest.fixture
def thread(reader, add_forum, add_thread):
    return add_thread('A thread', 'Text', add_forum('General', 'Everything'), reader)


@pytest.mark.parametrize(
    'script, url_name, count',
    [('editor.js', 'thread_add', 14), ('editor.js', 'thread_update', 14), ('editor.js', 'post_add', 14)],
)
def test_editor_gets_its_texts(client, reader, thread, script, url_name, count):
    client.force_login(reader)
    pk = thread.forum_id if url_name == 'thread_add' else thread.pk

    html = client.get(reverse(url_name, args=[pk])).content.decode()

    read = texts_read_by(script)
    assert len(read) == count
    assert read <= texts_passed_to(script, html)


def test_thread_page_script_gets_its_texts(client, reader, thread):
    client.force_login(reader)

    html = client.get(reverse('thread_detail', args=[thread.pk])).content.decode()

    read = texts_read_by('thread.js')
    assert read == {'data-copy', 'data-copied', 'data-not-copied'}
    assert read <= texts_passed_to('thread.js', html)


# Quoted words that aren't texts: the name of a key
NOT_TEXTS = {'Escape'}


def test_scripts_have_no_texts_of_their_own():
    """A sentence or a capitalised word in quotes is a text for members: it belongs in the template."""
    for script in ('editor.js', 'thread.js', 'theme.js', 'menu.js', 'search.js', 'notifications.js'):
        source = re.sub(r'//.*', '', (SCRIPTS / script).read_text())
        quoted = set(re.findall(r"'([^'\n]*)'", source)) - NOT_TEXTS
        assert [text for text in quoted if re.match(r'[A-Z][a-z]+( |$|…)', text)] == [], script
