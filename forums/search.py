"""
Full-text search over threads and replies, in English word forms (PostgreSQL). Threads and
replies are searched together as one list (a UNION), so it can be sorted and paged; the
objects for one page are loaded afterwards.
"""

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import (
    CharField,
    Count,
    F,
    FloatField,
    OuterRef,
    Q,
    Subquery,
    Value,
)

from .models import (
    POST_SEARCH_VECTOR,
    SEARCH_CONFIG,
    THREAD_SEARCH_VECTOR,
    Post,
    Thread,
)


def matches(data):
    """
    The matching threads and replies for the search form's cleaned data, as rows of
    kind ('thread' or 'post'), id, added and rank, sorted as asked.
    """
    query = SearchQuery(data['q'], search_type='websearch', config=SEARCH_CONFIG) if data['q'] else None
    kinds = {
        'threads': [_rows(Thread.objects.all(), 'thread', THREAD_SEARCH_VECTOR, 'forum', data, query)],
        'replies': [_rows(Post.objects.all(), 'post', POST_SEARCH_VECTOR, 'thread__forum', data, query)],
    }
    parts = kinds.get(data.get('kind')) or kinds['threads'] + kinds['replies']
    rows = parts[0].union(*parts[1:], all=True) if len(parts) > 1 else parts[0]
    if query and data.get('sort') != 'newest':
        return rows.order_by('-rank', '-added', '-id')
    return rows.order_by('-added', '-id')


def _rows(queryset, kind, vector, forum_field, data, query):
    if data.get('forum'):
        queryset = queryset.filter(**{forum_field: data['forum']})
    if data.get('author'):
        queryset = queryset.filter(user_id=data['author'])
    if data.get('since'):
        queryset = queryset.filter(added__date__gte=data['since'])
    if data.get('until'):
        queryset = queryset.filter(added__date__lte=data['until'])
    if query:
        # The same expression as the index on the model, so the index is used
        queryset = queryset.alias(document=vector).filter(document=query)
        rank = SearchRank(F('document'), query)
    else:
        rank = Value(0.0, output_field=FloatField())
    # Built the same way for both kinds, so the columns of the UNION line up
    return queryset.annotate(rank=rank, kind=Value(kind, output_field=CharField())).values(
        'id', 'added', 'rank', 'kind'
    )


def load(rows, posts_per_page):
    """
    The threads and replies for one page of rows, in the same order. Each reply gets its
    number in the thread (the opening post is #1) and the page of the thread it is on.
    """
    rows = list(rows)
    threads = Thread.objects.select_related('forum', 'user__profile').in_bulk(
        [row['id'] for row in rows if row['kind'] == 'thread']
    )
    # The replies up to and including this one, in the thread page's order
    position = (
        Post.objects.filter(thread=OuterRef('thread'))
        .filter(Q(added__lt=OuterRef('added')) | Q(added=OuterRef('added'), id__lte=OuterRef('id')))
        .order_by()
        .values('thread')
        .annotate(count=Count('id'))
        .values('count')
    )
    posts = (
        Post.objects.select_related('thread__forum', 'user__profile')
        .annotate(position=Subquery(position))
        .in_bulk([row['id'] for row in rows if row['kind'] == 'post'])
    )
    for post in posts.values():
        post.number = post.position + 1
        post.thread_page = (post.position - 1) // posts_per_page + 1
    return [(threads if row['kind'] == 'thread' else posts)[row['id']] for row in rows]
