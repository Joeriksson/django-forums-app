import logging

from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from users.audit import log_event


class Command(BaseCommand):
    help = (
        "Remove a user's two-factor authentication (authenticator app and recovery codes), "
        'e.g. after a lost phone. The user then logs in with the password alone and sets it up again.'
    )

    def add_arguments(self, parser):
        parser.add_argument('email')

    def handle(self, *args, email, **options):
        try:
            user = get_user_model().objects.get(email__iexact=email)
        except get_user_model().DoesNotExist:
            raise CommandError(f'No user with the email address {email}')
        deleted, _ = Authenticator.objects.filter(user=user).delete()
        if deleted:
            # Deleting rows directly sends no allauth signal
            log_event('mfa_removed_by_command', level=logging.WARNING, user=user.pk, count=deleted)
            self.stdout.write(self.style.SUCCESS(f'Removed two-factor authentication for {user.email}'))
        else:
            self.stdout.write(f'{user.email} has no two-factor authentication')
