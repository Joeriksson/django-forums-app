import pytest
from django.urls import reverse

from forums.models import Post, Thread

TEXT_LIMIT = 20_000
SIGNATURE_LIMIT = 500


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def forum(add_forum):
    return add_forum(title='General Forum', description='This is a general forum')


@pytest.fixture
def thread(add_thread, forum, author):
    return add_thread(title='A thread', text='Text', forum=forum, user=author)


def error_of(resp, field):
    return resp.context['form'].errors[field][0]


# Website


@pytest.mark.django_db
def test_thread_text_over_the_limit_is_refused(client, author, forum):
    client.force_login(author)

    resp = client.post(
        reverse('thread_add', args=[forum.pk]), {'title': 'Long', 'text': 'x' * (TEXT_LIMIT + 1)}
    )

    assert resp.status_code == 200
    assert 'at most 20000 characters' in error_of(resp, 'text')
    assert not Thread.objects.exists()


@pytest.mark.django_db
def test_thread_text_at_the_limit_is_saved(client, author, forum):
    client.force_login(author)

    resp = client.post(
        reverse('thread_add', args=[forum.pk]), {'title': 'Long', 'text': 'x' * TEXT_LIMIT}
    )

    assert resp.status_code == 302
    assert len(Thread.objects.get().text) == TEXT_LIMIT


@pytest.mark.django_db
def test_thread_update_over_the_limit_is_refused(client, author, thread):
    client.force_login(author)

    resp = client.post(
        reverse('thread_update', args=[thread.pk]),
        {'title': thread.title, 'text': 'x' * (TEXT_LIMIT + 1)},
    )

    assert resp.status_code == 200
    assert 'at most 20000 characters' in error_of(resp, 'text')
    thread.refresh_from_db()
    assert thread.text == 'Text'


@pytest.mark.django_db
def test_post_text_over_the_limit_is_refused(client, author, thread):
    client.force_login(author)

    resp = client.post(reverse('post_add', args=[thread.pk]), {'text': 'x' * (TEXT_LIMIT + 1)})

    assert resp.status_code == 200
    assert 'at most 20000 characters' in error_of(resp, 'text')
    assert not Post.objects.exists()


@pytest.mark.django_db
def test_post_text_at_the_limit_is_saved(client, author, thread):
    client.force_login(author)

    resp = client.post(reverse('post_add', args=[thread.pk]), {'text': 'x' * TEXT_LIMIT})

    assert resp.status_code == 302
    assert len(Post.objects.get().text) == TEXT_LIMIT


@pytest.mark.django_db
@pytest.mark.parametrize('length, saved', [(SIGNATURE_LIMIT, True), (SIGNATURE_LIMIT + 1, False)])
def test_signature_limit(client, author, length, saved):
    client.force_login(author)
    profile = author.profile

    resp = client.post(
        reverse('user_profile_edit', args=[profile.pk]),
        {'gender': profile.gender, 'signature': 'x' * length},
    )

    profile.refresh_from_db()
    assert (resp.status_code == 302) is saved
    assert len(profile.signature) == (length if saved else 0)


# Editor preview


@pytest.mark.django_db
def test_preview_over_the_limit_is_refused(client, author):
    client.force_login(author)

    resp = client.post(reverse('markdown_preview'), {'text': 'x' * (TEXT_LIMIT + 1)})

    assert resp.status_code == 400


@pytest.mark.django_db
def test_preview_at_the_limit_is_rendered(client, author):
    client.force_login(author)

    resp = client.post(reverse('markdown_preview'), {'text': 'x' * TEXT_LIMIT})

    assert resp.status_code == 200


# API


@pytest.mark.django_db
def test_api_thread_text_over_the_limit_is_refused(author, forum, get_user_client):
    resp = get_user_client(author).post(
        '/api/threads/', {'title': 'Long', 'text': 'x' * (TEXT_LIMIT + 1), 'forum': forum.pk}
    )

    assert resp.status_code == 400
    assert 'text' in resp.json()
    assert not Thread.objects.exists()


@pytest.mark.django_db
def test_api_post_text_over_the_limit_is_refused(author, thread, get_user_client):
    client = get_user_client(author)

    too_long = client.post('/api/posts/', {'text': 'x' * (TEXT_LIMIT + 1), 'thread': thread.pk})
    at_limit = client.post('/api/posts/', {'text': 'x' * TEXT_LIMIT, 'thread': thread.pk})

    assert too_long.status_code == 400
    assert 'text' in too_long.json()
    assert at_limit.status_code == 201
    assert Post.objects.count() == 1
