import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from forums.models import UserProfile

ADD_URL = reverse('admin:users_customuser_add')


@pytest.fixture
def admin_client(client, db):
    admin = get_user_model().objects.create_superuser(
        username='admin', email='admin@example.com', password='testpass123'
    )
    client.force_login(admin)
    return client


def add_user_data(**overrides):
    data = {
        'username': 'newuser',
        'email': 'newuser@example.com',
        'password1': 'a-strong-pass-123',
        'password2': 'a-strong-pass-123',
    }
    data.update(overrides)
    return data


# Users #4: the add page asks for an email


def test_add_page_shows_email_field(admin_client):
    resp = admin_client.get(ADD_URL)

    assert resp.status_code == 200
    assert 'email' in resp.context['adminform'].form.fields


def test_add_user_saves_email_and_one_profile(admin_client):
    resp = admin_client.post(ADD_URL, add_user_data())

    assert resp.status_code == 302
    user = get_user_model().objects.get(username='newuser')
    assert user.email == 'newuser@example.com'
    assert UserProfile.objects.filter(user=user).count() == 1


def test_add_user_without_email_shows_form_error(admin_client):
    resp = admin_client.post(ADD_URL, add_user_data(email=''))

    assert resp.status_code == 200
    assert 'email' in resp.context['adminform'].form.errors
    assert not get_user_model().objects.filter(username='newuser').exists()


def test_add_user_with_taken_email_shows_form_error(admin_client):
    resp = admin_client.post(ADD_URL, add_user_data(email='Admin@Example.com'))

    assert resp.status_code == 200
    assert resp.context['adminform'].form.errors['email'] == [
        'A user with that email already exists.'
    ]
    assert not get_user_model().objects.filter(username='newuser').exists()


def test_change_user_to_taken_email_shows_form_error(admin_client):
    other = get_user_model().objects.create_user(
        username='other', email='other@example.com', password='testpass123'
    )
    url = reverse('admin:users_customuser_change', args=[other.id])
    data = admin_client.get(url).context['adminform'].form.initial
    data = {k: v for k, v in data.items() if v is not None and k != 'password'}
    data.update(email='ADMIN@example.com', date_joined_0='2026-01-01', date_joined_1='00:00:00')
    data.update({
        'profile-TOTAL_FORMS': '1', 'profile-INITIAL_FORMS': '1',
        'profile-0-id': other.profile.id, 'profile-0-user': other.id,
    })

    resp = admin_client.post(url, data)

    assert resp.status_code == 200
    assert resp.context['adminform'].form.errors['email'] == [
        'A user with that email already exists.'
    ]
    other.refresh_from_db()
    assert other.email == 'other@example.com'


# Users #5: the profile is created by the signal, not the admin


def test_add_page_has_no_profile_inline(admin_client):
    resp = admin_client.get(ADD_URL)

    assert resp.context['inline_admin_formsets'] == []


def test_change_page_profile_inline_cannot_delete(admin_client):
    user = get_user_model().objects.get(username='admin')

    resp = admin_client.get(reverse('admin:users_customuser_change', args=[user.id]))

    formsets = resp.context['inline_admin_formsets']
    assert len(formsets) == 1
    assert formsets[0].formset.can_delete is False
