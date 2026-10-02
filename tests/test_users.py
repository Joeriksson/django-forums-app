import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects, assertTemplateUsed


@pytest.mark.django_db
def test_create_user():
    user = get_user_model().objects.create_user(
        username='julle', email='test2@test.com', password='testpass123'
    )

    assert user.username == 'julle'
    assert user.email == 'test2@test.com'
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_create_superuser():
    admin_user = get_user_model().objects.create_superuser(
        username='superjulle', email='supertest2@test.com', password='testpass123'
    )

    assert admin_user.is_active
    assert admin_user.is_staff
    assert admin_user.is_superuser


@pytest.mark.django_db
def test_signup_page(client):
    resp = client.get(reverse('account_signup'))

    assert resp.status_code == 200
    assertTemplateUsed(resp, 'account/signup.html')
    assertContains(resp, 'Sign Up')


@pytest.mark.django_db
def test_signup_form_asks_only_for_email_and_one_password(client):
    resp = client.get(reverse('account_signup'))

    fields = set(re.findall(r'<input[^>]*name="([^"]+)"', resp.content.decode()))
    assert fields - {'csrfmiddlewaretoken'} == {'email', 'password1'}


@pytest.mark.django_db
def test_signup_creates_user(client):
    resp = client.post(
        reverse('account_signup'),
        {'email': 'newuser@email.com', 'password1': 'a-long-test-pass-123'},
    )

    # Not logged in yet: the address must be confirmed first (test_email_verification.py)
    assertRedirects(resp, reverse('account_email_verification_sent'))
    user = get_user_model().objects.get(email='newuser@email.com')
    assert user.check_password('a-long-test-pass-123')
