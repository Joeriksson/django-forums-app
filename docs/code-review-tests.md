# Code Review: Test Suite

**Date:** 2026-09-24
**Scope:** Full review of the test suite (not only recent changes)

## Code Review Summary
- **Files Reviewed**:
  - `tests/forums/conftest.py`
  - `tests/forums/test_models.py`
  - `tests/forums/test_serializers.py`
  - `tests/forums/test_views_forums.py`
  - `tests/forums/test_views_posts.py`
  - `tests/forums/test_views_threads.py`
  - `forums/tests.py`, `users/tests.py`, `pages/tests.py`, `api/tests.py` (legacy Django `TestCase` suites)
  - Supporting context read (not reviewed): `forums/models.py`, `forums/views.py`, `forums/signals.py`, `forums/tasks.py`, `forums/urls.py`, `api/views.py`, `api/serializers.py`, `api/permissions.py`, `project/views.py`, `project/__init__.py`, `project/celery.py`, `project/settings/base.py`, `project/settings/test.py`, `pyproject.toml`, `Makefile`, `.github/workflows/django.yml`, `templates/forums/forum_detail.html`
- **Total Issues Found**: 17 (Critical: 2 | Important: 8 | Minor: 7)
- **Overall Assessment**: The pytest API tests are a reasonable start. They check both the HTTP status and the database state, and the new `test_notify_subscribers_excludes_post_author` regression test is a good pattern to copy. The main problems are elsewhere. One test hits the wrong endpoint. Two tests re-assert a stale variable. Most of the legacy tests only check data they created in `setUp`. The suite also has no coverage for the web views' permission logic, cache invalidation, or API ownership rules, which is where the real bugs are.

**What is already good**
- `pages/tests.py` is tidy and focused. `SimpleTestCase` is the right choice for a page with no database access.
- `tests/forums/test_views_forums.py` covers the anonymous, unprivileged, and privileged cases for forum creation, and each test checks the DB row count after the call.
- `tests/forums/test_models.py:80-102` monkeypatches `send_notifications_task.delay` rather than sending real mail, and it explicitly removes `CI` so the code path actually runs.

---

## Critical

### Issue #1: `test_add_post_not_logged_in` posts to the threads endpoint, not the posts endpoint
- **Category**: Best Practice (test correctness)
- **Severity**: Critical
- **Location**: `tests/forums/test_views_posts.py:41-69` (URL on line 55)
- **Explanation**: The test is named and written to check that anonymous users cannot create posts, but it sends the request to `/api/threads/`. That returns 403 because anonymous users cannot create threads. The test passes for the wrong reason, and the Post endpoint's anonymous-write protection (`PostViewSet`, `api/views.py:26-29`) is never tested. If someone relaxed `PostViewSet.permission_classes`, nothing would fail.
- **Current Code**:
```python
    client = APIClient()

    resp = client.post(
        "/api/threads/",
        json.dumps(
            {
                "text": "This is a new reply in a thread",
                "thread": thread.id,
                "user": user.id,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 403
```
- **Improved Version**:
```python
from rest_framework import status

    client = APIClient()

    resp = client.post(
        "/api/posts/",  # was /api/threads/ -- the test never hit the Post endpoint
        {"text": "This is a new reply in a thread", "thread": thread.id, "user": user.id},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert not Post.objects.filter(thread=thread).exists()
```

