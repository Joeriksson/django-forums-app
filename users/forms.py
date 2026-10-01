from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from .models import Invitation


class UniqueEmailMixin:
    def clean_email(self):
        # Same rule as the database constraint, but shown on the email field.
        email = self.cleaned_data['email']
        others = get_user_model().objects.exclude(pk=self.instance.pk)
        if others.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with that email already exists.')
        return email


class CustomUserCreationForm(UniqueEmailMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('email', 'username',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Login is email-only, so ask for it like any required field.
        self.fields['email'].required = True


class CustomUserChangeForm(UniqueEmailMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = ('email', 'username',)


class InvitationAdminForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = ('email',)

    def clean_email(self):
        email = self.cleaned_data['email']
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('This address already has an account.')
        if Invitation.objects.valid().filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'This address already has a pending invitation. '
                'Use "Resend invitation" in the list instead.'
            )
        return email
