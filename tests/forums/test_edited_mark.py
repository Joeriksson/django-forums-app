"""
A text that was changed after it was posted says so: "Edited" with the date and time,
under the opening post and under a reply. "edited" is empty until then.
"""

from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest
from django.apps import apps
from django.contrib.auth.models import Group
from django.urls import reverse

from forums.models import Post, Thread


@pytest.fixture
def client(client, reader):
    client.force_login(reader)
    return client


@pytest.fixture
def thread(add_forum, add_thread, reader):
    return add_thread('Greenhouse', 'Text', add_forum('The house', 'Repairs'), reader)


@pytest.fixture
def post(thread, reader, add_post):
    return add_post('A reply', thread, reader)


def page(client, thread):
    resp = client.get(reverse('thread_detail', args=[thread.pk]))
    assert resp.status_code == 200
    return resp.content.decode()


def test_new_texts_are_not_marked(client, thread, post):
    assert Thread.objects.get(pk=thread.pk).edited is None
    assert Post.objects.get(pk=post.pk).edited is None
    assert 'post__edited' not in page(client, thread)


def test_changed_reply_is_marked(post):
    post.text = 'A better reply'
    post.save()
    assert Post.objects.get(pk=post.pk).edited > post.added


def test_reply_saved_unchanged_is_not_marked(post):
    post.save()
    assert Post.objects.get(pk=post.pk).edited is None


def test_upvote_does_not_mark_the_reply(thread, post, add_user, client):
    client.force_login(add_user('voter', 'voter@example.com', 'testpass123'))
    resp = client.post(reverse('post_upvote', args=[thread.pk, post.pk]))
    assert resp.status_code == 302
    post.refresh_from_db()
    assert post.upvotes == 1
    assert post.edited is None


@pytest.mark.parametrize(
    'data', [{'title': 'Greenhouse', 'text': 'New text'}, {'title': 'Glasshouse', 'text': 'Text'}]
)
def test_thread_edit_marks_the_opening_post(client, thread, data):
    resp = client.post(reverse('thread_update', args=[thread.pk]), data)
    assert resp.status_code == 302
    assert Thread.objects.get(pk=thread.pk).edited is not None
    assert 'post__edited' in page(client, thread)


def test_thread_form_saved_unchanged_is_not_marked(client, thread):
    resp = client.post(
        reverse('thread_update', args=[thread.pk]), {'title': 'Greenhouse', 'text': 'Text'}
    )
    assert resp.status_code == 302
    assert Thread.objects.get(pk=thread.pk).edited is None


def test_announcement_mark_is_not_an_edit(thread):
    thread.announcement = True
    thread.save()
    assert Thread.objects.get(pk=thread.pk).edited is None


def test_page_shows_date_and_time_of_the_edit(client, thread, post, settings):
    settings.TIME_ZONE = 'Europe/Paris'
    edited = datetime(2026, 10, 5, 14, 32, tzinfo=timezone.utc)
    Post.objects.filter(pk=post.pk).update(edited=edited)
    content = page(client, thread)
    assert content.count('post__edited') == 1
    # In the site's time zone, here two hours ahead of UTC in the summer
    assert 'Edited <time datetime="2026-10-05T16:32:00+02:00">5 Oct 2026, 16:32</time>' in content


def test_api_edit_marks_the_reply(post, reader, get_user_client):
    client = get_user_client(reader)
    url = reverse('post-detail', args=[post.pk])
    assert client.get(url).data['edited'] is None
    resp = client.patch(url, {'text': 'Changed through the API'})
    assert resp.status_code == 200
    assert resp.data['edited'] is not None


def test_migration_clears_only_times_set_at_creation(thread, post, add_post, reader):
    """Before the migration every save set "edited", the first one included."""
    changed = add_post('Changed later', thread, reader)
    Post.objects.filter(pk=post.pk).update(edited=post.added + timedelta(milliseconds=2))
    Post.objects.filter(pk=changed.pk).update(edited=changed.added + timedelta(minutes=5))
    Thread.objects.filter(pk=thread.pk).update(edited=thread.added)

    migration = import_module('forums.migrations.0022_edited_only_when_changed')
    migration.clear_unedited(apps, None)

    assert Post.objects.get(pk=post.pk).edited is None
    assert Post.objects.get(pk=changed.pk).edited is not None
    assert Thread.objects.get(pk=thread.pk).edited is None


