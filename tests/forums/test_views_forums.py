import pytest
import json
from rest_framework.test import APIClient
from forums.models import Forum


@pytest.mark.django_db
def test_add_forum(add_super_user, get_user_client):

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.post(
        "/api/forums/",
        json.dumps({"title": "General Forum", "description": "This is a General Forum"}),
        content_type="application/json",
    )

    assert resp.status_code == 201
    assert resp.data["title"] == "General Forum"

    forums = Forum.objects.all()
    assert len(forums) == 1


@pytest.mark.django_db
def test_add_forum_not_logged_in():

    client = APIClient()

    resp = client.post(
        "/api/forums/",
        json.dumps({"title": "General Forum", "description": "This is a General Forum"}),
        content_type="application/json",
    )

    assert resp.status_code == 403

    movies = Forum.objects.all()
    assert len(movies) == 0


@pytest.mark.django_db
def test_add_forum_user_with_no_permissions(add_user, get_user_client):

    user = add_user('user', 'user@email.com', 'testpass123')

    assert not user.is_superuser

    client = get_user_client(user)

    resp = client.post(
        "/api/forums/",
        json.dumps({"title": "General Forum", "description": "This is a General Forum"}),
        content_type="application/json",
    )

    assert resp.status_code == 403

    forums = Forum.objects.all()
    assert len(forums) == 0


@pytest.mark.django_db
def test_remove_forum(add_forum, add_super_user, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.get(f"/api/forums/{forum.id}/")
    assert resp.status_code == 200
    assert resp.data["title"] == "General Forum"

    resp_two = client.delete(f"/api/forums/{forum.id}/")
    assert resp_two.status_code == 204

    forums = Forum.objects.all()
    assert len(forums) == 0


@pytest.mark.django_db
def test_remove_forum_incorrect_id(add_super_user, get_user_client):
    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.delete(f"/api/forums/99/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_update_forum(add_forum, add_super_user, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.put(
        f"/api/forums/{forum.id}/",
        json.dumps({"title": "This is an updated title", "description": "This is an updated description"}),
        content_type="application/json"
    )
    assert resp.status_code == 200
    assert resp.data["title"] == "This is an updated title"
    assert resp.data["description"] == "This is an updated description"

    resp_two = client.get(f"/api/forums/{forum.id}/")
    assert resp_two.status_code == 200
    assert resp.data["title"] == "This is an updated title"
    assert resp.data["description"] == "This is an updated description"


@pytest.mark.django_db
def test_update_forum_incorrect_id(add_super_user, get_user_client):
    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)
    resp = client.put(f"/api/forums/99/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_update_forum_invalid_json(add_forum, add_super_user, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")
    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.put(f"/api/forums/{forum.id}/", {}, content_type="application/json")
    assert resp.status_code == 400