### Issue #2: API tests send a client-supplied `user` field, and nothing checks that users cannot post as someone else
- **Category**: Security (coverage gap enshrined by tests)
- **Severity**: Critical
- **Location**: `tests/forums/test_views_threads.py:19-24`, `tests/forums/test_views_threads.py:148-154`, `tests/forums/test_views_posts.py:25-29`. Related app code: `api/serializers.py:11,21` (`user` is a writable field), `api/views.py:20-29` (no `perform_create`), `api/permissions.py:10-17` (only object-level, so it is not checked on create)
- **Explanation**: `ThreadSerializer` and `PostSerializer` expose `user` as a normal writable `PrimaryKeyRelatedField`. `IsOwnerOrReadOnly` only implements `has_object_permission`, which DRF does not call on `create`. As a result, any authenticated user can create a thread or post attributed to any other user by sending `"user": <other_id>`. An owner can also reassign their own thread to someone else with PUT. The current tests always send `"user"` in the payload, so they treat this behavior as the intended contract. `test_update_thread_wrong_user` gets a 403 only because the object already belongs to someone else, not because of the spoofed `user` value. Following the project rule, the first step is a failing test that reproduces the problem.
- **Current Code** (`tests/forums/test_views_threads.py:16-29`):
```python
    resp = client.post(
        "/api/threads/",
        json.dumps(
            {
                "title": "A thread in the General Forum",
                "text": "This is a new thread",
                "forum": forum.id,
                "user": user.id,
            }
        ),
        content_type="application/json",
    )

    assert resp.status_code == 201
```
- **Improved Version** (new regression tests; they fail until the serializer or viewset takes `user` from `request.user`, for example with `serializers.HiddenField(default=serializers.CurrentUserDefault())` or `read_only=True` plus `perform_create`):
```python
@pytest.mark.django_db
def test_add_thread_ignores_spoofed_user(add_forum, add_user, get_user_client):
    forum = add_forum("General Forum", "desc")
    author = add_user("author", "author@email.com", "testpass123")
    victim = add_user("victim", "victim@email.com", "testpass123")
    client = get_user_client(author)

    resp = client.post(
        "/api/threads/",
        {"title": "t", "text": "x", "forum": forum.id, "user": victim.id},
        format="json",
    )

    # The thread must be attributed to the authenticated user, never to the id in the payload
    assert resp.status_code == status.HTTP_201_CREATED
    assert Thread.objects.get().user == author


@pytest.mark.django_db
def test_owner_cannot_reassign_thread(add_forum, add_user, add_thread, get_user_client):
    forum = add_forum("General Forum", "desc")
    owner = add_user("owner", "owner@email.com", "testpass123")
    other = add_user("other", "other@email.com", "testpass123")
    thread = add_thread("t", "x", forum, owner)

    get_user_client(owner).put(
        f"/api/threads/{thread.id}/",
        {"title": "t", "text": "x", "forum": forum.id, "user": other.id},
        format="json",
    )

    thread.refresh_from_db()
    assert thread.user == owner
```
Add the same pair of tests for `/api/posts/`.

---

## Important

### Issue #3: Update tests re-assert the PUT response instead of the follow-up GET
- **Category**: Best Practice (weak assertion)
- **Severity**: Important
- **Location**: `tests/forums/test_views_forums.py:117-120`, `tests/forums/test_views_threads.py:124-127`
- **Explanation**: Both tests make a second GET to confirm the change was saved, but then assert on `resp` (the PUT response) instead of `resp_two`. The GET response body is never checked, so the "was it saved?" part of the test does nothing. This looks like a copy-paste slip. Checking the model with `refresh_from_db()` is even more direct.
- **Current Code**:
```python
    resp_two = client.get(f"/api/forums/{forum.id}/")
    assert resp_two.status_code == 200
    assert resp.data["title"] == "This is an updated title"
    assert resp.data["description"] == "This is an updated description"
```
- **Improved Version**:
```python
    resp_two = client.get(f"/api/forums/{forum.id}/")
    assert resp_two.status_code == status.HTTP_200_OK
    assert resp_two.data["title"] == "This is an updated title"          # resp -> resp_two
    assert resp_two.data["description"] == "This is an updated description"

    # Also check the database, not just the serializer output
    forum.refresh_from_db()
    assert forum.title == "This is an updated title"
```
Apply the same fix in `test_views_threads.py:124-127`.

