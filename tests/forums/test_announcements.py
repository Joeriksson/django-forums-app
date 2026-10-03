"""
Announcements: threads a moderator (anyone with forums.change_thread) marks to stay at the
top of their forum. Moderators can mark any thread, and their own new thread at once;
other members can neither set nor clear the mark.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from forums.models import Thread
from forums.views import ForumDetail

CHECKBOX = 'name="announcement"'


@pytest.fixture
def forum(add_forum):
    return add_forum('The house', 'Repairs')


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@example.com', 'x')


@pytest.fixture
def moderator(add_user):
    moderator = add_user('moderator', 'moderator@example.com', 'x')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    return moderator


@pytest.fixture
def author_client(client, author):
    client.force_login(author)
    return client


@pytest.fixture
def moderator_client(moderator, get_user_client):
    return get_user_client(moderator)


@pytest.fixture
def thread(forum, author, add_thread):
    return add_thread('Roof', 'Text', forum, author)


def edit(client, thread, **data):
    return client.post(
        reverse('thread_update', args=[thread.pk]), {'title': thread.title, 'text': thread.text, **data}
    )


# Forms


@pytest.mark.django_db
def test_members_have_no_announcement_checkbox(author_client, forum, thread):
    assertNotContains(author_client.get(reverse('thread_add', args=[forum.pk])), CHECKBOX)
    assertNotContains(author_client.get(reverse('thread_update', args=[thread.pk])), CHECKBOX)


@pytest.mark.django_db
def test_moderators_have_the_announcement_checkbox(moderator_client, forum, thread):
    assertContains(moderator_client.get(reverse('thread_add', args=[forum.pk])), CHECKBOX)
    assertContains(moderator_client.get(reverse('thread_update', args=[thread.pk])), CHECKBOX)


@pytest.mark.django_db
def test_moderator_starts_an_announcement(moderator_client, forum):
    moderator_client.post(
        reverse('thread_add', args=[forum.pk]), {'title': 'House rules', 'text': 'Text', 'announcement': 'on'}
    )

    assert Thread.objects.get(title='House rules').announcement is True


@pytest.mark.django_db
def test_member_cannot_start_an_announcement(author_client, forum):
    author_client.post(
        reverse('thread_add', args=[forum.pk]), {'title': 'Mine', 'text': 'Text', 'announcement': 'on'}
    )

    assert Thread.objects.get(title='Mine').announcement is False


@pytest.mark.django_db
def test_moderator_marks_someone_elses_thread_and_it_is_logged(
    moderator_client, moderator, author, thread, security_log
):
    edit(moderator_client, thread, announcement='on')

    thread.refresh_from_db()
    assert thread.announcement is True
    assert any(
        line.startswith(f'moderation action=change user={moderator.pk} object=thread id={thread.pk}')
        for line in security_log()
    )


@pytest.mark.django_db
def test_moderator_unmarks_an_announcement(moderator_client, thread):
    Thread.objects.filter(pk=thread.pk).update(announcement=True)

    edit(moderator_client, thread)

    thread.refresh_from_db()
    assert thread.announcement is False


@pytest.mark.django_db
def test_authors_edit_keeps_the_moderators_mark(author_client, thread):
    Thread.objects.filter(pk=thread.pk).update(announcement=True)

    edit(author_client, thread, title='Roof, again')

    thread.refresh_from_db()
    assert thread.title == 'Roof, again'
    assert thread.announcement is True


@pytest.mark.django_db
def test_member_cannot_mark_own_thread_by_editing(author_client, thread):
    edit(author_client, thread, announcement='on')

    thread.refresh_from_db()
    assert thread.announcement is False


# API


@pytest.mark.django_db
def test_api_shows_the_mark(get_user_client, author, thread):
    resp = get_user_client(author).get(reverse('thread-detail', args=[thread.pk]))

    assert resp.json()['announcement'] is False


@pytest.mark.django_db
def test_api_refuses_a_members_mark(get_user_client, author, thread):
    resp = get_user_client(author).patch(
        reverse('thread-detail', args=[thread.pk]), {'announcement': True}, format='json'
    )

    assert resp.status_code == 400
    thread.refresh_from_db()
    assert thread.announcement is False


@pytest.mark.django_db
def test_api_refuses_a_member_starting_an_announcement(get_user_client, author, forum):
    resp = get_user_client(author).post(
        reverse('thread-list'), {'title': 'T', 'text': 'Text', 'forum': forum.pk, 'announcement': True}, format='json'
    )

    assert resp.status_code == 400
    assert not Thread.objects.filter(title='T').exists()


@pytest.mark.django_db
def test_api_lets_a_moderator_mark(get_user_client, moderator, thread):
    resp = get_user_client(moderator).patch(
        reverse('thread-detail', args=[thread.pk]), {'announcement': True}, format='json'
    )

    assert resp.status_code == 200
    thread.refresh_from_db()
    assert thread.announcement is True


@pytest.mark.django_db
def test_api_member_may_send_the_unchanged_value(get_user_client, author, thread):
    resp = get_user_client(author).patch(
        reverse('thread-detail', args=[thread.pk]), {'title': 'New', 'announcement': False}, format='json'
    )

    assert resp.status_code == 200


# Where announcements show


@pytest.fixture
def announcement(forum, moderator, add_thread):
    thread = add_thread('House rules', 'Text', forum, moderator)
    Thread.objects.filter(pk=thread.pk).update(announcement=True)
    return thread


@pytest.mark.django_db
def test_forum_page_lists_announcements_above_the_threads_on_every_page(
    author_client, forum, author, add_thread, announcement, monkeypatch
):
    monkeypatch.setattr(ForumDetail, 'paginate_by', 2)
    for number in range(3):
        add_thread(f'Thread {number}', 'Text', forum, author)
    url = reverse('forum_detail', args=[forum.pk])

    for page in (1, 2):
        resp = author_client.get(url, {'page': page})
        assert list(resp.context['announcements']) == [announcement]
        assert announcement not in resp.context['threads']
        content = resp.content.decode()
        assert content.index('House rules') < content.index('aria-label="Threads"')

    # Three threads on pages of two: the announcement doesn't count
    assert resp.context['threads'].paginator.num_pages == 2


@pytest.mark.django_db
def test_forum_page_without_announcements_has_no_section(author_client, forum, thread):
    resp = author_client.get(reverse('forum_detail', args=[forum.pk]))

    assertNotContains(resp, 'aria-label="Announcements"')


@pytest.mark.django_db
def test_announcements_stay_in_their_forum(author_client, add_forum, announcement):
    other = add_forum('Trips', 'Where to')

    resp = author_client.get(reverse('forum_detail', args=[other.pk]))

    assert list(resp.context['announcements']) == []


@pytest.mark.django_db
def test_thread_page_labels_an_announcement(author_client, announcement, thread):
    assertContains(author_client.get(reverse('thread_detail', args=[announcement.pk])), '<p class="kicker">Announcement</p>')
    assertContains(author_client.get(reverse('thread_detail', args=[thread.pk])), '<p class="kicker">Thread</p>')


@pytest.mark.django_db
def test_forum_page_query_count_with_announcements(
    author_client, forum, author, add_thread, add_post, announcement, django_assert_num_queries
):
    for number in range(3):
        add_post('A reply', add_thread(f'Thread {number}', 'Text', forum, author), author)
    add_post('A reply', announcement, author)

    # As before (forum, count, threads, last repliers), plus the announcements,
    # after seven for the logged-in reader
    with django_assert_num_queries(7 + 5):
        author_client.get(reverse('forum_detail', args=[forum.pk]))
