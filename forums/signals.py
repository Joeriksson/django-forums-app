from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver

from users.models import CustomUser
from .models import Post, Notification, UserProfile


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
            # add users to bcc unless it is the user who created the post
            if not notification_user == obj.user:
                bcc.append(notification_user.user.email)

        text_content = f'A new post was added to thread "{obj.thread.title}" \n'

        msg = EmailMultiAlternatives(subject=subject, body=text_content, from_email=from_email, bcc=bcc)

        msg.send()


@receiver(post_save, sender=CustomUser, dispatch_uid="create_user_profile")
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=get_user_model(), dispatch_uid="save_user_profile")
def save_user_profile(sender, instance, **kwargs):
    user_profile = UserProfile.objects.filter(user=instance)
    if not user_profile:
        UserProfile.objects.create(user=instance)
    instance.profile.save()
