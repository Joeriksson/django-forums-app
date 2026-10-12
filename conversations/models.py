import os

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from forums.models import MARKDOWN_HELP, MAX_TEXT_LENGTH
from notifications.events import message_sent
from pages.models import SiteSettings
from project.utils import queue_task

from .tasks import send_message_mail_task


class Conversation(models.Model):
    """
    The direct messages between two members: one row per pair, with the smaller user id
    in user_low, so the pair is the same whoever writes first. Get it with between().
    """

    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    # When the latest message was sent
    updated = models.DateTimeField(default=timezone.now)

    @classmethod
    def between(cls, user, other):
        """The two members' conversation, started if they have none."""
        if user.pk == other.pk:
            raise ValueError('A conversation needs two members')
        low, high = sorted((user.pk, other.pk))
        conversation, _created = cls.objects.get_or_create(user_low_id=low, user_high_id=high)
        return conversation

    @classmethod
    def find(cls, user, other):
        """The two members' conversation, or None before their first message."""
        low, high = sorted((user.pk, other.pk))
        return cls.objects.filter(user_low_id=low, user_high_id=high).first()

    def other_id(self, user_id):
        """The id of the member that one of the two is talking to."""
        return self.user_high_id if user_id == self.user_low_id else self.user_low_id

    def __str__(self):
        return f'Conversation: {self.user_low} and {self.user_high}'

    class Meta:
        ordering = ['-updated']
        constraints = [
            models.UniqueConstraint(
                fields=['user_low', 'user_high'], name='unique_conversation_per_pair'
            ),
            models.CheckConstraint(
                condition=Q(user_low__lt=F('user_high')), name='conversation_users_in_order'
            ),
        ]


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    text = models.TextField(_('text'), max_length=MAX_TEXT_LENGTH, help_text=MARKDOWN_HELP)
    added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Not the text: messages are between the two members
        return f'Message {self.pk} from {self.sender}'

    class Meta:
        ordering = ['added', 'id']


class Block(models.Model):
    """
    The blocker doesn't want messages from the blocked member. It stops messages both
    ways, so the blocker doesn't get the last word: see send().
    """

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    added = models.DateTimeField(auto_now_add=True)

    @classmethod
    def between(cls, user, other):
        """Who of the two has blocked the other: the blockers' ids, in one query."""
        return set(
            cls.objects.filter(
                Q(blocker=user, blocked=other) | Q(blocker=other, blocked=user)
            ).values_list('blocker_id', flat=True)
        )

    def __str__(self):
        return f'Block: {self.blocker} blocks {self.blocked}'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['blocker', 'blocked'], name='unique_block_per_pair'),
            models.CheckConstraint(
                condition=~Q(blocker=F('blocked')), name='block_not_oneself'
            ),
        ]


MAX_NOTE_LENGTH = 500


class Report(models.Model):
    """
    One message that its receiver has shown to the moderators (the Reports page): a
    copy, since nobody but the two members reads the messages themselves. It is kept
    when the message, the conversation or an account is deleted. Make it with of().
    """

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+'
    )
    # Who wrote the message
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+'
    )
    # One report per message
    message = models.OneToOneField(
        Message, on_delete=models.SET_NULL, null=True, related_name='report'
    )
    # The message as it was when reported, and when it was sent
    text = models.TextField()
    sent = models.DateTimeField()
    note = models.CharField(_('note to the moderators'), max_length=MAX_NOTE_LENGTH, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    # Empty until a moderator has dealt with it
    handled = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    @classmethod
    def of(cls, message, reporter, note=''):
        """Report a message: copies it, so the report doesn't depend on it."""
        return cls.objects.create(
            reporter=reporter,
            sender_id=message.sender_id,
            message=message,
            text=message.text,
            sent=message.added,
            note=note,
        )

    def __str__(self):
        # Not the text
        return f'Report {self.pk} of a message from {self.sender}'

    class Meta:
        # Those not yet handled first, then the newest
        ordering = [F('handled').desc(nulls_first=True), '-created']


class Blocked(Exception):
    """One of the two members has blocked the other: no messages either way."""


def send(sender, receiver, text):
    """
    Add a message from one member to another, in their conversation. Once it is
    committed the receiver is told in the notification center, and the mail about it is
    queued to wait some minutes (conversations/tasks.py). Returns the message.
    Raises Blocked if either has blocked the other.
    """
    if Block.between(sender, receiver):
        raise Blocked
    with transaction.atomic():
        conversation = Conversation.between(sender, receiver)
        message = Message.objects.create(conversation=conversation, sender=sender, text=text)
        Conversation.objects.filter(pk=conversation.pk).update(updated=message.added)
        transaction.on_commit(lambda: notify(message))
    return message


def notify(message):
    # The notification center first: the mail goes to a receiver it still shows as unread
    notified = message_sent(message)
    # Not in CI, as for replies
    if notified and not os.environ.get('CI'):
        delay = SiteSettings.load().notification_mail_delay
        queue_task(send_message_mail_task, message.pk, countdown=delay * 60)
