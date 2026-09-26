from django.contrib.auth.models import AbstractUser

from django_lifecycle import AFTER_CREATE, LifecycleModelMixin, hook

from .tasks import send_welcome_email_task


class CustomUser(LifecycleModelMixin, AbstractUser):
    pass

    @hook(AFTER_CREATE, on_commit=True)
    def send_welcome_mail(self):
        # Runs only once the user is committed, so a rollback sends nothing.
        if self.email:
            send_welcome_email_task.delay(self.email)
