import pytest
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from tests.forums.clients import reader_client


@pytest.mark.django_db  # the 404 page names the site from SiteSettings
def test_api_has_no_login_page_of_its_own():
    # DRF's login view would skip the two-factor step: log in on the site instead
    with pytest.raises(NoReverseMatch):
        reverse('rest_framework:login')
    assert APIClient().get('/api/api-auth/login/').status_code == 404


@pytest.mark.django_db
def test_browsable_api_page_loads_without_login_link():
    resp = reader_client().get('/api/forums/', HTTP_ACCEPT='text/html')

    assert resp.status_code == 200


@pytest.mark.django_db
def test_schema_endpoint_describes_the_api():
    client = reader_client()

    yaml_resp = client.get('/api/schema/')
    json_resp = client.get('/api/schema/', {'format': 'openapi-json'})

    assert yaml_resp.status_code == 200
    assert yaml_resp.content.decode().startswith('openapi:')
    assert json_resp.status_code == 200
    paths = json_resp.json()['paths']
    for path in ('/api/forums/', '/api/threads/', '/api/posts/'):
        assert path in paths
