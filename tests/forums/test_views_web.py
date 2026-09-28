import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from pytest_django.asserts import (
    assertContains,
    assertNotContains,
    assertRedirects,
    assertTemplateUsed,
)

from forums.models import Forum, Post, Thread


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def forum(add_forum):
    return add_forum(title='Testforum', description='A test forum')


@pytest.fixture
def thread(add_thread, forum, author):
    return add_thread(title='Testtitle', text='Thread text', forum=forum, user=author)


@pytest.fixture
def post(add_post, thread, author):
    return add_post(text='A reply to a thread', thread=thread, user=author)


# Pages


@pytest.mark.django_db
def test_forum_list_page(client, forum):
    resp = client.get(reverse('forum_list'))

    assert resp.status_code == 200
    assertTemplateUsed(resp, 'forums/forum_list.html')
    assertContains(resp, 'Testforum')
    assertNotContains(resp, 'This should not be here')


@pytest.mark.django_db
def test_forum_detail_page(client, thread):
    resp = client.get(reverse('forum_detail', args=(thread.forum.id,)))

    assert resp.status_code == 200
    assertTemplateUsed(resp, 'forums/forum_detail.html')
    assertContains(resp, 'Testforum')
    assertContains(resp, 'Testtitle')


@pytest.mark.django_db
def test_thread_detail_page(client, post, author):
    client.force_login(author)

    resp = client.get(reverse('thread_detail', args=(post.thread.id,)))

    assert resp.status_code == 200
    # The page also renders for anonymous users, so check the login took effect
    assert resp.context['user'] == author
    assertTemplateUsed(resp, 'forums/thread_detail.html')
    assertContains(resp, 'Testtitle')
    assertContains(resp, 'A reply to a thread')


# Create views


@pytest.mark.django_db
def test_forum_create(client, author):
    author.user_permissions.add(Permission.objects.get(codename='add_forum'))
    client.force_login(author)

    resp = client.post(
        reverse('forum_add'), {'title': 'New Forum', 'description': 'Desc'}
    )

    assertRedirects(resp, reverse('forum_list'))
    assert Forum.objects.filter(title='New Forum', description='Desc').exists()


@pytest.mark.django_db
def test_thread_create_sets_author_and_forum(client, add_user, forum):
    user = add_user('poster', 'poster@email.com', 'testpass123')
    client.force_login(user)

    resp = client.post(
        reverse('thread_add', args=(forum.id,)), {'title': 'New thread', 'text': 'Hi'}
    )

    assertRedirects(resp, reverse('forum_detail', args=(forum.id,)))
    thread = Thread.objects.get(title='New thread')
    assert thread.user == user
    assert thread.forum == forum


@pytest.mark.django_db
def test_thread_create_anonymous_redirects_to_login(client, forum):
    url = reverse('thread_add', args=(forum.id,))

    resp = client.post(url, {'title': 'New thread', 'text': 'Hi'})

    assertRedirects(
        resp, f"{reverse('account_login')}?next={url}", fetch_redirect_response=False
    )
    assert not Thread.objects.exists()


@pytest.mark.django_db
def test_post_create_sets_author_and_thread(client, add_user, thread):
    user = add_user('poster', 'poster@email.com', 'testpass123')
    client.force_login(user)

    resp = client.post(reverse('post_add', args=(thread.id,)), {'text': 'Reply'})

    assertRedirects(resp, reverse('thread_detail', args=(thread.id,)))
    post = Post.objects.get(text='Reply')
    assert post.user == user
    assert post.thread == thread


@pytest.mark.django_db
def test_post_create_anonymous_redirects_to_login(client, thread):
    url = reverse('post_add', args=(thread.id,))

    resp = client.post(url, {'text': 'Reply'})

    assertRedirects(
        resp, f"{reverse('account_login')}?next={url}", fetch_redirect_response=False
    )
    assert not Post.objects.exists()


# Delete views


def login_as(client, who, author, add_user):
    """Log in as the author, another user, or a member of the Moderators group."""
    if who == 'author':
        client.force_login(author)
        return
    user = add_user(who, f'{who}@email.com', 'testpass123')
    if who == 'moderator':
        user.groups.add(Group.objects.get(name='Moderators'))
    client.force_login(user)


@pytest.mark.django_db
@pytest.mark.parametrize('who', ['author', 'moderator'])
def test_thread_delete_allowed(client, add_user, author, thread, who):
    login_as(client, who, author, add_user)

    resp = client.post(
        reverse('thread_delete', kwargs={'fpk': thread.forum.id, 'pk': thread.id})
    )

    assertRedirects(resp, reverse('forum_detail', args=(thread.forum.id,)))
    assert not Thread.objects.filter(id=thread.id).exists()


@pytest.mark.django_db
def test_thread_delete_by_other_user_forbidden(client, add_user, author, thread):
    login_as(client, 'other', author, add_user)

    resp = client.post(
        reverse('thread_delete', kwargs={'fpk': thread.forum.id, 'pk': thread.id})
    )

    assert resp.status_code == 403
    assert Thread.objects.filter(id=thread.id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize('who', ['author', 'moderator'])
def test_post_delete_allowed(client, add_user, author, post, who):
    login_as(client, who, author, add_user)

    resp = client.post(
        reverse('post_delete', kwargs={'tpk': post.thread.id, 'pk': post.id})
    )

    assertRedirects(resp, reverse('thread_detail', args=(post.thread.id,)))
    assert not Post.objects.filter(id=post.id).exists()


@pytest.mark.django_db
def test_post_delete_by_other_user_forbidden(client, add_user, author, post):
    login_as(client, 'other', author, add_user)

    resp = client.post(
        reverse('post_delete', kwargs={'tpk': post.thread.id, 'pk': post.id})
    )

    assert resp.status_code == 403
    assert Post.objects.filter(id=post.id).exists()
