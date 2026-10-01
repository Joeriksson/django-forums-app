import pytest
from django.urls import reverse

from forums.models import Gender


def profile_data(**overrides):
    data = {
        'first_name': 'First',
        'last_name': 'Last',
        'bio': '',
        'location': '',
        'gender': Gender.NOTPROVIDED,
        'web_site': '',
        'github_url': '',
        'signature': '',
    }
    data.update(overrides)
    return data


@pytest.fixture
def owner(add_user):
    return add_user('owner', 'owner@email.com', 'testpass123')


@pytest.mark.django_db
def test_anonymous_user_is_sent_to_login(client, owner):
    url = reverse('user_profile_edit', args=(owner.profile.id,))

    resp = client.get(url)

    assert resp.status_code == 302
    assert resp.url == f"{reverse('account_login')}?next={url}"


@pytest.mark.django_db
def test_other_user_gets_403_and_profile_is_unchanged(client, owner, add_user):
    other = add_user('other', 'other@email.com', 'testpass123')
    client.force_login(other)
    url = reverse('user_profile_edit', args=(owner.profile.id,))

    assert client.get(url).status_code == 403
    assert client.post(url, profile_data(first_name='Hacked')).status_code == 403
    owner.profile.refresh_from_db()
    assert owner.profile.first_name == ''


@pytest.mark.django_db
def test_owner_can_edit_profile(client, owner):
    client.force_login(owner)
    url = reverse('user_profile_edit', args=(owner.profile.id,))

    assert client.get(url).status_code == 200
    resp = client.post(url, profile_data(first_name='Owner'))

    assert resp.status_code == 302
    owner.profile.refresh_from_db()
    assert owner.profile.first_name == 'Owner'


@pytest.mark.django_db
def test_missing_profile_returns_404(client, owner):
    client.force_login(owner)

    resp = client.get(reverse('user_profile_edit', args=(99999,)))

    assert resp.status_code == 404


@pytest.mark.django_db
def test_url_without_scheme_is_saved_as_https(client, owner):
    client.force_login(owner)
    url = reverse('user_profile_edit', args=(owner.profile.id,))

    resp = client.post(url, profile_data(web_site='example.com', github_url='github.com/owner'))

    assert resp.status_code == 302
    owner.profile.refresh_from_db()
    assert owner.profile.web_site == 'https://example.com'
    assert owner.profile.github_url == 'https://github.com/owner'


@pytest.mark.django_db
def test_url_with_http_scheme_is_kept(client, owner):
    client.force_login(owner)
    url = reverse('user_profile_edit', args=(owner.profile.id,))

    client.post(url, profile_data(web_site='http://example.com'))

    owner.profile.refresh_from_db()
    assert owner.profile.web_site == 'http://example.com'