### Issue #4: Legacy tests check the data they created in `setUp`, not application behavior
- **Category**: Best Practice (weak assertions / misleading names)
- **Severity**: Important
- **Location**: `forums/tests.py:24-36` (`test_forum_listing`, `test_thread_listing`, `test_post_listing`), `forums/tests.py:55-59` (`test_forum_create`), `forums/tests.py:90-93` (`test_thread_create`), `forums/tests.py:123-126` (`test_post_create`), `users/tests.py:47-50` (`test_signup_form`), `users/tests.py:75-95` (`test_userprofile_update`)
- **Explanation**: These tests call `Model.objects.create(...)` in `setUp` and then assert the same values back. They are really testing Django's ORM. The names suggest more: `test_forum_create`, `test_thread_create`, and `test_post_create` never call `ForumCreate`, `ThreadCreate`, or `PostCreate`. `test_signup_form` never submits the signup form. `test_userprofile_update` never calls `UserProfileUpdate`. As a result, the actual create and update views, their permission mixins, and `form_valid` (which sets `user` and `forum`/`thread`) have no coverage at all.
- **Current Code** (`forums/tests.py:55-59`):
```python
    def test_forum_create(self):
        self.assertEqual(Forum.objects.all().count(), 1)
        self.assertEqual(Forum.objects.all()[0].title, "General Forum")
        self.assertEqual(
            Forum.objects.all()[0].description, "A forum for general topics"
        )
```
- **Improved Version** (test the view end-to-end):
```python
from django.contrib.auth.models import Permission

    def test_forum_create_view_with_permission(self):
        user = get_user_model().objects.create_user("mod", "mod@email.com", "testpass123")
        user.user_permissions.add(Permission.objects.get(codename="add_forum"))
        self.client.force_login(user)

        resp = self.client.post(
            reverse("forum_add"), {"title": "New Forum", "description": "Desc"}
        )

        self.assertRedirects(resp, reverse("forum_list"))
        self.assertTrue(Forum.objects.filter(title="New Forum").exists())

    def test_post_create_view_sets_author_and_thread(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            reverse("post_add", args=(self.thread.id,)), {"text": "Reply"}
        )
        self.assertRedirects(resp, reverse("thread_detail", args=(self.thread.id,)))
        post = Post.objects.get(text="Reply")
        self.assertEqual(post.user, self.user)       # set by form_valid, not the form
        self.assertEqual(post.thread, self.thread)
```

### Issue #5: `client.login()` results are never checked, so "logged-in" tests may run anonymously
- **Category**: Best Practice (flakiness / silent failure)
- **Severity**: Important
- **Location**: `forums/tests.py:113`, `users/tests.py:68`
- **Explanation**: `Client.login()` returns `False` on failure instead of raising. The two call sites use different credentials: an email in `forums/tests.py:113`, which only works through allauth's email backend, and a username in `users/tests.py:68`, which only works through `ModelBackend`. Any change to `AUTHENTICATION_BACKENDS` or the allauth settings would silently log out one of these tests. `ThreadDetail` renders for anonymous users too, so `ThreadDetailPageTests` would keep passing. `force_login` skips authentication backends and makes the test's intent explicit.
- **Current Code** (`forums/tests.py:112-115`):
```python
        url = reverse('thread_detail', args=(self.thread.id,))
        self.client.login(username='forumuser@email.com', password='testpass123')

        self.response = self.client.get(url)
```
- **Improved Version**:
```python
        url = reverse('thread_detail', args=(self.thread.id,))
        self.client.force_login(self.user)  # deterministic, independent of auth backends

        self.response = self.client.get(url)
        # Prove the logged-in branch ran (ThreadDetail adds these only for authenticated users)
        assert 'subscribed' in self.response.context
```

