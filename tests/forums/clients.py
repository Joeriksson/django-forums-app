from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


def reader_client():
    """An API client logged in as a plain member: reading needs a login."""
    reader, _ = get_user_model().objects.get_or_create(
        username='api-reader', defaults={'email': 'api-reader@example.com'}
    )
    client = APIClient()
    client.force_login(reader)
    return client
