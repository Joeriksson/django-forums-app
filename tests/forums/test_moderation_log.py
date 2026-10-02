import logging

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

IP = '203.0.113.7'


@pytest.fixture
def security_log(caplog):
    """The lines written to the security log during the test."""
    caplog.set_level(logging.INFO, logger='security')

    def lines():
        return [record.getMessage() for record in caplog.records if record.name == 'security']

    return lines


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def content(author, add_forum, add_thread, add_post):
    forum = add_forum(title='General Forum', description='This is a general forum')
    thread = add_thread(title='A thread', text='This is a new thread', forum=forum, user=author)
    post = add_post(text='A post by the author', thread=thread, user=author)
    return thread, post


@pytest.fixture
def moderator(add_user):
    moderator = add_user('moderator', 'moderator@email.com', 'testpass123')
    moderator.groups.add(Group.objects.get(name='Moderators'))
    return moderator


@pytest.fixture
def moderator_client(moderator, get_user_client):
    client = get_user_client(moderator)
    client.defaults['REMOTE_ADDR'] = IP
    return client


def moderation_line(action, moderator, kind, pk, author):
    return f'moderation action={action} user={moderator.pk} object={kind} id={pk} owner={author.pk} ip={IP}'


# Website


@pytest.mark.django_db
def test_deleting_someone_elses_post_on_the_site_is_logged(
    moderator, moderator_client, author, content, security_log
):
    thread, post = content

    resp = moderator_client.post(reverse('post_delete', kwargs={'tpk': thread.pk, 'pk': post.pk}))

    assert resp.status_code == 302
    assert security_log() == [moderation_line('delete', moderator, 'post', post.pk, author)]


@pytest.mark.django_db
def test_deleting_someone_elses_thread_on_the_site_is_logged(
    moderator, moderator_client, author, content, security_log
):
    thread, _ = content

    resp = moderator_client.post(
        reverse('thread_delete', kwargs={'fpk': thread.forum_id, 'pk': thread.pk})
    )

    assert resp.status_code == 302
    assert security_log() == [moderation_line('delete', moderator, 'thread', thread.pk, author)]


@pytest.mark.django_db
def test_editing_someone_elses_thread_on_the_site_is_logged(
    moderator, moderator_client, author, content, security_log
):
    thread, _ = content

    resp = moderator_client.post(
        reverse('thread_update', kwargs={'pk': thread.pk}), {'title': 'Edited', 'text': 'Edited'}
    )

    assert resp.status_code == 302
    assert security_log() == [moderation_line('change', moderator, 'thread', thread.pk, author)]


@pytest.mark.django_db
def test_a_rejected_edit_is_not_logged(moderator_client, content, security_log):
    thread, _ = content

    resp = moderator_client.post(
        reverse('thread_update', kwargs={'pk': thread.pk}), {'title': '', 'text': ''}
    )

    assert resp.status_code == 200
    assert security_log() == []


@pytest.mark.django_db
def test_changes_to_own_content_on_the_site_are_not_logged(
    client, author, content, security_log
):
    thread, post = content
    client.force_login(author)

    responses = (
        client.post(reverse('thread_update', kwargs={'pk': thread.pk}), {'title': 'Mine', 'text': 'Mine'}),
        client.post(reverse('post_delete', kwargs={'tpk': thread.pk, 'pk': post.pk})),
        client.post(reverse('thread_delete', kwargs={'fpk': thread.forum_id, 'pk': thread.pk})),
    )

    assert [resp.status_code for resp in responses] == [302, 302, 302]
    # Only the login
    assert security_log() == [f'login user={author.pk}']


# API


@pytest.mark.django_db
def test_deleting_someone_elses_post_through_the_api_is_logged(
    moderator, moderator_client, author, content, security_log
):
    _, post = content

    resp = moderator_client.delete(f'/api/posts/{post.pk}/')

    assert resp.status_code == 204
    assert security_log() == [moderation_line('delete', moderator, 'post', post.pk, author)]


@pytest.mark.django_db
def test_deleting_someone_elses_thread_through_the_api_is_logged(
    moderator, moderator_client, author, content, security_log
):
    thread, _ = content

    resp = moderator_client.delete(f'/api/threads/{thread.pk}/')

    assert resp.status_code == 204
    assert security_log() == [moderation_line('delete', moderator, 'thread', thread.pk, author)]


@pytest.mark.django_db
def test_editing_someone_elses_thread_through_the_api_is_logged(
    moderator, moderator_client, author, content, security_log
):
    thread, _ = content

    resp = moderator_client.patch(f'/api/threads/{thread.pk}/', {'title': 'Edited'}, format='json')

    assert resp.status_code == 200
    assert security_log() == [moderation_line('change', moderator, 'thread', thread.pk, author)]


@pytest.mark.django_db
def test_changes_to_own_content_through_the_api_are_not_logged(
    author, content, get_user_client, security_log
):
    thread, post = content
    client = get_user_client(author)

    assert client.patch(f'/api/threads/{thread.pk}/', {'title': 'Mine'}, format='json').status_code == 200
    assert client.delete(f'/api/posts/{post.pk}/').status_code == 204
    assert client.delete(f'/api/threads/{thread.pk}/').status_code == 204

    assert security_log() == []