### Issue #6: The notification/Celery path runs differently in CI and locally, and there is no suite-wide isolation
- **Category**: Best Practice (flakiness / environment coupling)
- **Severity**: Important
- **Location**: `forums/models.py:77-98` (`if not os.environ.get('CI')`), `project/__init__.py:4-6` (the Celery app is loaded only when `CI` is unset), `project/settings/base.py:305-306` (`CELERY_ALWAYS_EAGER`), `project/settings/test.py` (no Celery override). Affected tests include every test that creates a `Post`: `tests/forums/test_views_posts.py:10-38`, `forums/tests.py:18-22`, `forums/tests.py:108-110`.
- **Explanation**: GitHub Actions sets `CI=true`, so in CI `Post.notify_subscribers` is a no-op for every test. Locally and in `make dev_pytest`, `CI` is unset, so each `Post.objects.create` runs `send_notifications_task.delay(...)` through the real Celery app. Whether that call runs eagerly or goes to the Redis broker depends on `CELERY_ALWAYS_EAGER`. The Celery app is configured with `namespace='CELERY'` (`project/celery.py:7`), and Celery's documented namespaced name for this setting is `CELERY_TASK_ALWAYS_EAGER`. I have not run the suite to confirm whether Celery honors the older name here. Either way, the same test can hit different code paths, or need a running Redis, depending on where it runs. That is a classic source of "passes in CI, fails locally" problems. A suite-wide autouse fixture removes the ambiguity. Only `test_notify_subscribers_excludes_post_author` does this today, and only for itself.
- **Current Code** (`tests/forums/test_models.py:96-97`, the only isolation in the suite):
```python
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.setattr('forums.tasks.send_notifications_task.delay', fake_delay)
```
- **Improved Version** (move to `tests/conftest.py` so every pytest test gets it; also add `CELERY_TASK_ALWAYS_EAGER = True` and `CELERY_TASK_EAGER_PROPAGATES = True` to `project/settings/test.py` as a safety net):
```python
# tests/conftest.py
import pytest


@pytest.fixture(autouse=True)
def notification_calls(monkeypatch):
    """Run notify_subscribers the same way everywhere and record calls instead of queuing tasks."""
    calls = []
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(
        "forums.tasks.send_notifications_task.delay",
        lambda *args, **kwargs: calls.append(args),
    )
    return calls
```
Tests that care about notifications can then request `notification_calls` and assert on it directly.

### Issue #7: The cache is never cleared between tests
- **Category**: Best Practice (test isolation / xdist)
- **Severity**: Important
- **Location**: `project/settings/test.py:10-14` (`LocMemCache`), `forums/views.py:41-50` and `forums/views.py:98-107` (views cache querysets by pk). No fixture or `setUp` clears the cache.
- **Explanation**: `LocMemCache` is per process, so pytest-xdist workers do not share it. That part is fine. But the cache does persist across tests within one worker, and the `TestCase`/`django_db` transaction rollback does not clear it. Today, isolation depends on PostgreSQL sequences not being reset on rollback, so pks are rarely reused. As soon as someone adds `reset_sequences=True`, uses `TransactionTestCase`, hard-codes a pk, or writes the missing cache-invalidation tests (see Coverage Gaps), results will depend on test order and on which tests land on which worker.
- **Current Code**: none. No cache reset exists anywhere in `tests/` or the legacy suites.
- **Improved Version**:
```python
# tests/conftest.py
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()
```
For the legacy `TestCase` classes, add `cache.clear()` in `setUp` or in a shared base class.

