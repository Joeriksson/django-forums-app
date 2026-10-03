"""
Activity for the lists of forums and threads: reply counts, the latest activity and who
replied last. Each helper adds a fixed number of queries, however many rows there are.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Max, OuterRef, Subquery, Window
from django.db.models.functions import Coalesce, RowNumber

from .models import Post, Thread


def with_activity(threads):
    """
    Add post_count, last_activity (the newest reply, or the start for a thread without
    replies) and last_replier_id to a queryset of threads.
    """
    newest_reply = Post.objects.filter(thread=OuterRef('pk')).order_by('-added', '-id')
    return threads.annotate(
        post_count=Count('posts'),
        last_reply=Max('posts__added'),
        last_activity=Coalesce('last_reply', 'added'),
        last_replier_id=Subquery(newest_reply.values('user')[:1]),
    )


def add_last_repliers(threads):
    """Set last_replier on each thread from with_activity(): one query for all of them."""
    threads = list(threads)
    ids = {thread.last_replier_id for thread in threads if thread.last_replier_id}
    users = get_user_model().objects.select_related('profile').in_bulk(ids)
    for thread in threads:
        thread.last_replier = users.get(thread.last_replier_id)
    return threads


def latest_threads(count):
    """
    The count threads with the newest activity across all forums, each with its forum,
    author and last replier. A thread without replies counts from when it was started.
    Two queries.
    """
    threads = with_activity(Thread.objects.select_related('forum', 'user__profile'))
    return add_last_repliers(threads.order_by('-last_activity', '-id')[:count])


def with_counts(forums):
    """Add thread_count and reply_count to a queryset of forums."""
    return forums.annotate(
        thread_count=Count('threads', distinct=True),
        reply_count=Count('threads__posts', distinct=True),
    )


def add_top_threads(forums, per_forum=2):
    """
    Set top_threads on each forum: its announcements first, then the threads with the
    newest activity, per_forum in all, each with its activity and last replier. Two
    queries for all forums.
    """
    forums = list(forums)
    rank = Window(
        RowNumber(),
        partition_by='forum',
        order_by=(F('announcement').desc(), F('last_activity').desc(), F('id').desc()),
    )
    threads = add_last_repliers(
        with_activity(Thread.objects.filter(forum__in=forums).select_related('user__profile'))
        .annotate(rank=rank)
        .filter(rank__lte=per_forum)
        .order_by('forum', 'rank')
    )
    by_forum = {}
    for thread in threads:
        by_forum.setdefault(thread.forum_id, []).append(thread)
    for forum in forums:
        forum.top_threads = by_forum.get(forum.id, [])
    return forums
