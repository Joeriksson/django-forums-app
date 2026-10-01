import secrets
from datetime import timedelta

from allauth.account.signals import user_signed_up
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from django_lifecycle import AFTER_CREATE, LifecycleModelMixin, hook

from .tasks import send_welcome_email_task


class CustomUser(LifecycleModelMixin, AbstractUser):
    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        constraints = [
            # Email is the login, so it must be present and unique ignoring case.
            models.UniqueConstraint(Lower('email'), name='users_customuser_email_ci_unique'),
            models.CheckConstraint(
                condition=~models.Q(email=''), name='users_customuser_email_not_empty'
            ),
        ]

    @hook(AFTER_CREATE, on_commit=True)
    def send_welcome_mail(self):
        # Runs only once the user is committed, so a rollback sends nothing.
        send_welcome_email_task.delay(self.email)


def new_invitation_key():
    return secrets.token_urlsafe(32)


class InvitationQuerySet(models.QuerySet):
    def valid(self):
        """Not used yet, and created within the last INVITATION_EXPIRY_DAYS."""
        cutoff = timezone.now() - timedelta(days=settings.INVITATION_EXPIRY_DAYS)
        return self.filter(accepted_at__isnull=True, created__gt=cutoff)


class Invitation(models.Model):
    """Lets one email address sign up while signup is closed."""

    # Session key holding the accepted link's key until the signup is done
    SESSION_KEY = 'invitation_key'

    email = models.EmailField()
    key = models.CharField(max_length=64, unique=True, default=new_invitation_key, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='invitations_sent',
    )
    # When the link was made; the expiry counts from here
    created = models.DateTimeField(default=timezone.now)
    # When the invitation email went out; empty if it hasn't (yet)
    sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    objects = InvitationQuerySet.as_manager()

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return self.email

    def is_valid(self):
        # Same rule as InvitationQuerySet.valid(), without a query
        return self.accepted_at is None and self.expires_at > timezone.now()

    @property
    def expires_at(self):
        return self.created + timedelta(days=settings.INVITATION_EXPIRY_DAYS)

    def get_link(self):
        return settings.SITE_URL + reverse('accept_invitation', args=[self.key])

    def renew(self):
        """Replace the link with a new one, valid for the full expiry time again."""
        self.key = new_invitation_key()
        self.created = timezone.now()
        self.sent_at = None
        self.save(update_fields=['key', 'created', 'sent_at'])

    @classmethod
    def from_session(cls, request):
        """The valid invitation whose link this visitor opened, or None."""
        key = request.session.get(cls.SESSION_KEY)
        return cls.objects.valid().filter(key=key).first() if key else None


@receiver(user_signed_up)
def accept_invitation_on_signup(request, user, **kwargs):
    """Mark the invitation used once its signup (email or GitHub) has created the user."""
    invitation = Invitation.from_session(request)
    if invitation is not None:
        Invitation.objects.filter(pk=invitation.pk, accepted_at__isnull=True).update(
            accepted_at=timezone.now(), accepted_by=user
        )
    request.session.pop(Invitation.SESSION_KEY, None)
