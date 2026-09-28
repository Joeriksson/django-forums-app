import pytest
from django.urls import reverse
from rest_framework.test import APIClient


def test_api_login_url_has_slash_after_prefix():
    assert reverse('rest_framework:login') == '/api/api-auth/login/'
    assert reverse('rest_framework:logout') == '/api/api-auth/logout/'


@pytest.mark.django_db
def test_api_login_page_loads():
    resp = APIClient().get('/api/api-auth/login/')

    assert resp.status_code == 200


@pytest.mark.django_db
def test_schema_endpoint_describes_the_api():
    client = APIClient()

    yaml_resp = client.get('/api/schema/')
    json_resp = client.get('/api/schema/', {'format': 'openapi-json'})

    assert yaml_resp.status_code == 200
    assert yaml_resp.content.decode().startswith('openapi:')
    assert json_resp.status_code == 200
    paths = json_resp.json()['paths']
    for path in ('/api/forums/', '/api/threads/', '/api/posts/'):
        assert path in paths
