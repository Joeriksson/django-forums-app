import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse


def grant(user, *codenames):
    perms = Permission.objects.filter(
        content_type__app_label='forums', codename__in=codenames
    )
    assert perms.count() == len(codenames)
    user.user_permissions.add(*perms)


@pytest.fixture
def forum_with_thread(add_user, add_forum, add_thread):
    author = add_user('author', 'author@email.com', 'testpass123')
    forum = add_forum(title="General Forum", description="This is a general forum")
    thread = add_thread(
        title='A thread in the General Forum',
        text='This is a new thread',
        forum=forum,
        user=author,
    )
    return forum, thread


def thread_button_urls(forum, thread):
    return (
        reverse('thread_delete', kwargs={'fpk': forum.id, 'pk': thread.id}),
        reverse('thread_update', kwargs={'pk': thread.id}),
    )


# ForumCreate


@pytest.mark.django_db
def test_forum_add_anonymous_redirects_to_login(client):
    resp = client.get(reverse('forum_add'))

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))


@pytest.mark.django_db
def test_forum_add_without_permission_forbidden(client, add_user):
    user = add_user('user', 'user@email.com', 'testpass123')
    client.force_login(user)

    resp = client.get(reverse('forum_add'))

    assert resp.status_code == 403


# ThreadUpdate


@pytest.mark.django_db
def test_moderator_can_update_other_users_thread(client, add_user, forum_with_thread):
    _, thread = forum_with_thread
    moderator = add_user('moderator', 'moderator@email.com', 'testpass123')
    grant(moderator, 'change_thread')
    client.force_login(moderator)

    resp = client.get(reverse('thread_update', kwargs={'pk': thread.id}))

    assert resp.status_code == 200


@pytest.mark.django_db
def test_user_cannot_update_other_users_thread(client, add_user, forum_with_thread):
    _, thread = forum_with_thread
    user = add_user('user', 'user@email.com', 'testpass123')
    client.force_login(user)

    resp = client.get(reverse('thread_update', kwargs={'pk': thread.id}))

    assert resp.status_code == 403


# Thread buttons on the forum page


@pytest.mark.django_db
def test_moderator_sees_thread_buttons(client, add_user, forum_with_thread):
    forum, thread = forum_with_thread
    moderator = add_user('moderator', 'moderator@email.com', 'testpass123')
    grant(moderator, 'delete_thread', 'change_thread')
    client.force_login(moderator)

    content = client.get(reverse('forum_detail', kwargs={'pk': forum.id})).content.decode()

    for url in thread_button_urls(forum, thread):
        assert url in content


@pytest.mark.django_db
def test_forum_permissions_do_not_show_thread_buttons(
    client, add_user, forum_with_thread
):
    forum, thread = forum_with_thread
    user = add_user('user', 'user@email.com', 'testpass123')
    grant(user, 'delete_forum', 'change_forum')
    client.force_login(user)

    content = client.get(reverse('forum_detail', kwargs={'pk': forum.id})).content.decode()

    for url in thread_button_urls(forum, thread):
        assert url not in content


@pytest.mark.django_db
def test_author_sees_thread_buttons(client, forum_with_thread):
    forum, thread = forum_with_thread
    client.force_login(thread.user)

    content = client.get(reverse('forum_detail', kwargs={'pk': forum.id})).content.decode()

    for url in thread_button_urls(forum, thread):
        assert url in content
