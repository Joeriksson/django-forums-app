"""
The security log: who logged in, failed to, or changed a password or two-factor setting.

One line per event on the `security` logger, as `event key=value ...`, with the
user's id and the client's address. Never log passwords, codes, tokens or
invitation keys here.
"""

import logging

from allauth.account import signals as account_signals
from allauth.account.adapter import get_adapter
from allauth.mfa import signals as mfa_signals
from django.contrib.auth import signals as auth_signals
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver

logger = logging.getLogger('security')

MAX_TEXT_LENGTH = 100


def quoted(text):
    """Text that a visitor typed: cut short, and escaped so it can't start a line of its own."""
    return repr(str(text)[:MAX_TEXT_LENGTH])


def client_ip(request):
    # Management commands and some tests have no request
    if request is None:
        return None
    try:
        # Same address as allauth's rate limits use (ALLAUTH_TRUSTED_PROXY_COUNT)
        return get_adapter().get_client_ip(request)
    except PermissionDenied:
        return None


def log_event(event, request=None, level=logging.INFO, **fields):
    fields['ip'] = client_ip(request)
    details = ' '.join(f'{key}={value}' for key, value in fields.items() if value is not None)
    logger.log(level, '%s %s', event, details)


@receiver(auth_signals.user_logged_in, dispatch_uid='audit_login')
def log_login(request, user, **kwargs):
    log_event('login', request, user=user.pk)


@receiver(auth_signals.user_logged_out, dispatch_uid='audit_logout')
def log_logout(request, user, **kwargs):
    if user is not None:
        log_event('logout', request, user=user.pk)


@receiver(auth_signals.user_login_failed, dispatch_uid='audit_login_failed')
def log_login_failed(credentials, request=None, **kwargs):
    # Django has already masked the password
    address = credentials.get('email') or credentials.get('username') or ''
    log_event('login_failed', request, level=logging.WARNING, email=quoted(address))


@receiver(account_signals.user_signed_up, dispatch_uid='audit_signup')
def log_signup(request, user, **kwargs):
    log_event('signup', request, user=user.pk)


@receiver(account_signals.password_set, dispatch_uid='audit_password_set')
def log_password_set(request, user, **kwargs):
    log_event('password_set', request, user=user.pk)


@receiver(account_signals.password_changed, dispatch_uid='audit_password_changed')
def log_password_changed(request, user, **kwargs):
    log_event('password_changed', request, user=user.pk)


@receiver(account_signals.password_reset, dispatch_uid='audit_password_reset')
def log_password_reset(request, user, **kwargs):
    log_event('password_reset', request, user=user.pk)


@receiver(account_signals.email_changed, dispatch_uid='audit_email_changed')
def log_email_changed(request, user, **kwargs):
    log_event('email_changed', request, user=user.pk)


@receiver(mfa_signals.authenticator_added, dispatch_uid='audit_mfa_added')
def log_authenticator_added(request, user, authenticator, **kwargs):
    log_event('mfa_added', request, user=user.pk, type=authenticator.type)


@receiver(mfa_signals.authenticator_removed, dispatch_uid='audit_mfa_removed')
def log_authenticator_removed(request, user, authenticator, **kwargs):
    log_event('mfa_removed', request, level=logging.WARNING, user=user.pk, type=authenticator.type)


@receiver(mfa_signals.authenticator_reset, dispatch_uid='audit_mfa_reset')
def log_authenticator_reset(request, user, authenticator, **kwargs):
    log_event('mfa_reset', request, user=user.pk, type=authenticator.type)


@receiver(mfa_signals.authentication_failed, dispatch_uid='audit_mfa_failed')
def log_mfa_failed(request, user, **kwargs):
    log_event('mfa_failed', request, level=logging.WARNING, user=user.pk)
