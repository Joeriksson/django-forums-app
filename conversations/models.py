from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from forums.models import MARKDOWN_HELP, MAX_TEXT_LENGTH
from notifications.events import message_sent


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


class Blocked(Exception):
    """One of the two members has blocked the other: no messages either way."""


def send(sender, receiver, text):
    """
    Add a message from one member to another, in their conversation, and tell the
    receiver in the notification center once it is committed. Returns the message.
    Raises Blocked if either has blocked the other.
    """
    if Block.between(sender, receiver):
        raise Blocked
    with transaction.atomic():
        conversation = Conversation.between(sender, receiver)
        message = Message.objects.create(conversation=conversation, sender=sender, text=text)
        Conversation.objects.filter(pk=conversation.pk).update(updated=message.added)
        transaction.on_commit(lambda: message_sent(message))
    return message
