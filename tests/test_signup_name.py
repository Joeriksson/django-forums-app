"""
Signup asks for the name others will see, so a new member isn't "Member <id>"; the
profile form doesn't let the first name be removed again.
"""

import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from forums.models import Gender
from users.models import Invitation

pytestmark = pytest.mark.django_db

EMAIL = 'new@example.com'
PASSWORD = 'a-long-test-pass-123'


def sign_up(client, **names):
    return client.post(reverse('account_signup'), {'email': EMAIL, 'password1': PASSWORD, **names})


def new_member():
    return get_user_model().objects.select_related('profile').get(email=EMAIL)


# Signup


def test_the_fields_come_between_the_address_and_the_password(client):
    main = client.get(reverse('account_signup')).content.decode().split('<main', 1)[1]

    fields = re.findall(r'<input[^>]*name="([^"]+)"', main)
    assert [name for name in fields if name != 'csrfmiddlewaretoken'] == [
        'email',
        'first_name',
        'last_name',
        'password1',
    ]
    assert 'First name' in main and 'Last name' in main
    # So nobody types a name without knowing where it shows
    assert 'Others see your first and last name next to what you write.' in main


def test_signup_saves_the_name_to_the_profile(client):
    resp = sign_up(client, first_name='Anna', last_name='Berg')

    assert resp.status_code == 302
    member = new_member()
    assert (member.profile.first_name, member.profile.last_name) == ('Anna', 'Berg')
    assert member.display_name == 'Anna Berg'
    assert member.has_profile_name


def test_the_last_name_is_optional(client):
    assert sign_up(client, first_name='Anna').status_code == 302

    assert new_member().display_name == 'Anna'


@pytest.mark.parametrize('first_name', [None, '', '   '])
def test_signup_without_a_first_name_is_refused(client, first_name):
    names = {} if first_name is None else {'first_name': first_name}

    resp = sign_up(client, last_name='Berg', **names)

    assert resp.status_code == 200
    assert resp.context['form'].errors['first_name']
    assert not get_user_model().objects.exists()


def test_names_are_trimmed_and_at_most_100_characters(client):
    resp = sign_up(client, first_name='x' * 101)
    assert resp.context['form'].errors['first_name']
    resp = sign_up(client, first_name='Anna', last_name='x' * 101)
    assert resp.context['form'].errors['last_name']
    assert not get_user_model().objects.exists()

    sign_up(client, first_name='  Anna ', last_name=' Berg  ')

    assert new_member().display_name == 'Anna Berg'


def test_a_name_is_shown_escaped(client):
    sign_up(client, first_name='<b>Anna</b>', last_name='& co')
    member = new_member()
    client.force_login(member)

    html = client.get(reverse('home')).content.decode()

    assert '&lt;b&gt;Anna&lt;/b&gt; &amp; co' in html
    assert '<b>Anna</b>' not in html


def test_an_invited_signup_asks_for_the_name_too(client, settings):
    settings.SIGNUP_OPEN = False
    invitation = Invitation.objects.create(email=EMAIL)
    client.get(reverse('accept_invitation', args=[invitation.key]))

    assert sign_up(client).context['form'].errors['first_name']
    assert sign_up(client, first_name='Anna', last_name='Berg').status_code == 302

    assert new_member().display_name == 'Anna Berg'


def test_the_labels_are_translated(client, settings):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sv'

    main = client.get(reverse('account_signup')).content.decode().split('<main', 1)[1]

    assert 'Förnamn' in main and 'Efternamn' in main


# The profile form


@pytest.fixture
def member():
    user = get_user_model().objects.create_user(username='m', email='m@example.com', password='x')
    user.profile.first_name = 'Anna'
    user.profile.save()
    return user


def save_profile(client, member, **fields):
    data = {
        'first_name': 'Anna',
        'last_name': '',
        'bio': '',
        'location': '',
        'gender': Gender.NOTPROVIDED,
        'web_site': '',
        'github_url': '',
        'signature': '',
        **fields,
    }
    return client.post(reverse('user_profile_edit', args=[member.profile.pk]), data)


def test_the_first_name_cannot_be_removed(client, member):
    client.force_login(member)

    resp = save_profile(client, member, first_name='  ')

    assert resp.status_code == 200
    assert resp.context['form'].errors['first_name']
    member.profile.refresh_from_db()
    assert member.profile.first_name == 'Anna'


def test_the_name_can_be_changed_and_the_last_name_left_out(client, member):
    client.force_login(member)

    assert save_profile(client, member, first_name='Annika').status_code == 302

    member.profile.refresh_from_db()
    assert (member.profile.first_name, member.profile.last_name) == ('Annika', '')


def test_a_member_without_a_name_must_give_one_to_save_the_profile(client):
    nameless = get_user_model().objects.create_user(username='n', email='n@example.com', password='x')
    client.force_login(nameless)

    assert save_profile(client, nameless, first_name='', signature='Hi').status_code == 200
    assert save_profile(client, nameless, first_name='Nils', signature='Hi').status_code == 302

    nameless.profile.refresh_from_db()
    assert (nameless.profile.first_name, nameless.profile.signature) == ('Nils', 'Hi')


def test_an_account_made_without_signup_still_has_no_name():
    user = get_user_model().objects.create_superuser(username='root', email='root@example.com', password='x')

    assert user.display_name == f'Member {user.pk}'
