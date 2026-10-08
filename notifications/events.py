"""What happens on the site, turned into rows for the notification center."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from forums.models import Subscription

from .models import Notification


def reply_added(post):
    """
    Tell the thread's subscribers about a new reply, except its author: one more on a
    row not yet read, a fresh start at this reply on a row that was read or is missing.
    Four queries however many subscribers. Returns whether anyone was told.
    """
    user_ids = list(
        Subscription.objects.filter(thread_id=post.thread_id, user__is_active=True)
        .exclude(user_id=post.user_id)
        .values_list('user_id', flat=True)
    )
    if not user_ids:
        return False

    now = timezone.now()
    rows = Notification.objects.filter(thread_id=post.thread_id, user_id__in=user_ids)
    with transaction.atomic():
        rows.filter(read=False).update(count=F('count') + 1, updated=now)
        rows.filter(read=True).update(read=False, post=post, count=1, updated=now)
        # Rows that exist were handled above and are left alone here
        Notification.objects.bulk_create(
            [
                Notification(user_id=user_id, thread_id=post.thread_id, post=post, updated=now)
                for user_id in user_ids
            ],
            ignore_conflicts=True,
        )
    return True


def thread_opened(user, thread):
    """The member has seen the thread: its news is read, whichever page was opened."""
    Notification.objects.filter(user=user, thread=thread, read=False).update(read=True)
