from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Post, Notification


@receiver(post_save, sender=Post, dispatch_uid="notify_thread_subscribers")
def send_notification(sender, created, **kwargs):
    # TODO: Look into how to send multiple mails via header instead of BCC
    if created:
        obj = kwargs['instance']

        # Check which users has subscribed to the thread which was posted to
        notification_users = Notification.objects.filter(thread=obj.thread)

        # Compose message to subscribers
        subject, from_email = f'New post added by {obj.user.username}', 'info@email.com'

        bcc = []

        for notification_user in notification_users:
            bcc.append(notification_user.user.email)

        text_content = f'A new post was added to thread "{obj.thread.title}" \n'

        msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, bcc=bcc)

        msg.send()
