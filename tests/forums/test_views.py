import pytest

from forums.models import Forum


@pytest.mark.xfail(reason='Probably need the test code to login via api and token')
@pytest.mark.django_db
def test_add_forum(client, add_super_user):
    movies = Forum.objects.all()
    assert len(movies) == 0

    super_user = add_super_user('admin', 'admin@email.com', 'testpass123')

    print(super_user.email)
    response = client.login(username=super_user.email, password=super_user.password)
    print(f'Response: {response}')
    assert super_user.is_superuser

    resp = client.post(
        "/api/forums/",
        {"title": "General Forum", "description": "This is a General Forum"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    assert resp.data["title"] == "General Forum"

    movies = Forum.objects.all()
    assert len(movies) == 1
