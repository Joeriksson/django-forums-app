from django.contrib.auth.models import AbstractUser
from django.core.mail import EmailMultiAlternatives

from django_lifecycle import LifecycleModelMixin, hook


class CustomUser(LifecycleModelMixin, AbstractUser):
    pass

    @hook('after_create')
    def send_welcome_mail(self):
        subject, from_email = f'Welcome to Wildvasa Forums', 'info@wildvasa.com'

        to = (self.email,)

        text_content = f'Thank you for registering at Wildvasa forums'

        msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, to=to)

        msg.send()
