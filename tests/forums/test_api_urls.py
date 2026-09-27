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
