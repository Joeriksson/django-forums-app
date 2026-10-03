import pytest
from django.core.cache import cache
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from forums.models import UpVote
from forums.views import ThreadDetail

@pytest.fixture
def client(client, reader):
    """Reading needs a login: the pages are requested by a member."""
    client.force_login(reader)
    return client



@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def reader(add_user):
    return add_user('reader', 'reader@email.com', 'testpass123')


@pytest.fixture
def thread(add_forum, add_thread, author):
    forum = add_forum(title='General Forum', description='This is a general forum')
    return add_thread(title='A thread', text='Text', forum=forum, user=author)


@pytest.fixture
def five_posts(add_post, thread, author, monkeypatch):
    """Five posts, oldest first, on pages of two."""
    monkeypatch.setattr(ThreadDetail, 'paginate_by', 2)
    return [add_post(text=f'Post {n}', thread=thread, user=author) for n in range(5)]


def thread_url(thread, page=None):
    url = reverse('thread_detail', args=[thread.pk])
    return f'{url}?page={page}' if page else url


def thread_page(client, thread, page=None):
    resp = client.get(thread_url(thread, page))
    assert resp.status_code == 200
    return resp


@pytest.mark.django_db
def test_thread_page_shows_the_oldest_posts_first(client, thread, five_posts):
    resp = thread_page(client, thread)

    assert list(resp.context['posts']) == five_posts[:2]
    content = resp.content.decode()
    assert 'Page 1 of 3' in content
    assert '?page=2' in content


@pytest.mark.django_db
@pytest.mark.parametrize('page', ['3', 'last'])
def test_thread_page_last_page_has_the_newest_post(client, thread, five_posts, page):
    resp = thread_page(client, thread, page)

    assert list(resp.context['posts']) == five_posts[4:]
    content = resp.content.decode()
    assert 'Page 3 of 3' in content
    assert '?page=2' in content
    assert '?page=4' not in content


@pytest.mark.django_db
@pytest.mark.parametrize('page, expected', [('abc', 1), ('0', 3), ('999', 3)])
def test_thread_page_with_a_bad_page_number_still_loads(client, thread, five_posts, page, expected):
    resp = thread_page(client, thread, page)

    assert resp.context['posts'].number == expected


@pytest.mark.django_db
def test_thread_page_with_one_page_has_no_page_links(client, thread, add_post, author):
    add_post(text='Only post', thread=thread, user=author)

    assert '?page=' not in thread_page(client, thread).content.decode()


@pytest.mark.django_db
def test_new_post_leads_to_the_last_page(client, thread, five_posts, reader):
    client.force_login(reader)

    resp = client.post(reverse('post_add', args=[thread.pk]), {'text': 'The newest post'})

    assertRedirects(resp, thread_url(thread, 'last'))
    posts = list(client.get(resp.url).context['posts'])
    assert [post.text for post in posts] == ['Post 4', 'The newest post']


@pytest.mark.django_db
def test_upvote_returns_to_the_same_page(client, thread, five_posts, reader):
    client.force_login(reader)

    resp = client.post(
        reverse('post_upvote', args=[thread.pk, five_posts[2].pk]), {'page': '2'}
    )

    assertRedirects(resp, thread_url(thread, 2))
    five_posts[2].refresh_from_db()
    assert five_posts[2].upvotes == 1
    # The page shows the new count at once
    assert '1 upvote' in client.get(resp.url).content.decode()


@pytest.mark.django_db
def test_thread_page_marks_the_posts_the_reader_upvoted(client, thread, five_posts, reader, add_user):
    UpVote.objects.create(post=five_posts[0], user=reader)
    # Someone else's vote doesn't count as the reader's
    UpVote.objects.create(post=five_posts[1], user=add_user('other', 'other@email.com', 'pass'))

    resp = thread_page(client, thread)

    assert resp.context['voted'] == {five_posts[0].pk}
    content = resp.content.decode()
    assert content.count('You upvoted') == 1
    assert reverse('post_upvote', args=[thread.pk, five_posts[0].pk]) not in content
    assert reverse('post_upvote', args=[thread.pk, five_posts[1].pk]) in content


@pytest.mark.django_db
def test_thread_page_looks_up_votes_on_its_own_posts_only(client, thread, five_posts, reader):
    UpVote.objects.create(post=five_posts[4], user=reader)

    assert thread_page(client, thread).context['voted'] == set()
    assert thread_page(client, thread, 3).context['voted'] == {five_posts[4].pk}


@pytest.mark.django_db
def test_subscribe_returns_to_the_same_page(client, thread, five_posts, reader):
    client.force_login(reader)

    resp = client.post(reverse('thread_notification', args=[thread.pk]), {'page': '3'})

    assertRedirects(resp, thread_url(thread, 3))


@pytest.mark.django_db
@pytest.mark.parametrize('page', ['', 'abc', '2&next=//evil.example', '-1'])
def test_upvote_ignores_a_page_that_is_not_a_number(client, thread, five_posts, reader, page):
    client.force_login(reader)

    resp = client.post(
        reverse('post_upvote', args=[thread.pk, five_posts[0].pk]), {'page': page}
    )

    assertRedirects(resp, thread_url(thread))


@pytest.mark.django_db
def test_thread_page_has_the_page_number_in_its_forms(client, thread, five_posts, reader):
    client.force_login(reader)

    content = thread_page(client, thread, 2).content.decode()

    # The subscribe form and one upvote form per post on the page
    assert content.count('<input type="hidden" name="page" value="2">') == 3


@pytest.mark.django_db
def test_thread_page_uses_three_queries_however_many_posts(
    client, thread, add_user, add_post, django_assert_num_queries
):
    for n in range(3):
        user = add_user(f'user{n}', f'user{n}@email.com', 'testpass123')
        add_post(text=f'Post {n}', thread=thread, user=user)

    # The thread with its forum and author, the number of posts, one page of posts with
    # authors, the reader's subscription and the reader's upvotes on the page, after six
    # for the logged-in reader (session, user, permissions, profile, GitHub account)
    with django_assert_num_queries(6 + 5):
        thread_page(client, thread)


@pytest.mark.django_db
def test_thread_page_keeps_no_user_data_in_the_cache(client, thread, add_post, author):
    add_post(text='A post', thread=thread, user=author)

    thread_page(client, thread)

    assert cache.get(f'post_objects_thread_{thread.pk}') is None