### Issue #8: `test_user_profile_model` has assertions that cannot fail and misses the real behavior
- **Category**: Best Practice (weak assertion)
- **Severity**: Important
- **Location**: `tests/forums/test_models.py:72-77`
- **Explanation**: The test builds an unsaved `UserProfile` in memory and asserts that it is truthy (always true for model instances) and that `gender` equals the value just passed in. The interesting behavior is that `forums/signals.py:9-20` automatically creates a profile when a user is created, with `gender` defaulting to `NOTPROVIDED`. That is never tested directly. The test also lacks `@pytest.mark.django_db`. It only works because the local `create_user` fixture happens to depend on `db`.
- **Current Code**:
```python
def test_user_profile_model(create_user):
    user = create_user(username='palle')
    user_profile = UserProfile(user=user, gender='F')

    assert user_profile
    assert user_profile.gender == 'F'
```
- **Improved Version**:
```python
from forums.models import Gender


@pytest.mark.django_db
def test_user_profile_created_by_signal(add_user):
    user = add_user('palle', 'palle@email.com', 'testpass123')

    # post_save signal (forums/signals.py) should create exactly one profile
    assert UserProfile.objects.filter(user=user).count() == 1
    assert user.profile.gender == Gender.NOTPROVIDED

    user.save()  # save_user_profile runs again; it must not create a duplicate
    assert UserProfile.objects.filter(user=user).count() == 1
```

### Issue #9: The legacy and pytest suites overlap, and CI runs them through two different runners
- **Category**: Readability / Maintainability
- **Severity**: Important
- **Location**: `tests/forums/test_models.py:7-35` duplicates `forums/tests.py:7-36` and `forums/tests.py:55-59`; `tests/forums/test_models.py:65-69` duplicates `users/tests.py:9-18`; `.github/workflows/django.yml:57-58`; `pyproject.toml:40`
- **Explanation**: The same model facts (forum and thread fields, `is_staff`/`is_superuser` on new users) are asserted in both suites. CI runs `manage.py test --parallel`, which only picks up the legacy `TestCase` classes, and then `pytest tests/`. Meanwhile `pyproject.toml:40` includes `tests.py` in `python_files`, so a bare `pytest` from the repo root would also collect the legacy files. That means "the test suite" means different things depending on how you run it. Two suites double the maintenance cost and make coverage harder to reason about.
- **Current Code** (`.github/workflows/django.yml:56-58`):
```yaml
      run: |
        uv run python manage.py test --settings=project.settings.test --parallel
        uv run pytest tests/ -v --disable-warnings
```
- **Improved Version** (incremental: pytest-django runs `TestCase` classes natively, so use one runner, then migrate the legacy files into `tests/` over time and delete the duplicates):
```yaml
      run: |
        uv run pytest -v --disable-warnings   # collects tests/ AND legacy */tests.py via pyproject python_files
```
Then delete `test_forum_model`, `test_thread_model`, and `test_user_model` from `tests/forums/test_models.py` (or the legacy equivalents), keeping one copy of each check.

### Issue #10: Factory fixtures force every test to repeat the same 10 to 15 lines of setup
- **Category**: Readability / Best Practice (fixture design)
- **Severity**: Important
- **Location**: `tests/forums/conftest.py:8-78`. The repeated setup appears in `tests/forums/test_views_threads.py:11-14, 38-39, 64-71, 96-104, 132-142, 171-178`, `tests/forums/test_views_posts.py:11-18, 43-50`, and `tests/forums/test_serializers.py:36-37, 60-61, 77-81, 97-101`.
- **Explanation**: Every fixture returns a factory that takes positional arguments, so each test rebuilds the same forum, user, and thread with the same literal strings. That hides what is actually different in each test. Other problems:
  - `get_user_client` calls `Token.objects.create`, so calling it twice for the same user raises `IntegrityError` because `Token.user` is a OneToOne field.
  - `scope="function"` is the default and adds noise.
  - The fixtures live in `tests/forums/conftest.py`, so a future `tests/api/` or `tests/users/` package cannot use them.

  Moving them to `tests/conftest.py` and adding simple composed fixtures, while keeping the factories for the unusual cases, fixes all of this.
