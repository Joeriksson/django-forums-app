import pytest
from django.urls import reverse

from forums.views import SearchResultsView

SEARCH_URL = reverse('search_results')


@pytest.fixture
def author(add_user):
    return add_user('author', 'author@email.com', 'testpass123')


@pytest.fixture
def forum(add_forum):
    return add_forum(title='General Forum', description='This is a general forum')


def search(client, query):
    resp = client.get(SEARCH_URL, {'q': query})
    assert resp.status_code == 200
    return resp


@pytest.mark.django_db
def test_search_finds_threads_and_posts(client, author, forum, add_thread, add_post):
    thread = add_thread(title='About pelicans', text='Birds', forum=forum, user=author)
    other = add_thread(title='Something else', text='Nothing here', forum=forum, user=author)
    post = add_post(text='I saw a pelican today', thread=other, user=author)

    resp = search(client, 'pelican')

    assert list(resp.context['object_list']) == [post, thread]


@pytest.mark.django_db
@pytest.mark.parametrize('query', ['', ' ', 'pe', ' pe '])
def test_search_needs_three_characters(client, author, forum, add_thread, query):
    add_thread(title='About pelicans', text='Birds', forum=forum, user=author)

    resp = search(client, query)

    assert list(resp.context['object_list']) == []
    assert 'at least 3 characters' in resp.content.decode()


@pytest.mark.django_db
def test_search_shows_the_newest_results_up_to_a_limit(
    client, author, forum, add_thread, add_post, monkeypatch
):
    monkeypatch.setattr(SearchResultsView, 'max_results', 2)
    threads = [
        add_thread(title=f'Pelican {n}', text='Birds', forum=forum, user=author) for n in range(3)
    ]
    posts = [add_post(text=f'pelican post {n}', thread=threads[0], user=author) for n in range(3)]

    resp = search(client, 'pelican')

    # The newest two of each kind; the oldest are left out
    assert list(resp.context['object_list']) == [posts[2], posts[1], threads[2], threads[1]]
    assert 'Only the newest results are shown' in resp.content.decode()


@pytest.mark.django_db
def test_search_within_the_limit_has_no_note(client, author, forum, add_thread):
    add_thread(title='About pelicans', text='Birds', forum=forum, user=author)

    resp = search(client, 'pelican')

    assert 'Only the newest results are shown' not in resp.content.decode()


@pytest.mark.django_db
def test_search_without_results_says_so(client):
    resp = search(client, 'pelican')

    assert "didn't return any results" in resp.content.decode()


@pytest.mark.django_db
def test_search_uses_two_queries_however_many_results(
    client, add_user, forum, add_thread, add_post, django_assert_num_queries
):
    for n in range(3):
        user = add_user(f'user{n}', f'user{n}@email.com', 'testpass123')
        thread = add_thread(title=f'Pelican {n}', text='Birds', forum=forum, user=user)
        add_post(text=f'pelican post {n}', thread=thread, user=user)

    # One for posts, one for threads: their users, threads and forums come along
    with django_assert_num_queries(2):
        search(client, 'pelican')
