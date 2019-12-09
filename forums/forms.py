from django import forms

from .models import UserProfile


class SearchForm(forms.Form):
    q = forms.CharField(label='Search', max_length=200)


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
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
