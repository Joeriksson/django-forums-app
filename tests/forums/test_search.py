"""
The search page: English word forms (PostgreSQL full-text search), filters for forum,
author, dates and kind, sorting, and every result in pages.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from forums.models import Post, Thread
from forums.views import SearchView

SEARCH_URL = reverse('search_results')


@pytest.fixture
def client(client, reader):
    """Reading needs a login: the pages are requested by a member."""
    client.force_login(reader)
    return client


@pytest.fixture
def anna(add_user):
    return add_user('anna', 'anna@example.com', 'x')


@pytest.fixture
def bo(add_user):
    return add_user('bo', 'bo@example.com', 'x')


@pytest.fixture
def house(add_forum):
    return add_forum('The house', 'Repairs')


@pytest.fixture
def trips(add_forum):
    return add_forum('Trips', 'Where to')


def search(client, **params):
    resp = client.get(SEARCH_URL, params)
    assert resp.status_code == 200
    return resp


def found(resp):
    return list(resp.context['results'])


def days_ago(obj, days):
    obj.__class__.objects.filter(pk=obj.pk).update(added=timezone.now() - timedelta(days=days))
    obj.refresh_from_db()
    return obj


# Words


@pytest.mark.django_db
def test_finds_threads_and_replies(client, anna, house, add_thread, add_post):
    thread = add_thread('About pelicans', 'Birds', house, anna)
    other = add_thread('Something else', 'Nothing here', house, anna)
    post = add_post('I saw a pelican today', other, anna)

    assert set(found(search(client, q='pelican'))) == {thread, post}


@pytest.mark.django_db
def test_finds_english_word_forms(client, anna, house, add_thread, add_post):
    thread = add_thread('Tomatoes', 'I watered the beds every morning', house, anna)
    post = add_post('A watering can is enough', thread, anna)

    assert set(found(search(client, q='water'))) == {thread, post}


@pytest.mark.django_db
def test_quoted_words_are_a_phrase(client, anna, house, add_thread):
    exact = add_thread('Valves', 'Buy one that is normally closed', house, anna)
    add_thread('Doors', 'Closed doors are normally locked', house, anna)

    assert found(search(client, q='"normally closed"')) == [exact]


@pytest.mark.django_db
def test_minus_leaves_a_word_out(client, anna, house, add_thread):
    sensor = add_thread('Watering', 'A valve with a sensor', house, anna)
    add_thread('Watering, simpler', 'A valve with a timer', house, anna)

    assert found(search(client, q='valve -timer')) == [sensor]


@pytest.mark.django_db
def test_best_match_puts_titles_first(client, anna, house, add_thread, add_post):
    other = add_thread('Something else', 'Nothing here', house, anna)
    in_text = add_post('Someone mentioned a pelican', other, anna)
    in_title = days_ago(add_thread('Pelican', 'Birds', house, anna), 3)

    assert found(search(client, q='pelican')) == [in_title, in_text]


@pytest.mark.django_db
def test_newest_first_when_asked(client, anna, house, add_thread, add_post):
    other = add_thread('Something else', 'Nothing here', house, anna)
    in_text = add_post('Someone mentioned a pelican', other, anna)
    days_ago(add_thread('Pelican', 'Birds', house, anna), 3)

    assert found(search(client, q='pelican', sort='newest'))[0] == in_text


@pytest.mark.django_db
@pytest.mark.parametrize('query', ['', ' ', 'pe', ' pe '])
def test_words_need_three_characters_without_a_filter(client, anna, house, add_thread, query):
    add_thread('About pelicans', 'Birds', house, anna)

    resp = search(client, q=query, sort='best')

    assert resp.context['results'] is None
    assertContains(resp, 'at least 3 characters')


@pytest.mark.django_db
def test_page_without_anything_shows_only_the_form(client):
    resp = search(client)

    assert resp.context['results'] is None
    assertContains(resp, 'name="q"')
    assertNotContains(resp, 'at least 3 characters')
    assertNotContains(resp, 'Nothing found')


@pytest.mark.django_db
def test_without_results_says_so(client):
    assertContains(search(client, q='pelican'), 'Nothing found')


# Filters


@pytest.mark.django_db
def test_forum_filter(client, anna, house, trips, add_thread):
    roof = add_thread('Roof water', 'Text', house, anna)
    add_thread('Lake water', 'Text', trips, anna)

    assert found(search(client, q='water', forum=house.pk)) == [roof]


@pytest.mark.django_db
def test_author_filter(client, anna, bo, house, add_thread, add_post):
    thread = add_thread('Roof water', 'Text', house, anna)
    reply = add_post('More water', thread, bo)

    assert found(search(client, q='water', author=bo.pk)) == [reply]


@pytest.mark.django_db
def test_date_filter(client, anna, house, add_thread):
    old = days_ago(add_thread('Old water', 'Text', house, anna), 40)
    recent = days_ago(add_thread('Recent water', 'Text', house, anna), 5)
    days_ago(add_thread('Today water', 'Text', house, anna), 0)
    today = timezone.localdate()

    resp = search(
        client, q='water', since=(today - timedelta(days=10)).isoformat(),
        until=(today - timedelta(days=1)).isoformat(),
    )

    assert found(resp) == [recent]
    assert old not in found(resp)


@pytest.mark.django_db
def test_dates_the_wrong_way_round_are_an_error(client):
    resp = search(client, q='water', since='2026-10-02', until='2026-10-01')

    assert resp.context['results'] is None
    assertContains(resp, 'The end date is before the start date')


@pytest.mark.django_db
@pytest.mark.parametrize('kind, expected', [('threads', 'thread'), ('replies', 'post')])
def test_kind_filter(client, anna, house, add_thread, add_post, kind, expected):
    thread = add_thread('Water', 'Text', house, anna)
    post = add_post('More water', thread, anna)

    assert found(search(client, q='water', kind=kind)) == [{'thread': thread, 'post': post}[expected]]


@pytest.mark.django_db
def test_filters_without_words_list_everything_newest_first(client, anna, bo, house, add_thread, add_post):
    first = days_ago(add_thread('Roof', 'Text', house, anna), 2)
    reply = add_post('Hm', first, anna)
    add_thread('Keys', 'Text', house, bo)

    assert found(search(client, author=anna.pk)) == [reply, first]


@pytest.mark.django_db
def test_forum_list_shows_plain_titles(client, house):
    assertContains(search(client), f'<option value="{house.pk}">The house</option>')


@pytest.mark.django_db
def test_author_list_names_members_and_tells_twins_apart(client, anna, bo, add_user):
    for user in (anna, bo):
        user.profile.first_name, user.profile.last_name = 'Anna', 'Berg'
        user.profile.save()

    content = search(client).content.decode()

    assert f'<option value="{anna.pk}">Anna Berg (member {anna.pk})</option>' in content
    assert f'<option value="{bo.pk}">Anna Berg (member {bo.pk})</option>' in content
    assert 'anna@example.com' not in content


# Results


@pytest.mark.django_db
def test_results_come_in_pages_that_keep_the_search(client, anna, house, add_thread, monkeypatch):
    monkeypatch.setattr(SearchView, 'paginate_by', 2)
    for number in range(3):
        add_thread(f'Water {number}', 'Text', house, anna)

    resp = search(client, q='water', forum=house.pk, sort='newest')

    assert len(found(resp)) == 2
    content = resp.content.decode()
    assert content.count('aria-label="Pages of results"') == 2
    link = re.search(r'<a href="(\?[^"]*page=2[^"]*)">', content).group(1).replace('&amp;', '&')
    assert 'q=water' in link and f'forum={house.pk}' in link and 'sort=newest' in link

    assert len(found(search(client, q='water', forum=house.pk, sort='newest', page=2))) == 1


@pytest.mark.django_db
def test_reply_links_to_its_page_and_number(client, anna, house, add_thread, add_post, site_settings):
    site_settings(posts_per_page=2)
    thread = add_thread('Roof', 'Text', house, anna)
    posts = [add_post(f'Reply {n}', thread, anna) for n in range(4)]
    target = posts[3]
    Post.objects.filter(pk=target.pk).update(text='The pelican came back')

    content = search(client, q='pelican').content.decode()

    # The fourth reply is post #5, on the second page of two replies each
    url = reverse('thread_detail', args=[thread.pk])
    assert f'href="{url}?page=2#post-{target.pk}"' in content
    assert '#5' in content


@pytest.mark.django_db
def test_excerpt_is_plain_text_and_escaped(client, anna, house, add_thread):
    add_thread('Pelicans', '**Bold** pelican <script>alert(1)</script>', house, anna)

    # Without words: the start of the text, unmarked
    content = search(client, forum=house.pk).content.decode()

    assert 'Bold pelican &lt;script&gt;alert(1)&lt;/script&gt;' in content
    assert '<script>alert' not in content
    assert '**Bold**' not in content


@pytest.mark.django_db
def test_search_box_escapes_the_query(client):
    content = search(client, q='"><b>x').content.decode()

    assert 'value="&quot;&gt;&lt;b&gt;x"' in content


@pytest.mark.django_db
def test_query_count_does_not_grow_with_results(
    client, add_user, house, add_thread, add_post, django_assert_num_queries
):
    for number in range(3):
        user = add_user(f'user{number}', f'user{number}@example.com', 'x')
        thread = add_thread(f'Pelican {number}', 'Birds', house, user)
        add_post(f'pelican post {number}', thread, user)

    # The forums and members for the filters, the number of results, one page of them,
    # and the threads and replies on it, after seven for the logged-in reader
    with django_assert_num_queries(7 + 6):
        search(client, q='pelican')


# Addresses


def test_search_url():
    assert SEARCH_URL == '/search/'


@pytest.mark.django_db
def test_old_address_keeps_the_query(client):
    resp = client.get('/forums/search/', {'q': 'pelican'})

    assertRedirects(resp, f'{SEARCH_URL}?q=pelican', fetch_redirect_response=False)


# Highlighting the matched words


@pytest.mark.django_db
def test_matched_word_forms_are_marked(client, anna, house, add_thread):
    add_thread('Watering the beds', 'I watered them every morning before work.', house, anna)

    resp = search(client, q='water')

    content = resp.content.decode()
    assert '<mark>watered</mark>' in content
    # Titles are shown as typed
    assert '>Watering the beds</a>' in content


@pytest.mark.django_db
def test_excerpt_is_taken_around_the_match(client, anna, house, add_thread):
    before = ' '.join(f'early{number}' for number in range(80))
    after = ' '.join(f'late{number}' for number in range(80))
    add_thread('Long one', f'{before} the pelican arrived {after}', house, anna)

    content = search(client, q='pelican').content.decode()

    assert 'the <mark>pelican</mark> arrived' in content
    assert 'early0 early1' not in content


@pytest.mark.django_db
def test_marked_excerpt_is_escaped(client, anna, house, add_thread):
    add_thread('Pelicans', '**Bold** pelican <script>alert(1)</script>', house, anna)

    content = search(client, q='pelican').content.decode()

    # ts_headline drops what looks like tags; whatever it keeps is escaped
    assert '<mark>pelican</mark>' in content
    assert '<script>alert' not in content


@pytest.mark.django_db
def test_markup_kept_in_an_excerpt_is_escaped(client, anna, house, add_thread):
    add_thread('Pelicans', 'A pelican &lt;img src=x onerror=alert(1)&gt; and 1 < 2', house, anna)

    # The page's own part: the header's language menu has flag images
    content = search(client, q='pelican').content.decode().split('<main', 1)[1]

    assert '<img' not in content
    assert '<mark>pelican</mark>' in content


@pytest.mark.django_db
def test_marker_characters_typed_by_a_member_make_no_tags(client, anna, house, add_thread):
    from forums.search import START, STOP

    add_thread('Odd one', f'A pelican and {START}evil{STOP} text', house, anna)

    content = search(client, q='pelican').content.decode()

    assert content.count('<mark>') == 1
    assert '<mark>pelican</mark>' in content
    assert START not in content and STOP not in content


@pytest.mark.django_db
def test_title_is_shown_as_typed_and_escaped(client, anna, house, add_thread):
    add_thread('<b>Pelican</b> news', 'Text', house, anna)

    content = search(client, q='pelican').content.decode()

    assert '>&lt;b&gt;Pelican&lt;/b&gt; news</a>' in content


@pytest.mark.django_db
def test_search_without_words_marks_nothing(client, anna, house, add_thread):
    add_thread('Pelican', 'The start of the text', house, anna)

    content = search(client, forum=house.pk).content.decode()

    assert '<mark>' not in content
    assert 'The start of the text' in content


# The filters fold away on small screens


def filters_tag(resp):
    return re.search(r'<details class="search-form__more"[^>]*>', resp.content.decode()).group(0)


@pytest.mark.django_db
def test_filters_start_folded_without_filters(client):
    resp = search(client, q='pelican')

    assert ' open' not in filters_tag(resp)
    assertContains(resp, '<summary>Filters</summary>')


@pytest.mark.django_db
def test_filters_start_open_and_counted_when_used(client, house):
    resp = search(client, q='pelican', forum=house.pk, kind='threads')

    assert ' open' in filters_tag(resp)
    assertContains(resp, '<summary>Filters (2)</summary>')


@pytest.mark.django_db
def test_search_page_loads_its_script(client):
    assertContains(search(client), 'js/search.js')
