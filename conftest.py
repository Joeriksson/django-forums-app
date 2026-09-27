import pytest
from django.core.cache import cache


# At the repo root so it also covers the legacy app tests.py suites under pytest
@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()
