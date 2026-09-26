from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_welcome_email_task(email):
    subject, from_email = 'Welcome to Wildvasa Forums', settings.DEFAULT_FROM_EMAIL

    to = (email,)

    text_content = 'Thank you for registering at Wildvasa forums'

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, to=to
    )

    msg.send()
