import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction

from forums.tasks import send_notifications_task

SENDER = 'forum@example.com'


@pytest.mark.django_db
def test_welcome_mail_uses_default_from_email(
    settings, django_capture_on_commit_callbacks
):
    settings.DEFAULT_FROM_EMAIL = SENDER

    with django_capture_on_commit_callbacks(execute=True):
        get_user_model().objects.create_user(
            username='newuser', email='newuser@example.com', password='testpass123'
        )

    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == SENDER
    assert mail.outbox[0].to == ['newuser@example.com']


@pytest.mark.django_db
def test_welcome_mail_not_sent_before_commit(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks() as callbacks:
        get_user_model().objects.create_user(
            username='newuser', email='newuser@example.com', password='testpass123'
        )
        # The user is saved but the transaction hasn't committed yet.
        assert len(mail.outbox) == 0

    for callback in callbacks:
        callback()
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_welcome_mail_not_sent_when_creation_is_rolled_back():
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            get_user_model().objects.create_user(
                username='newuser', email='newuser@example.com', password='testpass123'
            )
            raise RuntimeError('something later in the request failed')

    assert not get_user_model().objects.filter(username='newuser').exists()
    assert len(mail.outbox) == 0


def test_notification_mail_uses_default_from_email(settings):
    settings.DEFAULT_FROM_EMAIL = SENDER

    send_notifications_task(
        1, 'A thread', 'someone', 'http://example.com', ['subscriber@example.com']
    )

    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == SENDER
    assert mail.outbox[0].bcc == ['subscriber@example.com']
