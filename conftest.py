import pytest
from django.core.cache import cache


# At the repo root so it also covers the legacy app tests.py suites under pytest
@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# Same notification path in CI and locally: CI unset, task recorded instead of queued
@pytest.fixture(autouse=True)
def notification_calls(monkeypatch):
    calls = []
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.setattr(
        'forums.tasks.send_notifications_task.delay', lambda *args: calls.append(args)
    )
    return calls
