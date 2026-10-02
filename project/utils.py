import logging

from django.core.mail import EmailMultiAlternatives
from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)


def send_mail(subject, from_email, bcc, text_content):

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, bcc=bcc
    )

    msg.send()

    # The count only: addresses don't belong in the log
    logger.info('Mail sent to %d recipients', len(bcc))


def queue_task(task, *args):
    """
    Queue a Celery task whose failure mustn't fail the request: the post, user or
    invitation is already saved, and a 500 would make the user try again.
    """
    try:
        task.delay(*args)
    except OperationalError:
        # The broker (Redis) is unreachable. Logged as an error, so ADMINS get a mail.
        # Without the arguments: they can hold email addresses
        logger.exception('Could not queue %s: the mail is not sent', task.name)
