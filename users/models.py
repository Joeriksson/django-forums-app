from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

from django_lifecycle import AFTER_CREATE, LifecycleModelMixin, hook

from .tasks import send_welcome_email_task


class CustomUser(LifecycleModelMixin, AbstractUser):
    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        constraints = [
            # Email is the login, so it must be present and unique ignoring case.
            models.UniqueConstraint(Lower('email'), name='users_customuser_email_ci_unique'),
            models.CheckConstraint(
                check=~models.Q(email=''), name='users_customuser_email_not_empty'
            ),
        ]

    @hook(AFTER_CREATE, on_commit=True)
    def send_welcome_mail(self):
        # Runs only once the user is committed, so a rollback sends nothing.
        send_welcome_email_task.delay(self.email)
