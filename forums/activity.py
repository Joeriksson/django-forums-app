"""
Activity for the lists of forums and threads: reply counts, the latest activity and who
replied last. Each helper adds a fixed number of queries, however many rows there are.
"""

from django.contrib.auth import get_user_model
from django.db.models import Count, Max, OuterRef, Subquery
from django.db.models.functions import Coalesce

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


def with_counts_and_latest(forums):
    """
    Add thread_count, reply_count and, for finding the latest thread, the newest thread
    and the thread with the newest reply to a queryset of forums.
    """
    newest_thread = Thread.objects.filter(forum=OuterRef('pk')).order_by('-added', '-id')
    newest_reply = Post.objects.filter(thread__forum=OuterRef('pk')).order_by('-added', '-id')
    return forums.annotate(
        thread_count=Count('threads', distinct=True),
        reply_count=Count('threads__posts', distinct=True),
        newest_thread_id=Subquery(newest_thread.values('id')[:1]),
        newest_thread_added=Subquery(newest_thread.values('added')[:1]),
        newest_reply_thread_id=Subquery(newest_reply.values('thread')[:1]),
        newest_reply_added=Subquery(newest_reply.values('added')[:1]),
    )


def add_latest_threads(forums):
    """
    Set latest on each forum from with_counts_and_latest(): the thread with the newest
    activity, with its activity and last replier, or None. Two queries for all forums.
    """
    forums = list(forums)
    for forum in forums:
        forum.latest_id = forum.newest_thread_id
        if forum.newest_reply_added and forum.newest_reply_added > forum.newest_thread_added:
            forum.latest_id = forum.newest_reply_thread_id
    ids = {forum.latest_id for forum in forums if forum.latest_id}
    threads = add_last_repliers(
        with_activity(Thread.objects.filter(id__in=ids).select_related('user__profile'))
    )
    by_id = {thread.id: thread for thread in threads}
    for forum in forums:
        forum.latest = by_id.get(forum.latest_id)
    return forums
