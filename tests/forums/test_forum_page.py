import pytest
from django.core.cache import cache
from django.urls import reverse
from pytest_django.asserts import assertContains

from forums.views import ForumDetail

@pytest.fixture
def client(client, reader):
    """Reading needs a login: the pages are requested by a member."""
    client.force_login(reader)
    return client



@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def forum(add_forum):
    return add_forum(title='General Forum', description='This is a general forum')


@pytest.fixture
def five_threads(add_thread, forum, author, monkeypatch):
    """Five threads, oldest first, on pages of two."""
    monkeypatch.setattr(ForumDetail, 'paginate_by', 2)
    return [add_thread(title=f'Thread {n}', text='Text', forum=forum, user=author) for n in range(5)]


def forum_page(client, forum, **params):
    resp = client.get(reverse('forum_detail', args=[forum.pk]), params)
    assert resp.status_code == 200
    return resp


@pytest.mark.django_db
def test_forum_page_shows_the_newest_threads_first(client, forum, five_threads):
    resp = forum_page(client, forum)

    assert list(resp.context['threads']) == [five_threads[4], five_threads[3]]
    content = resp.content.decode()
    assert 'Page 1 of 3' in content
    assert '?page=2' in content


@pytest.mark.django_db
def test_forum_page_last_page_has_the_oldest_thread(client, forum, five_threads):
    resp = forum_page(client, forum, page=3)

    assert list(resp.context['threads']) == [five_threads[0]]
    content = resp.content.decode()
    assert 'Page 3 of 3' in content
    assert '?page=2' in content
    assert '?page=4' not in content


@pytest.mark.django_db
@pytest.mark.parametrize('page, expected', [('abc', 1), ('0', 3), ('999', 3)])
def test_forum_page_with_a_bad_page_number_still_loads(client, forum, five_threads, page, expected):
    resp = forum_page(client, forum, page=page)

    assert resp.context['threads'].number == expected


@pytest.mark.django_db
def test_forum_page_with_one_page_has_no_page_links(client, forum, author, add_thread):
    add_thread(title='Only thread', text='Text', forum=forum, user=author)

    content = forum_page(client, forum).content.decode()

    assert '?page=' not in content


@pytest.mark.django_db
def test_forum_page_counts_a_new_post_at_once(client, forum, author, add_thread, add_post):
    thread = add_thread(title='A thread', text='Text', forum=forum, user=author)
    assertContains(forum_page(client, forum), 'no replies yet')

    add_post(text='A post', thread=thread, user=author)

    assertContains(forum_page(client, forum), '1 reply,')


@pytest.mark.django_db
def test_forum_page_uses_three_queries_however_many_threads(
    client, forum, add_user, add_thread, add_post, django_assert_num_queries
):
    for n in range(3):
        user = add_user(f'user{n}', f'user{n}@email.com', 'testpass123')
        thread = add_thread(title=f'Thread {n}', text='Text', forum=forum, user=user)
        add_post(text='A post', thread=thread, user=user)

    # The forum, the number of threads, and one page of threads with authors and post counts,
    # after six for the logged-in reader (session, user, permissions, profile, GitHub account)
    with django_assert_num_queries(6 + 3):
        forum_page(client, forum)


@pytest.mark.django_db
def test_forum_page_keeps_no_user_data_in_the_cache(client, forum, author, add_thread):
    add_thread(title='A thread', text='Text', forum=forum, user=author)

    forum_page(client, forum)

    assert cache.get(f'thread_objects_forum_{forum.pk}') is None


# The list of forums


@pytest.mark.django_db
def test_forum_list_shows_each_forum_with_its_thread_count(client, forum, author, add_forum, add_thread):
    empty = add_forum(title='Quiet corner', description='Nothing here yet')
    for number in range(2):
        add_thread(title=f'Thread {number}', text='Text', forum=forum, user=author)

    resp = client.get(reverse('forum_list'))

    assertContains(resp, 'General Forum')
    assertContains(resp, 'This is a general forum')
    assertContains(resp, '2 threads')
    assertContains(resp, 'Quiet corner')
    assertContains(resp, 'No threads yet')
    assertContains(resp, f'href="{reverse("forum_detail", args=[empty.pk])}"')


@pytest.mark.django_db
def test_forum_list_counts_one_thread_in_the_singular(client, forum, author, add_thread):
    add_thread(title='Only one', text='Text', forum=forum, user=author)

    assertContains(client.get(reverse('forum_list')), '1 thread<')


@pytest.mark.django_db
def test_forum_list_uses_one_query_however_many_forums(
    client, author, add_forum, add_thread, django_assert_num_queries
):
    for number in range(4):
        add_thread(title='T', text='Text', forum=add_forum(title=f'Forum {number}', description='D'), user=author)

    # The forums with their thread counts, after six for the logged-in reader
    with django_assert_num_queries(6 + 1):
        client.get(reverse('forum_list'))


@pytest.mark.django_db
def test_forum_list_has_a_search_form(client, forum):
    resp = client.get(reverse('forum_list'))

    assertContains(resp, f'action="{reverse("search_results")}"')
    assertContains(resp, 'name="q"')


@pytest.mark.django_db
def test_forum_page_names_the_starter_and_counts_replies(client, forum, author, add_thread, add_post):
    thread = add_thread(title='With replies', text='Text', forum=forum, user=author)
    add_thread(title='Without', text='Text', forum=forum, user=author)
    for _ in range(2):
        add_post(text='A post', thread=thread, user=author)

    resp = forum_page(client, forum)

    assertContains(resp, f'Member {author.pk}')
    assertContains(resp, '2 replies')
    assertContains(resp, 'no replies yet')