- **Current Code** (`tests/forums/conftest.py:65-78`, plus the repeated setup in each test):
```python
@pytest.fixture(scope="function")
def get_user_client():
    def _get_user_client(user):

        token = Token.objects.create(
            user=user,
        )
```
- **Improved Version** (`tests/conftest.py`):
```python
@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("user", "user@email.com", "testpass123")


@pytest.fixture
def forum(db):
    return Forum.objects.create(title="General Forum", description="This is a general forum")


@pytest.fixture
def thread(forum, user):
    return Thread.objects.create(title="A thread", text="Thread text", forum=forum, user=user)


@pytest.fixture
def get_user_client():
    def _get_user_client(user):
        token, _ = Token.objects.get_or_create(user=user)  # safe to call repeatedly
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client
    return _get_user_client


@pytest.fixture
def user_client(get_user_client, user):
    return get_user_client(user)
```
With these, `test_remove_thread` shrinks to `def test_remove_thread(thread, user_client): ...`.

---

## Minor

### Issue #11: `add_super_user` does not create a real superuser
- **Category**: Best Practice
- **Severity**: Minor
- **Location**: `tests/forums/conftest.py:51-62`
- **Explanation**: `create_user(..., is_superuser=True)` leaves `is_staff=False`. That is enough for `DjangoModelPermissionsOrAnonReadOnly`, but `IsAdminUser` (used by `UserViewSet`, `api/views.py:33`) checks `is_staff`. A future `/api/users/` test using this fixture would get an unexpected 403. `create_superuser` sets both flags.
- **Current Code**:
```python
        super_user = get_user_model().objects.create_user(
            username=username,
            email=email,
            password=password,
            is_superuser=True,
        )
```
- **Improved Version**:
```python
        super_user = get_user_model().objects.create_superuser(
            username=username, email=email, password=password  # sets is_staff and is_superuser
        )
```

### Issue #12: `test_models.py` redefines user fixtures and requests unused ones
- **Category**: Readability
- **Severity**: Minor
- **Location**: `tests/forums/test_models.py:8` (`add_forum` requested but unused), `tests/forums/test_models.py:38-62` (`test_password`, `test_email`, `create_user` duplicate `conftest.add_user`), `tests/forums/test_models.py:16-24` (builds a user inline instead of using the fixture)
- **Explanation**: Three different ways to create a user in one file make it harder to see which one is canonical. The module-level string at line 38 is a no-op expression, not a docstring.
- **Current Code**:
```python
@pytest.mark.django_db
def test_forum_model(add_forum):
    forum = Forum(title='Test Forum', description='This is a Test Forum')
    forum.save()
```
- **Improved Version**:
```python
@pytest.mark.django_db
def test_forum_str(add_forum):
    forum = add_forum('Test Forum', 'This is a Test Forum')
    assert str(forum) == 'Forum: Test Forum'   # the only non-trivial behavior of Forum
```
Then delete the `test_password`, `test_email`, and `create_user` fixtures and use `add_user`.

### Issue #13: Serializer tests contain misleading inputs, dead comments, and unused fixtures
- **Category**: Readability
- **Severity**: Minor
- **Location**: `tests/forums/test_serializers.py:85` (`'forum'` is not a `PostSerializer` field and is silently ignored), `tests/forums/test_serializers.py:50-55, 88, 121-122` (commented-out code), `tests/forums/test_serializers.py:114, 127` (`add_user` requested but unused), `tests/forums/test_serializers.py:96-101` (`thread` created but unused)
- **Explanation**: Passing a field the serializer does not declare suggests to readers that it matters. The commented-out blocks copy old serializer code and will drift out of date. `test_valid_post_serializer` also only checks `is_valid()` and `errors`, not `validated_data`.
- **Current Code**:
```python
    valid_serializer_data = {
        'text': 'A General Forum',
        'thread': thread.id,
        'forum': forum.id,
        'user': user.id,
    }
    # 'id', 'text', 'thread', 'upvotes', 'user', 'user_name', 'added', 'edited'
    serializer = PostSerializer(data=valid_serializer_data)

    assert serializer.is_valid()
    assert serializer.errors == {}
```
- **Improved Version**:
```python
    serializer = PostSerializer(data={'text': 'A reply', 'thread': thread.id, 'user': user.id})

    assert serializer.is_valid(), serializer.errors  # show errors on failure
    assert serializer.validated_data['thread'] == thread
    assert serializer.validated_data['text'] == 'A reply'
```

