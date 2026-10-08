import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction

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


@pytest.mark.django_db
def test_notification_mail_uses_default_from_email(settings, verify_email, reply_with_mail):
    from forums.models import Forum, Subscription, Thread

    settings.DEFAULT_FROM_EMAIL = SENDER
    users = get_user_model().objects
    author = users.create_user(username='author', email='author@example.com', password='testpass123')
    subscriber = verify_email(
        users.create_user(username='subscriber', email='subscriber@example.com', password='testpass123')
    )
    forum = Forum.objects.create(title='General', description='Everything')
    thread = Thread.objects.create(title='A thread', text='Text', forum=forum, user=author)
    Subscription.objects.create(thread=thread, user=subscriber)

    reply_with_mail(thread, author)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == SENDER
    assert mail.outbox[0].bcc == ['subscriber@example.com']
