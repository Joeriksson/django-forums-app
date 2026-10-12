from celery import shared_task
from django.conf import settings
from django.db.models import F
from django.urls import reverse
from django.utils.translation import gettext

from project.utils import send_mail, site_language


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_message_mail_task(message_id):
    """
    The mail about a direct message, queued to run some minutes after it (Site
    settings), by the rule for replies: it goes to the receiver if their notification
    for the conversation still starts at this message and is unread. Who has opened the
    conversation gets none, and the messages that follow send none either, until the
    member has been there. A link, never the message's text.
    """
    # The models import this module
    from conversations.models import Block, Message
    from notifications.models import Notification

    message = (
        Message.objects.select_related('conversation', 'sender__profile')
        .filter(pk=message_id)
        .first()
    )
    # Gone with an account while the mail waited
    if message is None:
        return

    receiver_id = message.conversation.other_id(message.sender_id)
    # Only to an active account, and only to an address its owner has confirmed
    email_addresses = list(
        Notification.objects.filter(
            user_id=receiver_id,
            message=message,
            read=False,
            user__is_active=True,
            user__emailaddress__verified=True,
            user__emailaddress__email__iexact=F('user__email'),
        )
        .values_list('user__email', flat=True)
        .distinct()
    )
    if not email_addresses:
        return
    # Blocked during the wait: the receiver wants nothing more from the sender
    if Block.objects.filter(blocker_id=receiver_id, blocked_id=message.sender_id).exists():
        return

    conversation_url = reverse('conversation', kwargs={'pk': message.sender_id})
    full_url = f'{settings.SITE_URL}{conversation_url}'

    # The site's language, also for "Member <id>": a worker has no other
    with site_language():
        name = message.sender.display_name
        subject = gettext('New message from %(name)s') % {'name': name}
        told = gettext('%(name)s has sent you a message.') % {'name': name}
        url = gettext('Url: %(url)s') % {'url': full_url}

    send_mail(subject, settings.DEFAULT_FROM_EMAIL, email_addresses, f'{told} \n\n{url} \n\n')
