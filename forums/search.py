"""
Full-text search over threads and replies, in English word forms (PostgreSQL). Threads and
replies are searched together as one list (a UNION), so it can be sorted and paged; the
objects for one page are loaded afterwards, with the matched words marked.
"""

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank
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
from django.db.models.functions import Replace
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import Truncator

from .markdown import render as render_markdown
from .models import (
    POST_SEARCH_VECTOR,
    SEARCH_CONFIG,
    THREAD_SEARCH_VECTOR,
    Post,
    Thread,
)

# PostgreSQL marks the matched words with these (Unicode private use characters, which no
# text needs); they become <mark> tags only after the text has been escaped
START, STOP = '\ue000', '\ue001'


def search_query(data):
    """The words of the search form's cleaned data as a full-text query, or None."""
    return SearchQuery(data['q'], search_type='websearch', config=SEARCH_CONFIG) if data['q'] else None


def matches(data):
    """
    The matching threads and replies for the search form's cleaned data, as rows of
    kind ('thread' or 'post'), id, added and rank, sorted as asked.
    """
    query = search_query(data)
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


def load(rows, posts_per_page, query=None):
    """
    The threads and replies for one page of rows, in the same order. Each reply gets its
    number in the thread (the opening post is #1) and the page of the thread it is on;
    each result an excerpt, with the words of `query` marked. Titles are shown as typed:
    ts_headline treats text as HTML and may drop parts that look like tags, which is
    fine for an excerpt but not for a title.
    """
    rows = list(rows)
    threads = Thread.objects.select_related('forum', 'user__profile')
    posts = Post.objects.select_related('thread__forum', 'user__profile')
    if query:
        threads = threads.annotate(text_marked=_headline('text', query))
        posts = posts.annotate(text_marked=_headline('text', query))
    threads = threads.in_bulk([row['id'] for row in rows if row['kind'] == 'thread'])
    # The replies up to and including this one, in the thread page's order
    position = (
        Post.objects.filter(thread=OuterRef('thread'))
        .filter(Q(added__lt=OuterRef('added')) | Q(added=OuterRef('added'), id__lte=OuterRef('id')))
        .order_by()
        .values('thread')
        .annotate(count=Count('id'))
        .values('count')
    )
    posts = posts.annotate(position=Subquery(position)).in_bulk(
        [row['id'] for row in rows if row['kind'] == 'post']
    )
    for post in posts.values():
        post.number = post.position + 1
        post.thread_page = (post.position - 1) // posts_per_page + 1
    for result in [*threads.values(), *posts.values()]:
        if query:
            result.excerpt = _marked(_plain(result.text_marked))
        else:
            result.excerpt = mark_safe(Truncator(_plain(result.text[:400])).chars(160))
    return [(threads if row['kind'] == 'thread' else posts)[row['id']] for row in rows]


def _headline(field, query):
    # Marker characters a member typed are dropped first, so every marker is PostgreSQL's
    text = Replace(Replace(F(field), Value(START), Value('')), Value(STOP), Value(''))
    return SearchHeadline(
        text,
        query,
        config=SEARCH_CONFIG,
        start_sel=START,
        stop_sel=STOP,
        max_words=30,
        min_words=15,
        max_fragments=2,
        fragment_delimiter=' … ',
    )


def _plain(markdown_text):
    """Markdown as plain text, escaped: rendered (which escapes), then the tags dropped."""
    return strip_tags(render_markdown(markdown_text))


def _marked(escaped_text):
    """Escaped text with PostgreSQL's markers turned into <mark> tags."""
    return mark_safe(escaped_text.replace(START, '<mark>').replace(STOP, '</mark>'))