### Issue #14: The notification test does not check that the task was called or what it was called with
- **Category**: Best Practice
- **Severity**: Minor
- **Location**: `tests/forums/test_models.py:91-102`
- **Explanation**: `captured.get('email_addresses', [])` defaults to an empty list, so the first assertion passes even if `delay` was never called. The second assertion does catch that case, but the test does not check the call count, `thread_id`, or the URL. A regression that queued two tasks, or pointed at the wrong thread, would still pass.
- **Current Code**:
```python
    assert 'author@example.com' not in captured.get('email_addresses', [])
    assert 'subscriber@example.com' in captured.get('email_addresses', [])
```
- **Improved Version**:
```python
    calls = []
    monkeypatch.setattr('forums.tasks.send_notifications_task.delay',
                        lambda *args: calls.append(args))

    Post.objects.create(text='A reply', thread=thread, user=author)

    assert len(calls) == 1
    thread_id, thread_title, username, full_url, email_addresses = calls[0]
    assert thread_id == thread.id
    assert full_url.endswith(f'/forums/thread/{thread.id}')
    assert email_addresses == ['subscriber@example.com']  # exact list: no author, no duplicates
```

### Issue #15: Magic status codes, manual `json.dumps`, and copy-paste variable names
- **Category**: Readability
- **Severity**: Minor
- **Location**: `tests/forums/test_views_forums.py:43-44` (`movies` holds forums), `tests/forums/test_views_threads.py:82-83` (`forums` holds threads), and bare `201`/`403`/`404` throughout `tests/forums/test_views_*.py`
- **Explanation**: `APIClient` accepts `format="json"`, so `json.dumps(...)` plus `content_type=...` is unnecessary. `rest_framework.status` constants make failures self-explanatory. Leftover names like `movies` from a tutorial make readers stop and wonder whether something is wrong.
- **Current Code**:
```python
    assert resp.status_code == 403

    movies = Forum.objects.all()
    assert len(movies) == 0
```
- **Improved Version**:
```python
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert not Forum.objects.exists()   # also avoids loading rows just to count them
```

### Issue #16: Dead test file and unused imports
- **Category**: Readability
- **Severity**: Minor
- **Location**: `api/tests.py:1-3` (empty placeholder), `forums/tests.py:2` (`Client` unused), `forums/tests.py:4` (`resolve` unused)
- **Explanation**: The empty `api/tests.py` suggests the API is untested, when it is actually tested under `tests/forums/`. Unused imports add noise and trigger linters.
- **Current Code**:
```python
from django.test import TestCase, Client
from .models import Forum, Thread, Post
from django.urls import reverse, resolve
```
- **Improved Version**:
```python
from django.test import TestCase
from django.urls import reverse

from .models import Forum, Thread, Post
```
Delete `api/tests.py`, or move the API tests from `tests/forums/test_views_*.py` into a `tests/api/` package, since they test the API rather than forum views.

### Issue #17: Coverage configuration hides the `pages` app entirely
- **Category**: Best Practice
- **Severity**: Minor
- **Location**: `pyproject.toml:55` (`"pages/*"` in `omit`)
- **Explanation**: Omitting `pages/*` removes `pages/views.py` from coverage reports as well as `pages/tests.py`. The other omit entries (`*tests/*`, `forums/tests.py`, `users/tests.py`) show the intent was to exclude test files, so `pages/tests.py` is what should be listed.
- **Current Code**:
```toml
    "pages/*",
    "users/tests.py",
```
- **Improved Version**:
```toml
    "pages/tests.py",   # exclude the tests, keep pages/views.py measured
    "users/tests.py",
```

