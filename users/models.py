from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.mail import EmailMultiAlternatives

from django_lifecycle import LifecycleModelMixin, hook


class CustomUser(LifecycleModelMixin, AbstractUser):
    pass

    @hook('after_create')
    def send_welcome_mail(self):
        subject, from_email = 'Welcome to Wildvasa Forums', settings.DEFAULT_FROM_EMAIL

        to = (self.email,)

        text_content = 'Thank you for registering at Wildvasa forums'

        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email, to=to
        )

        msg.send()
