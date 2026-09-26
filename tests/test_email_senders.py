import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from forums.tasks import send_notifications_task

SENDER = 'forum@example.com'


@pytest.mark.django_db
def test_welcome_mail_uses_default_from_email(settings):
    settings.DEFAULT_FROM_EMAIL = SENDER

    get_user_model().objects.create_user(
        username='newuser', email='newuser@example.com', password='testpass123'
    )

    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == SENDER


def test_notification_mail_uses_default_from_email(settings):
    settings.DEFAULT_FROM_EMAIL = SENDER

    send_notifications_task(
        1, 'A thread', 'someone', 'http://example.com', ['subscriber@example.com']
    )

    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == SENDER
    assert mail.outbox[0].bcc == ['subscriber@example.com']
