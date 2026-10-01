from django import forms
from django.db import models

from .models import UserProfile


class SearchForm(forms.Form):
    q = forms.CharField(label='Search', max_length=200)


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
