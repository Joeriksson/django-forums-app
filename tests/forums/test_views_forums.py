import pytest
from rest_framework import status
from rest_framework.test import APIClient
from forums.models import Forum


@pytest.mark.django_db
def test_add_forum(add_super_user, get_user_client):

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.post(
        "/api/forums/",
        {"title": "General Forum", "description": "This is a General Forum"},
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["title"] == "General Forum"

    assert Forum.objects.count() == 1


@pytest.mark.django_db
def test_add_forum_not_logged_in():

    client = APIClient()

    resp = client.post(
        "/api/forums/",
        {"title": "General Forum", "description": "This is a General Forum"},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN

    assert Forum.objects.count() == 0


@pytest.mark.django_db
def test_add_forum_user_with_no_permissions(add_user, get_user_client):

    user = add_user('user', 'user@email.com', 'testpass123')

    assert not user.is_superuser

    client = get_user_client(user)

    resp = client.post(
        "/api/forums/",
        {"title": "General Forum", "description": "This is a General Forum"},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN

    assert Forum.objects.count() == 0


@pytest.mark.django_db
def test_remove_forum(add_forum, add_super_user, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.get(f"/api/forums/{forum.id}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["title"] == "General Forum"

    resp_two = client.delete(f"/api/forums/{forum.id}/")
    assert resp_two.status_code == status.HTTP_204_NO_CONTENT

    assert Forum.objects.count() == 0


@pytest.mark.django_db
def test_remove_forum_incorrect_id(add_super_user, get_user_client):
    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)
    resp = client.delete("/api/forums/99/")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_update_forum(add_forum, add_super_user, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.put(
        f"/api/forums/{forum.id}/",
        {
            "title": "This is an updated title",
            "description": "This is an updated description",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["title"] == "This is an updated title"
    assert resp.data["description"] == "This is an updated description"

    resp_two = client.get(f"/api/forums/{forum.id}/")
    assert resp_two.status_code == status.HTTP_200_OK
    assert resp_two.data["title"] == "This is an updated title"
    assert resp_two.data["description"] == "This is an updated description"


@pytest.mark.django_db
def test_update_forum_incorrect_id(add_super_user, get_user_client):
    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)
    resp = client.put("/api/forums/99/")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_update_forum_invalid_json(add_forum, add_super_user, get_user_client):
    forum = add_forum(title="General Forum", description="This is a general forum")
    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')
    client = get_user_client(super_user)

    resp = client.put(f"/api/forums/{forum.id}/", {}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
