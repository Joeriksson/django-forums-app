"""
Mails that aren't an answer to the one making the request are in the site's language,
also when that request runs in another language (in development the tasks run inside it).
"""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone, translation

from forums.models import Subscription
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


@pytest.fixture
def reply(db, verify_email):
    """A reply by a member without a profile name, in a thread with a subscriber."""
    from forums.models import Forum, Thread

    users = get_user_model().objects
    author = users.create_user(username='author', email='author@example.com', password='pass12345')
    subscriber = verify_email(
        users.create_user(username='subscriber', email='subscriber@example.com', password='pass12345')
    )
    forum = Forum.objects.create(title='General', description='Everything')
    thread = Thread.objects.create(title='A thread', text='Text', forum=forum, user=author)
    Subscription.objects.create(thread=thread, user=subscriber)
    return thread, author


def test_notification_mail_is_in_the_site_language(tagged, reply, reply_with_mail, settings):
    settings.SITE_URL = 'https://forum.example.com'
    thread, author = reply

    # In development the task runs inside the request, in its visitor's language
    with translation.override('sv'):
        post = reply_with_mail(thread, author)

    message = mail.outbox[0]
    # "Member <id>" is a text too
    assert message.subject == f'<en>New post added by <en>Member {author.pk}'
    assert '<en>A new post was added to thread "A thread"' in message.body
    assert f'<en>Url: https://forum.example.com/forums/thread/{thread.pk}?page=1#post-{post.pk}' in message.body


def test_notification_mail_follows_a_swedish_site(tagged, reply, reply_with_mail, settings):
    settings.LANGUAGE_CODE = 'sv'

    reply_with_mail(*reply)

    assert mail.outbox[0].subject.startswith('<sv>New post added by <sv>Member ')


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
