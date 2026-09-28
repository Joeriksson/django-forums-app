import pytest
from django.core.cache import cache


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