---

## Coverage Gaps

These are untested areas that I confirmed by reading the app code. Several of them hide real bugs, which are noted.

1. **Web view permissions (none tested)**
   - `ForumCreate` (`forums/views.py:57-77`): anonymous users should be redirected. Instead, `login_url = ''` makes `get_login_url()` raise `NotImplementedError`, so anonymous users get a 500 on `/forums/add/`.
   - `ThreadUpdate.test_func` (`forums/views.py:130`) checks `forums.update_thread`, which is not a Django default permission (the default is `change_thread`), so the moderator override can never succeed. Add a test that gives a non-owner `change_thread` and expects 200.
   - `ThreadDelete` and `PostDelete` (`forums/views.py:164-223`): owner, non-owner (403), and holder of `delete_*` permission.
   - `UserProfileUpdate` (`project/views.py:9-22`): editing another user's profile should redirect to `home`. `users/tests.py:66` asserts only `302` without checking the target, and both branches currently redirect to `home`.
2. **State-changing GET endpoints**
   - `PostUpvote` (`forums/views.py:226-237`): repeated GETs by the same user increment `upvotes` without limit. A missing post raises `Post.DoesNotExist`, which becomes a 500 instead of a 404.
   - `ThreadNotification` (`forums/views.py:240-257`): toggling on and off. A missing thread also gives a 500.
3. **Cache invalidation (none tested)**
   - Creating, updating, or deleting a `Thread` should clear `thread_objects_forum_<id>`, and the same for `Post` with `post_objects_thread_<id>` (`forums/models.py:52-56, 120-124`).
   - Bug: `ForumDetail` caches threads together with their prefetched `posts`, and the template shows `{{ thread.posts.all.count }}` (`templates/forums/forum_detail.html:40`). `Post` hooks only invalidate `post_objects_thread_*`, so post counts on the forum page go stale after a reply. A test that loads the forum page, adds a post, and reloads would catch this. It needs Issue #7's cache fixture.
4. **Notification task**
   - `send_notifications_task` itself (`forums/tasks.py:11-26`) is never run. Call it directly and assert on `django.core.mail.outbox` (subject, BCC list).
   - The case with no subscribers: `notify_subscribers` still calls `.delay` with an empty list.
   - The welcome email hook (`users/models.py:10-22`) is also untested and could be covered with a `mail.outbox` assertion.
5. **API permissions**
   - Not tested:
     - PUT, PATCH, or DELETE on `/api/posts/<id>/` by a non-owner
     - DELETE on `/api/threads/<id>/` by a non-owner
     - Anonymous GET on list and detail endpoints (should be 200)
     - `/api/users/` (`IsAdminUser`): anonymous, regular, and staff users
     - A non-superuser staff member granted `forums.add_forum` (should be 201)
   - The spoofed `user` field is covered in Issue #2.
6. **Search** (`forums/views.py:260-275`): empty query, matches in posts versus threads, and case-insensitivity.

---

## Quick Wins

1. **Fix the three false-confidence assertions.** Point `test_add_post_not_logged_in` at `/api/posts/` (`tests/forums/test_views_posts.py:55`) and change `resp` to `resp_two` in `tests/forums/test_views_forums.py:119-120` and `tests/forums/test_views_threads.py:126-127`. This is a five-line change that makes three existing tests actually verify what their names say.
2. **Add the failing API impersonation tests (Issue #2).** Once the serializer takes `user` from `request.user`, they will pass and protect against a real security hole: any authenticated user can currently create threads and posts as someone else.
3. **Add a root `tests/conftest.py` with autouse `clear_cache` and `notification_calls` fixtures (Issues #6 and #7).** This makes behavior identical in CI and locally, removes the hidden dependency on Celery and Redis, and is required before any cache-invalidation tests can be reliable.
