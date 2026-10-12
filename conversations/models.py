from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from forums.models import MARKDOWN_HELP, MAX_TEXT_LENGTH


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
    """The blocker doesn't want messages from the blocked member."""

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+'
    )
    added = models.DateTimeField(auto_now_add=True)

    @classmethod
    def is_blocked(cls, sender, receiver):
        """Whether the receiver has blocked the sender."""
        return cls.objects.filter(blocker=receiver, blocked=sender).exists()

    def __str__(self):
        return f'Block: {self.blocker} blocks {self.blocked}'

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['blocker', 'blocked'], name='unique_block_per_pair'),
            models.CheckConstraint(
                condition=~Q(blocker=F('blocked')), name='block_not_oneself'
            ),
        ]


def send(sender, receiver, text):
    """Add a message from one member to another, in their conversation. Returns the message."""
    with transaction.atomic():
        conversation = Conversation.between(sender, receiver)
        message = Message.objects.create(conversation=conversation, sender=sender, text=text)
        Conversation.objects.filter(pk=conversation.pk).update(updated=message.added)
    return message
