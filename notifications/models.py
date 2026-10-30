from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """
    News for one member, shown in the notification center. Replies are kept as one row
    per thread: it counts the replies since the member last opened the thread and starts
    over at the next reply after that, so the table doesn't grow with the posts.
    Direct messages are kept the same way, as one row per conversation.
    Written by notifications/events.py.
    """

    class Kind(models.TextChoices):
        REPLY = 'reply', 'Reply'
        MESSAGE = 'message', 'Message'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.REPLY)
    thread = models.ForeignKey(
        'forums.Thread',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    # The first reply the member hasn't seen; empty once that reply is deleted
    post = models.ForeignKey(
        'forums.Post', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    # The first message the member hasn't seen
    message = models.ForeignKey(
        'conversations.Message', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    # Replies or messages since the member last opened the thread or the conversation;
    # a deleted reply doesn't lower it
    count = models.PositiveIntegerField(default=1)
    read = models.BooleanField(default=False)
    updated = models.DateTimeField(default=timezone.now)

    @classmethod
    def unread_counts(cls, user):
        """
        The numbers in the header, in one query: threads with unread replies (the bell)
        and conversations with unread messages (the envelope).
        """
        return cls.objects.filter(user=user, read=False).aggregate(
            replies=models.Count('pk', filter=models.Q(kind=cls.Kind.REPLY)),
            messages=models.Count('pk', filter=models.Q(kind=cls.Kind.MESSAGE)),
        )

    def __str__(self):
        where = self.thread or self.conversation
        return f'Notification: {self.kind} in {where} ({self.count}) for {self.user}'

    class Meta:
        ordering = ['read', '-updated']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'thread'], name='unique_notification_per_thread'
            ),
            models.UniqueConstraint(
                fields=['user', 'conversation'], name='unique_notification_per_conversation'
            ),
        ]
