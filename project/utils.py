import logging

from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def send_mail(subject, from_email, bcc, text_content):

    msg = EmailMultiAlternatives(
        subject=subject, body=text_content, from_email=from_email, bcc=bcc
    )

    msg.send()

    # The count only: addresses don't belong in the log
    logger.info('Mail sent to %d recipients', len(bcc))
