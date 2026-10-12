from django import forms

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
