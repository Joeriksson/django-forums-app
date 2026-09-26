import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def users(add_user):
    staff = add_user('staff', 'staff@email.com', 'testpass123')
    staff.is_staff = True
    staff.save()
    superuser = get_user_model().objects.create_superuser(
        username='admin', email='admin@email.com', password='testpass123'
    )
    member = add_user('member', 'member@email.com', 'testpass123')
    return {'staff': staff, 'superuser': superuser, 'member': member}


# Staff can look users up


@pytest.mark.django_db
def test_staff_can_list_users(get_user_client, users):
    client = get_user_client(users['staff'])

    resp = client.get('/api/users/')

    assert resp.status_code == 200
    assert {u['username'] for u in resp.data['results']} == {'staff', 'admin', 'member'}


@pytest.mark.django_db
def test_staff_can_read_a_user(get_user_client, users):
    client = get_user_client(users['staff'])

    resp = client.get(f"/api/users/{users['member'].id}/")

    assert resp.status_code == 200
    assert resp.data['username'] == 'member'


# Nobody can change users through the API


@pytest.mark.django_db
def test_staff_cannot_create_user(get_user_client, users):
    client = get_user_client(users['staff'])

    resp = client.post(
        '/api/users/',
        {'username': 'newuser', 'email': 'new@email.com'},
        format='json',
    )

    assert resp.status_code == 405
    assert not get_user_model().objects.filter(username='newuser').exists()


@pytest.mark.django_db
@pytest.mark.parametrize('method', ['put', 'patch'])
def test_staff_cannot_change_superuser_email(get_user_client, users, method):
    superuser = users['superuser']
    client = get_user_client(users['staff'])

    resp = getattr(client, method)(
        f'/api/users/{superuser.id}/',
        {'username': 'admin', 'email': 'attacker@email.com'},
        format='json',
    )

    assert resp.status_code == 405
    superuser.refresh_from_db()
    assert superuser.email == 'admin@email.com'


@pytest.mark.django_db
def test_staff_cannot_delete_user(get_user_client, users):
    member = users['member']
    client = get_user_client(users['staff'])

    resp = client.delete(f'/api/users/{member.id}/')

    assert resp.status_code == 405
    assert get_user_model().objects.filter(id=member.id).exists()


# Non-staff can't see users


@pytest.mark.django_db
def test_non_staff_cannot_list_users(get_user_client, users):
    client = get_user_client(users['member'])

    resp = client.get('/api/users/')

    assert resp.status_code == 403


@pytest.mark.django_db
def test_anonymous_cannot_list_users(users):
    resp = APIClient().get('/api/users/')

    assert resp.status_code in (401, 403)