# Who made the change: "by a moderator" when it wasn't the author


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@example.com', 'testpass123')


@pytest.fixture
def reply(thread, author, add_post):
    return add_post('As first written', thread, author)


@pytest.fixture
def moderator_client(add_user, get_user_client):
    moderator = add_user('moderator', 'moderator@example.com', 'testpass123')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    return get_user_client(moderator)


@pytest.fixture
def superuser_client(add_super_user, get_user_client):
    return get_user_client(add_super_user('root', 'root@example.com', 'testpass123'))


def edit_thread(client, thread, **data):
    resp = client.post(
        reverse('thread_update', args=[thread.pk]),
        {'title': thread.title, 'text': thread.text, **data},
    )
    assert resp.status_code == 302


def edit_reply(client, reply, text):
    resp = client.post(reverse('post_update', args=[reply.thread_id, reply.pk]), {'text': text})
    assert resp.status_code == 302


def test_authors_own_edit_names_no_moderator(client, thread):
    edit_thread(client, thread, text='New text')
    content = page(client, thread)
    assert 'post__edited' in content
    assert 'by a moderator' not in content


def test_moderators_edit_of_a_thread_says_so(client, moderator_client, thread):
    edit_thread(moderator_client, thread, text='Tidied up')
    assert page(client, thread).count('</time> by a moderator</p>') == 1


def test_moderators_announcement_mark_leaves_no_line(client, moderator_client, thread):
    edit_thread(moderator_client, thread, announcement='on')
    thread.refresh_from_db()
    assert thread.announcement
    assert thread.edited_by is None
    assert 'post__edited' not in page(client, thread)


def test_authors_later_edit_makes_the_line_plain_again(client, moderator_client, thread):
    edit_thread(moderator_client, thread, text='Tidied up')
    edit_thread(client, Thread.objects.get(pk=thread.pk), text='My own words again')
    content = page(client, thread)
    assert 'post__edited' in content
    assert 'by a moderator' not in content


def test_superusers_edit_of_a_reply_says_by_a_moderator(client, superuser_client, thread, reply):
    edit_reply(superuser_client, reply, 'Tidied up')
    assert page(client, thread).count('</time> by a moderator</p>') == 1


def test_authors_edit_of_a_reply_names_no_moderator(client, author, thread, reply):
    client.force_login(author)
    edit_reply(client, reply, 'Thought again')
    content = page(client, thread)
    assert 'post__edited' in content
    assert 'by a moderator' not in content


def test_api_edit_by_someone_else_is_marked(superuser_client, reply):
    resp = superuser_client.patch(reverse('post-detail', args=[reply.pk]), {'text': 'Tidied up'})
    assert resp.status_code == 200
    assert Post.objects.get(pk=reply.pk).edited_by_moderator


def test_api_edit_by_the_author_is_not(reply, author, get_user_client):
    resp = get_user_client(author).patch(
        reverse('post-detail', args=[reply.pk]), {'text': 'Thought again'}
    )
    assert resp.status_code == 200
    reply = Post.objects.get(pk=reply.pk)
    assert reply.edited_by == author
    assert not reply.edited_by_moderator


def test_admin_edit_is_marked(superuser_client, thread, reply):
    resp = superuser_client.post(
        reverse('admin:forums_post_change', args=[reply.pk]),
        {'text': 'Tidied up', 'upvotes': 0, 'thread': thread.pk, 'user': reply.user_id},
    )
    assert resp.status_code == 302
    reply = Post.objects.get(pk=reply.pk)
    assert reply.text == 'Tidied up'
    assert reply.edited_by_moderator


def test_change_saved_without_an_editor_is_plain(reply):
    reply.text = 'Changed by a script'
    reply.save()
    reply = Post.objects.get(pk=reply.pk)
    assert reply.edited is not None
    assert not reply.edited_by_moderator


def test_line_turns_plain_when_the_editors_account_is_deleted(superuser_client, reply):
    edit_reply(superuser_client, reply, 'Tidied up')
    Post.objects.get(pk=reply.pk).edited_by.delete()
    reply = Post.objects.get(pk=reply.pk)
    assert reply.edited is not None
    assert not reply.edited_by_moderator
