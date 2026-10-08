"""
Others see a member's profile name, or "Member <id>": never the username, which
allauth derives from the email address (anna.berg@example.com -> anna.berg).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from forums.models import Forum, Subscription, Post, Thread

User = get_user_model()

@pytest.fixture
def client(client, reader):
    """Reading needs a login: the pages are requested by a member."""
    client.force_login(reader)
    return client



@pytest.fixture
def anna(db):
    return User.objects.create_user(
        username='anna.berg', email='anna.berg@example.com', password='testpass123'
    )


@pytest.fixture
def thread(anna):
    forum = Forum.objects.create(title='Forum', description='Description')
    return Thread.objects.create(title='A thread', text='findable text', forum=forum, user=anna)


@pytest.fixture
def post(thread, anna):
    return Post.objects.create(text='findable reply', thread=thread, user=anna)


def set_name(user, first='', last=''):
    user.profile.first_name, user.profile.last_name = first, last
    user.profile.save()


# The name


def test_display_name_without_profile_name(anna):
    assert anna.display_name == f'Member {anna.pk}'
    assert anna.has_profile_name is False


@pytest.mark.parametrize(
    'first, last, expected',
    [
        ('Anna', 'Berg', 'Anna Berg'),
        ('Anna', '', 'Anna'),
        ('', 'Berg', 'Berg'),
        ('  Anna  ', ' Berg ', 'Anna Berg'),
        # A name must fit on one line: it goes into the subject of notification mails
        ('Anna\nBcc: x@example.com', 'Berg', 'Anna Bcc: x@example.com Berg'),
    ],
)
def test_display_name_from_profile(anna, first, last, expected):
    set_name(anna, first, last)

    assert anna.display_name == expected
    assert anna.has_profile_name is True


def test_blank_profile_name_does_not_count(anna):
    set_name(anna, '   ', '\n')

    assert anna.display_name == f'Member {anna.pk}'
    assert anna.has_profile_name is False


def test_display_name_without_a_profile(anna):
    anna.profile.delete()
    anna = User.objects.get(pk=anna.pk)

    assert anna.display_name == f'Member {anna.pk}'


# Public pages


def public_pages(thread):
    return [
        reverse('forum_detail', args=[thread.forum_id]),
        reverse('thread_detail', args=[thread.pk]),
        reverse('search_results') + '?q=findable',
    ]


def test_pages_show_member_number_not_username(client, anna, thread, post):
    for url in public_pages(thread):
        resp = client.get(url)

        assertContains(resp, f'Member {anna.pk}')
        assertNotContains(resp, 'anna.berg')


def test_pages_show_profile_name(client, anna, thread, post):
    set_name(anna, 'Anna', 'B')

    for url in public_pages(thread):
        resp = client.get(url)

        assertContains(resp, 'Anna B')
        assertNotContains(resp, f'Member {anna.pk}')
        assertNotContains(resp, 'anna.berg')


def test_profile_name_is_escaped(client, anna, thread, post):
    set_name(anna, '<b>Anna</b>')

    for url in public_pages(thread):
        resp = client.get(url)

        assertNotContains(resp, '<b>Anna</b>')
        assertContains(resp, '&lt;b&gt;Anna&lt;/b&gt;')


def test_search_loads_names_without_a_query_per_result(client, anna, thread, django_assert_max_num_queries):
    for number in range(5):
        Post.objects.create(text=f'findable {number}', thread=thread, user=anna)

    # The forums and members for the filters, the number of results, one page of them and
    # the replies on it, seven for the logged-in reader: none per result
    with django_assert_max_num_queries(13):
        client.get(reverse('search_results') + '?q=findable')


# Notification mail


def test_notification_names_the_author_by_display_name(
    anna, thread, verify_email, notification_calls, django_capture_on_commit_callbacks
):
    subscriber = verify_email(
        User.objects.create_user(username='sub', email='sub@example.com', password='x')
    )
    Subscription.objects.create(thread=thread, user=subscriber)

    with django_capture_on_commit_callbacks(execute=True):
        Post.objects.create(text='A reply', thread=thread, user=anna)

    (call,) = notification_calls
    assert call[2] == f'Member {anna.pk}'


# The reminder on the forms


def test_new_thread_and_post_forms_remind_a_member_without_a_name(client, anna, thread):
    client.force_login(anna)
    profile_url = reverse('user_profile_edit', args=[anna.profile.pk])

    for url in (
        reverse('thread_add', args=[thread.forum_id]),
        reverse('post_add', args=[thread.pk]),
    ):
        resp = client.get(url)

        assertContains(resp, f'You are posting as <strong>Member {anna.pk}</strong>', html=False)
        assertContains(resp, f'href="{profile_url}"')


def test_no_reminder_with_a_profile_name(client, anna, thread):
    set_name(anna, 'Anna')
    client.force_login(anna)

    for url in (
        reverse('thread_add', args=[thread.forum_id]),
        reverse('post_add', args=[thread.pk]),
    ):
        assertNotContains(client.get(url), 'You are posting as')


def test_no_reminder_when_editing(client, anna, thread):
    client.force_login(anna)

    assertNotContains(client.get(reverse('thread_update', args=[thread.pk])), 'You are posting as')


# The monogram next to a name


@pytest.mark.parametrize(
    'first, last, expected',
    [
        ('Anna', 'Berg', 'AB'),
        ('anna', 'berg', 'AB'),
        ('Anna', '', 'A'),
        ('Anna Maria', 'von Berg', 'AB'),
        ('Åsa', 'Öberg', 'ÅÖ'),
    ],
)
def test_monogram_from_profile_name(anna, first, last, expected):
    set_name(anna, first, last)

    assert anna.monogram == expected


def test_monogram_without_a_name_is_the_member_number(anna):
    assert anna.monogram == str(anna.pk)


def test_monogram_tone_is_stable_and_one_of_six(anna):
    assert anna.monogram_tone == anna.pk % 6 + 1
    assert 1 <= anna.monogram_tone <= 6
