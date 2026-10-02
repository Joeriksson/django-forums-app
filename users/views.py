import logging

from allauth.account.adapter import get_adapter
from django.shortcuts import redirect, render

from .audit import log_event
from .models import Invitation


def accept_invitation(request, key):
    """Open signup for the invited address, then continue on the signup page."""
    if request.user.is_authenticated:
        return redirect('home')
    invitation = Invitation.objects.valid().filter(key=key).first()
    if invitation is None:
        # Without the key: an expired one may be renewed, and a guess may be close
        log_event('invitation_refused', request, level=logging.WARNING)
        return render(request, 'account/invitation_invalid.html', status=404)
    request.session[Invitation.SESSION_KEY] = invitation.key
    # Pre-fills the signup form and marks the address as verified: the link proved it
    get_adapter(request).stash_verified_email(request, invitation.email)
    return redirect('account_signup')
