import logging
import time

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import translation
from kombu.exceptions import OperationalError

logger = logging.getLogger(__name__)


class UTCFormatter(logging.Formatter):
    """Log timestamps in UTC, whatever TIME_ZONE the pages show."""

    converter = time.gmtime


def site_language():
    """
    Context manager for texts that aren't for the one making the request, such as mails:
    the site's language (LANGUAGE_CODE). A Celery worker has it anyway; in development
    tasks run inside the request, in the language its visitor chose.
    """
    return translation.override(settings.LANGUAGE_CODE)


def send_mail(subject, from_email, bcc, text_content):

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, bcc=bcc
    )

    msg.send()

    # The count only: addresses don't belong in the log
    logger.info('Mail sent to %d recipients', len(bcc))


def queue_task(task, *args, countdown=None):
    """
    Queue a Celery task whose failure mustn't fail the request: the post, user or
    invitation is already saved, and a 500 would make the user try again.
    `countdown` makes the worker wait that many seconds before it runs the task.
    """
    try:
        if countdown is None:
            task.delay(*args)
        else:
            task.apply_async(args, countdown=countdown)
    except OperationalError:
        # The broker (Redis) is unreachable. Logged as an error, so ADMINS get a mail.
        # Without the arguments: they can hold email addresses
        logger.exception('Could not queue %s: the mail is not sent', task.name)
