from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """
    News for one member, shown in the notification center. Replies are kept as one row
    per thread: it counts the replies since the member last opened the thread and starts
    over at the next reply after that, so the table doesn't grow with the posts.
    Written by notifications/events.py.
    """

    class Kind(models.TextChoices):
        REPLY = 'reply', 'Reply'

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
    # Replies since the member last opened the thread; a deleted reply doesn't lower it
    count = models.PositiveIntegerField(default=1)
    read = models.BooleanField(default=False)
    updated = models.DateTimeField(default=timezone.now)

    @classmethod
    def unread_count(cls, user):
        """The number on the header's bell."""
        return cls.objects.filter(user=user, read=False).count()

    def __str__(self):
        return f'Notification: {self.kind} in {self.thread} ({self.count}) for {self.user}'

    class Meta:
        ordering = ['read', '-updated']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'thread'], name='unique_notification_per_thread'
            ),
        ]
