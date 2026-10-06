"""
Mails that aren't an answer to the one making the request are in the site's language,
also when that request runs in another language (in development the tasks run inside it).
"""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone, translation

from forums.models import Notification, Post
from forums.tasks import send_notifications_task
from users.models import Invitation
from users.tasks import send_invitation_email_task, send_welcome_email_task


@pytest.fixture
def tagged(monkeypatch):
    """Stands in for a catalog: every translated text starts with the language it was made in."""
    monkeypatch.setattr(
        translation._trans,
        'gettext',
        lambda message: f'<{translation.get_language()}>{message}',
        raising=False,
    )


@pytest.mark.django_db
def test_welcome_mail_is_in_the_site_language(tagged):
    with translation.override('sv'):
        send_welcome_email_task('new@example.com')

    message = mail.outbox[0]
    assert message.subject.startswith('<en>Welcome to ')
    assert message.body.startswith('<en>Thank you for registering at ')


def test_notification_mail_is_in_the_site_language(tagged):
    with translation.override('sv'):
        send_notifications_task(1, 'A thread', 'Anna Berg', 'https://forum.example.com/t/1', ['a@example.com'])

    message = mail.outbox[0]
    assert message.subject == '<en>New post added by Anna Berg'
    assert '<en>A new post was added to thread "A thread"' in message.body
    assert '<en>Url: https://forum.example.com/t/1' in message.body


@pytest.mark.django_db
def test_notification_mail_follows_a_swedish_site(tagged, settings):
    settings.LANGUAGE_CODE = 'sv'

    send_notifications_task(1, 'A thread', 'Anna Berg', 'https://forum.example.com/t/1', ['a@example.com'])

    assert mail.outbox[0].subject == '<sv>New post added by Anna Berg'


@pytest.mark.django_db
def test_notification_names_a_member_without_a_name_in_the_site_language(
    tagged, notification_calls, verify_email, django_capture_on_commit_callbacks
):
    from forums.models import Forum, Thread

    users = get_user_model().objects
    author = users.create_user(username='author', email='author@example.com', password='pass12345')
    subscriber = verify_email(
        users.create_user(username='subscriber', email='subscriber@example.com', password='pass12345')
    )
    forum = Forum.objects.create(title='General', description='Everything')
    thread = Thread.objects.create(title='A thread', text='Text', forum=forum, user=author)
    Notification.objects.create(thread=thread, user=subscriber)

    with translation.override('sv'), django_capture_on_commit_callbacks(execute=True):
        Post.objects.create(text='A reply', thread=thread, user=author)

    assert notification_calls[0][2] == f'<en>Member {author.pk}'


@pytest.mark.django_db
def test_invitation_mail_is_in_the_site_language(tagged):
    invitation = Invitation.objects.create(email='anna@example.com')

    with translation.override('sv'):
        send_invitation_email_task(invitation.pk)

    message = mail.outbox[0]
    assert message.subject.startswith("<en>You're invited to ")
    assert '<en>Hello,' in message.body
    assert '<sv>' not in message.subject + message.body
    # The date too: Django's own month names, which need no catalog of ours
    month = timezone.localtime(invitation.expires_at).strftime('%B')
    assert month in message.body


@pytest.mark.django_db
def test_invitation_mail_reads_as_before():
    invitation = Invitation.objects.create(email='anna@example.com')

    send_invitation_email_task(invitation.pk)

    message = mail.outbox[0]
    assert message.subject == "You're invited to Wildvasa"
    assert message.body.startswith("Hello,\n\nYou're invited to join Wildvasa. Use this link to create your account:\n\n")
    assert f'\n\n{invitation.get_link()}\n\nThe link works once, for this email address only, until ' in message.body
    assert message.body.endswith(".\n\nIf you weren't expecting this invitation, you can ignore this email.\n")
