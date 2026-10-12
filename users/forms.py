from allauth.account.forms import SignupForm
from allauth.core import context as allauth_context
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.utils.text import capfirst
from django.utils.translation import gettext, gettext_lazy

from forums.models import UserProfile

from .models import Invitation
from .security import has_second_factor


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
    # Any of these makes the account more than a member (users.security.is_privileged)
    RIGHTS_FIELDS = ('is_staff', 'is_superuser', 'groups', 'user_permissions')

    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = ('email', 'username',)

    def clean(self):
        cleaned_data = super().clean()
        # Whoever logs in to an account without an authenticator app gets to set one up,
        # so rights given before that would be open to anyone with the password.
        if (
            settings.STAFF_REQUIRE_MFA
            and any(cleaned_data.get(field) for field in self.RIGHTS_FIELDS)
            and not has_second_factor(self.instance)
        ):
            raise forms.ValidationError(
                'This account has no authenticator app. It must set up two-factor '
                'authentication before it can get staff status, a group or a permission.'
            )
        return cleaned_data


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


def name_field(name, required, help_text=''):
    """A signup field for one of the profile's names, with its label and length."""
    field = UserProfile._meta.get_field(name)
    return forms.CharField(
        label=capfirst(field.verbose_name),
        max_length=field.max_length,
        required=required,
        help_text=help_text,
    )


class InvitedSignupForm(SignupForm):
    """
    allauth's signup form (ACCOUNT_FORMS), with the name others will see: a member has
    one from the start, instead of "Member <id>". With an invitation, the address is fixed.
    """

    first_name = name_field(
        'first_name',
        required=True,
        # The same line as on the profile page
        help_text=gettext_lazy('Others see your first and last name next to what you write.'),
    )
    last_name = name_field('last_name', required=False)
    field_order = ['email', 'first_name', 'last_name', 'password1']

    def custom_signup(self, request, user):
        super().custom_signup(request, user)
        # The profile was made when the user was saved (forums/signals.py)
        profile = user.profile
        profile.first_name = self.cleaned_data['first_name']
        profile.last_name = self.cleaned_data['last_name']
        profile.save(update_fields=['first_name', 'last_name'])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = allauth_context.request
        # While signup is closed, only the invited address is accepted
        # (AccountAdapter.clean_email): don't offer to change it. The check there is the
        # guard; a read-only field is still posted and can be changed by hand.
        if request and not settings.SIGNUP_OPEN and Invitation.from_session(request):
            email = self.fields['email']
            email.widget.attrs['readonly'] = True
            email.help_text = gettext('Your invitation is for this address.')
