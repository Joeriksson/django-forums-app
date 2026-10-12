"""Who to write to: a search among the members, and before it the ones already written with."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains
from rest_framework.throttling import SimpleRateThrottle

from conversations.models import Conversation, send
from conversations.views import MAX_MEMBERS

pytestmark = pytest.mark.django_db

PAGE = reverse('conversation_new')


def add_member(username, first_name='', last_name=''):
    user = get_user_model().objects.create_user(
        username=username, email=f'{username}@example.com', password='testpass123'
    )
    user.profile.first_name = first_name
    user.profile.last_name = last_name
    user.profile.save()
    return user


@pytest.fixture
def anna():
    return add_member('anna', 'Anna', 'Berg')


@pytest.fixture
def as_anna(client, anna):
    client.force_login(anna)
    return client


@pytest.fixture
def members():
    return {
        'bo': add_member('bo', 'Bo', 'Lind'),
        'bodil': add_member('bodil', 'Bodil', 'Ek'),
        'cia': add_member('cia', 'Cecilia', 'Lindgren'),
        'nameless': add_member('zed.zeta'),
    }


def found(resp):
    return resp.context['members']


def search(client, text):
    return client.get(PAGE, {'q': text})


def link(user):
    return f'href="{reverse("conversation", kwargs={"pk": user.pk})}"'


# Before a search


def test_the_page_lists_nobody_until_one_has_conversations(as_anna, members):
    resp = as_anna.get(PAGE)

    assert found(resp) is None
    assert resp.context['known'] == []
    assertContains(resp, 'name="q"')
    for member in members.values():
        assertNotContains(resp, link(member))


def test_the_page_lists_the_members_already_written_with_newest_first(as_anna, anna, members):
    send(anna, members['bo'], 'Hello')
    send(members['cia'], anna, 'Hello')
    send(members['bo'], members['bodil'], 'Not with Anna')

    resp = as_anna.get(PAGE)

    assert resp.context['known'] == [members['cia'], members['bo']]
    assertContains(resp, 'Members you have written with')
    assertContains(resp, link(members['cia']))
    assertNotContains(resp, link(members['bodil']))


def test_a_deactivated_member_is_not_listed_or_found(as_anna, anna, members):
    send(anna, members['bo'], 'Hello')
    members['bo'].is_active = False
    members['bo'].save()

    assert as_anna.get(PAGE).context['known'] == []
    assert found(search(as_anna, 'Bo')) == [members['bodil']]


def test_the_empty_page_costs_one_query(as_anna, anna, members, django_assert_num_queries):
    for member in members.values():
        send(anna, member, 'Hello')
    as_anna.get(PAGE)

    with django_assert_num_queries(8 + 1):
        as_anna.get(PAGE)


def test_looking_and_searching_start_no_conversation(as_anna, members):
    as_anna.get(PAGE)
    search(as_anna, 'Bo')

    assert not Conversation.objects.exists()


# The search


@pytest.mark.parametrize(
    'text, names',
    [
        ('bo', ['bo', 'bodil']),
        ('BO', ['bo', 'bodil']),
        ('lind', ['bo', 'cia']),
        ('bo lind', ['bo']),
        ('lind bo', ['bo']),
        ('  cecilia  ', ['cia']),
        ('ek', ['bodil']),
        ('nobody', []),
        # The username and the address are nobody else's business
        ('zed', []),
        ('zeta', []),
        ('example.com', []),
        # LIKE's wildcards are plain characters
        ('%', []),
        ('_', []),
    ],
)
def test_every_word_must_be_in_the_first_or_last_name(as_anna, members, text, names):
    assert found(search(as_anna, text)) == [members[name] for name in names]


def test_oneself_is_not_found(as_anna, anna, members):
    assert found(search(as_anna, 'Anna')) == []
    assert found(search(as_anna, str(anna.pk))) == []


def test_a_number_finds_that_member(as_anna, members):
    nameless = members['nameless']

    for text in (str(nameless.pk), f'Member {nameless.pk}', f'member  {nameless.pk}'):
        resp = search(as_anna, text)

        assert found(resp) == [nameless]
        assertContains(resp, f'Member {nameless.pk}')
    assertNotContains(resp, 'zed')


def test_a_number_also_fits_a_name_with_that_number(as_anna, members):
    numbered = add_member('numbered', 'Agent', '007')

    assert found(search(as_anna, '007')) == [numbered]


def test_a_number_too_long_for_a_member_finds_nobody(as_anna, members):
    assert found(search(as_anna, '9' * 30)) == []


def test_only_the_word_member_finds_nobody(as_anna, members):
    assert found(search(as_anna, 'member')) == []


def test_a_search_that_finds_nobody_says_so(as_anna, members):
    assertContains(search(as_anna, 'nobody'), 'No member fits that.')


def test_the_field_keeps_what_was_typed_escaped(as_anna, members):
    resp = search(as_anna, '"><b>bo')

    assertContains(resp, 'value="&quot;&gt;&lt;b&gt;bo"')


def test_text_longer_than_the_field_allows_is_refused(as_anna, members):
    resp = search(as_anna, 'b' * 101)

    assert resp.status_code == 200
    assert found(resp) is None
    assert resp.context['form'].errors['q']


def test_members_with_the_same_name_show_their_numbers(as_anna, members):
    twin = add_member('bo2', 'Bo', 'Lind')

    resp = search(as_anna, 'bo lind')

    assert found(resp) == [members['bo'], twin]
    assertContains(resp, f'member {members["bo"].pk}')
    assertContains(resp, f'member {twin.pk}')
    assertNotContains(search(as_anna, 'bodil'), f'member {members["bodil"].pk}')


def test_at_most_twenty_are_shown_with_a_line_asking_for_more(as_anna):
    for n in range(MAX_MEMBERS + 2):
        add_member(f'member{n}', 'Kim', f'Number{n:02}')

    resp = search(as_anna, 'kim')

    assert len(found(resp)) == MAX_MEMBERS == 20
    assert found(resp)[0].profile.last_name == 'Number00'
    assertContains(resp, 'More members fit than are shown.')
    assertNotContains(search(as_anna, 'Number01'), 'More members fit')


def test_a_search_costs_one_query(as_anna, members, django_assert_num_queries):
    search(as_anna, 'lind')

    with django_assert_num_queries(8 + 1):
        search(as_anna, 'lind')


# The limit


def test_searches_over_the_limit_are_refused(as_anna, anna, members, monkeypatch, security_log):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, 'search', '2/min')

    assert [search(as_anna, 'bo').status_code for _ in range(2)] == [200, 200]
    resp = search(as_anna, 'bo')

    assertContains(resp, 'Too many searches.', status_code=429)
    assert found(resp) is None
    assertNotContains(resp, link(members['bo']), status_code=429)
    assert security_log()[-1].startswith(f'denied status=429 user={anna.pk} method=GET')


def test_the_empty_page_does_not_count_and_the_search_page_shares_the_limit(as_anna, members, monkeypatch):
    monkeypatch.setitem(SimpleRateThrottle.THROTTLE_RATES, 'search', '2/min')
    for _ in range(3):
        assert as_anna.get(PAGE).status_code == 200
        assert search(as_anna, '   ').status_code == 200

    assert search(as_anna, 'bo').status_code == 200
    assert as_anna.get(reverse('search_results'), {'q': 'anything'}).status_code == 200
    assert search(as_anna, 'bo').status_code == 429


def test_a_visitor_is_sent_to_the_login_page(client, members):
    resp = search(client, 'bo')

    assert resp.status_code == 302
    assert resp.url.startswith(reverse('account_login'))
