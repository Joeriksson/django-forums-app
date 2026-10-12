from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Message, Report


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['text']


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['note']
        widgets = {'note': forms.Textarea(attrs={'rows': 3})}


class MemberSearchForm(forms.Form):
    """Who to write to (MemberList): part of a name, or a member number."""

    q = forms.CharField(
        label=_('Name'),
        required=False,
        max_length=100,
        help_text=_('Part of a name, or a member number.'),
    )
