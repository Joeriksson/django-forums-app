"""
Texts are marked for translation. A text set when a module is imported (a field's name,
a choice, a form label) must be lazy: translated when shown, not once at import.
"""

from datetime import timedelta

import pytest
from django.utils import timezone, translation
from django.utils.functional import Promise

from forums.forms import SearchForm
from forums.models import MARKDOWN_HELP, Forum, Gender, Post, Posting, Thread, UserProfile
from forums.templatetags.when import when
from forums.views import PostCreate, ThreadCreate

FORM_FIELDS = {
    Forum: ['title', 'description', 'posting'],
    Thread: ['title', 'text', 'announcement'],
    Post: ['text'],
    UserProfile: [
        'first_name', 'last_name', 'bio', 'location', 'gender', 'web_site', 'github_url', 'signature',
    ],
}


@pytest.mark.parametrize(
    'model, name', [(model, name) for model, names in FORM_FIELDS.items() for name in names]
)
def test_form_field_names_are_lazy(model, name):
    field = model._meta.get_field(name)

    assert isinstance(field.verbose_name, Promise)
    if field.help_text:
        assert isinstance(field.help_text, Promise)


def test_markdown_help_is_lazy():
    assert isinstance(MARKDOWN_HELP, Promise)


@pytest.mark.parametrize('choices', [Posting, Gender])
def test_choice_labels_are_lazy(choices):
    assert all(isinstance(member._label_, Promise) for member in choices)


def test_search_form_texts_are_lazy():
    for name, field in SearchForm.base_fields.items():
        if name == 'forum':
            assert isinstance(field.empty_label, Promise)
        else:
            assert isinstance(field.label, Promise), name
        for _, label in getattr(field, '_choices', None) or []:
            assert isinstance(label, Promise), name
    assert isinstance(SearchForm.base_fields['q'].help_text, Promise)


@pytest.mark.parametrize('view', [ThreadCreate, PostCreate])
def test_success_messages_are_lazy(view):
    assert isinstance(view.success_message, Promise)


@pytest.fixture
def marked(monkeypatch):
    """Stands in for a catalog: every translated text comes back in brackets."""
    monkeypatch.setattr(translation._trans, 'gettext', lambda message: f'[{message}]', raising=False)
    monkeypatch.setattr(
        translation._trans,
        'ngettext',
        lambda singular, plural, number: f'[{singular if number == 1 else plural}]',
        raising=False,
    )


@pytest.mark.parametrize(
    'age, expected',
    [
        (timedelta(seconds=5), '[just now]'),
        (timedelta(minutes=1), '[1 minute ago]'),
        (timedelta(minutes=5), '[5 minutes ago]'),
        (timedelta(hours=1), '[1 hour ago]'),
        (timedelta(hours=3), '[3 hours ago]'),
        (timedelta(days=1), '[yesterday]'),
        (timedelta(days=4), '[4 days ago]'),
    ],
)
def test_when_is_translated(marked, age, expected):
    now = timezone.now()

    assert when(now - age, now) == expected


@pytest.mark.django_db
def test_member_number_name_is_translated(marked, add_user):
    user = add_user('nameless', 'nameless@example.com', 'testpass123')

    assert user.display_name == f'[Member {user.pk}]'


def test_lazy_texts_follow_the_language_when_shown(marked):
    assert str(Posting.MODERATORS_ONLY.label) == '[Moderators only: members can read]'
    assert str(Forum._meta.get_field('title').verbose_name) == '[title]'


@pytest.mark.django_db
def test_closed_forum_note_is_translated(marked, add_forum):
    forum = add_forum('News', 'From the moderators')
    forum.posting = Posting.MODERATORS_ONLY

    assert forum.posting_note == '[Only moderators can post here.]'
