from collections import Counter

from django import forms
from django.contrib.auth import get_user_model
from django.db import models

from .models import Forum, UserProfile


class SearchForm(forms.Form):
    """The search page: words, filters and the order of the results (forums/search.py)."""

    min_words_length = 3

    q = forms.CharField(
        label='Words',
        required=False,
        max_length=200,
        help_text='Use "quotes" for a phrase and -word to leave a word out.',
    )
    forum = forms.ModelChoiceField(
        queryset=Forum.objects.order_by('title', 'id'), required=False, empty_label='All forums'
    )
    author = forms.TypedChoiceField(label='Author', required=False, coerce=int, empty_value=None)
    since = forms.DateField(label='From', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    until = forms.DateField(label='To', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    kind = forms.ChoiceField(
        label='Search in',
        required=False,
        choices=[('all', 'Threads and replies'), ('threads', 'Threads'), ('replies', 'Replies')],
    )
    sort = forms.ChoiceField(
        label='Sort by', required=False, choices=[('best', 'Best match'), ('newest', 'Newest first')]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['author'].choices = [('', 'Anyone'), *author_choices()]
        # The forum's own title, not its __str__ ('Forum: ...')
        self.fields['forum'].label_from_instance = lambda forum: forum.title

    def has_filter(self):
        data = self.cleaned_data
        return bool(
            data.get('forum') or data.get('author') or data.get('since') or data.get('until')
            or data.get('kind') in ('threads', 'replies')
        )

    def clean(self):
        data = super().clean()
        since, until = data.get('since'), data.get('until')
        if since and until and until < since:
            self.add_error('until', 'The end date is before the start date.')
        words = data.get('q', '')
        if words and len(words) < self.min_words_length:
            self.add_error('q', f'Type at least {self.min_words_length} characters.')
        elif not words and not self.has_filter():
            self.add_error('q', f'Type at least {self.min_words_length} characters, or choose a filter.')
        return data


def author_choices():
    """Members by the name others see; members with the same name get their number too."""
    users = list(get_user_model().objects.filter(is_active=True).select_related('profile'))
    names = [user.display_name for user in users]
    counts = Counter(names)
    return sorted(
        (
            (user.pk, f'{name} (member {user.pk})' if counts[name] > 1 else name)
            for user, name in zip(users, names)
        ),
        key=lambda choice: choice[1].casefold(),
    )


def https_url_formfield(db_field, **kwargs):
    """A URL typed without a scheme ('example.com') becomes https, as in Django 6."""
    if isinstance(db_field, models.URLField):
        kwargs['assume_scheme'] = 'https'
    return db_field.formfield(**kwargs)


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        formfield_callback = https_url_formfield
        fields = (
            'first_name',
            'last_name',
            'bio',
            'location',
            'gender',
            'web_site',
            'github_url',
            'signature',
        )
