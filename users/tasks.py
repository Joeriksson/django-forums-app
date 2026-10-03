from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from pages.models import SiteSettings


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_welcome_email_task(email):
    title = SiteSettings.load().title
    subject, from_email = f'Welcome to {title}', settings.DEFAULT_FROM_EMAIL

    to = (email,)

    text_content = f'Thank you for registering at {title}'

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, to=to
    )

    msg.send()


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_invitation_email_task(invitation_id):
    # Imported here: users.models imports this module
    from .models import Invitation

    # Used, expired or deleted since it was queued: nothing to send
    invitation = Invitation.objects.valid().filter(pk=invitation_id).first()
    if invitation is None:
        return

    context = {
        'link': invitation.get_link(),
        'expires_at': invitation.expires_at,
        'title': SiteSettings.load().title,
    }
    msg = EmailMultiAlternatives(
        subject=render_to_string('users/invitation_email_subject.txt', context).strip(),
        body=render_to_string('users/invitation_email_message.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=(invitation.email,),
    )
    msg.send()
    Invitation.objects.filter(pk=invitation.pk).update(sent_at=timezone.now())
