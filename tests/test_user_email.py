import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError


@pytest.mark.django_db
def test_email_must_be_unique():
    get_user_model().objects.create_user(
        username='first', email='same@example.com', password='testpass123'
    )

    with pytest.raises(IntegrityError):
        get_user_model().objects.create_user(
            username='second', email='same@example.com', password='testpass123'
        )


@pytest.mark.django_db
def test_email_uniqueness_ignores_case():
    get_user_model().objects.create_user(
        username='first', email='same@example.com', password='testpass123'
    )

    with pytest.raises(IntegrityError):
        get_user_model().objects.create_user(
            username='second', email='Same@Example.com', password='testpass123'
        )


@pytest.mark.django_db
def test_email_is_required():
    with pytest.raises(IntegrityError):
        get_user_model().objects.create_user(username='noemail', password='testpass123')
