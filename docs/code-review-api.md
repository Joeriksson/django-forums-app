# Code Review: `api/` App

**Date:** 2026-09-24
**Scope:** Full review of every non-migration Python file in `api/` (`views.py`, `serializers.py`, `urls.py`, `permissions.py`, `tests.py`, `admin.py`, `models.py`, `apps.py`, `__init__.py`). `forums/models.py`, `users/models.py`, `project/settings/base.py` and `tests/forums/` were read for context only.

## Code Review Summary

- **Files Reviewed**: `api/views.py`, `api/serializers.py`, `api/urls.py`, `api/permissions.py`, `api/tests.py`, `api/admin.py`, `api/models.py`, `api/apps.py`, `api/__init__.py`
- **Total Issues Found**: 12 (Critical: 2 | Important: 4 | Minor: 6)
- **Overall Assessment**: The app is small and easy to read. It uses DRF idioms (ModelViewSet, router, composed permissions) and turns on pagination and authentication globally. The two main risks are the serializers and the nesting. Ownership fields (`user`) and derived fields (`upvotes`) are client-writable, so any authenticated user can post as someone else. The nested Forum -> Thread -> Post serializers cause unbounded payloads and N+1 queries on the list endpoints.

### What is already done well

- The Thread and Post serializers expose `user` only as a primary key, so no email or other personal data leaks from the public (read-only for anonymous users) endpoints.
- `UserSerializer`, which includes `email` and `last_login`, is only reachable through `UserViewSet`, and that viewset is behind `IsAdminUser` (`api/views.py:33`).
- Global `PageNumberPagination` with `PAGE_SIZE = 10` (`project/settings/base.py:205-206`) keeps the top-level list endpoints bounded.
- `IsOwnerOrReadOnly & IsAuthenticatedOrReadOnly` (`api/views.py:21`, `api/views.py:27`) combines permissions correctly. Anonymous writes are rejected at `has_permission`, and non-owners are rejected at `has_object_permission`.

---

## Critical

### Issue #1: `user` is client-writable on Thread and Post, allowing impersonation and ownership takeover

- **Category**: Security
- **Severity**: Critical
- **Location**: `api/serializers.py:11`, `api/serializers.py:21`; `api/views.py:20-29`
- **Explanation**: `ModelSerializer` makes a ForeignKey in `fields` a writable `PrimaryKeyRelatedField`. Neither serializer marks `user` as read-only, and neither viewset sets `user` from `request.user`. This causes two problems:
  1. **Create**: `IsOwnerOrReadOnly.has_object_permission` never runs on `POST` to a list endpoint, because no object exists yet. Any authenticated user can send `{"user": <victim_id>, ...}` and the thread or post is saved under the victim's name. This also sets off the `notify_subscribers` hook and sends emails that claim the victim wrote the post (`forums/models.py:77-98`).
  2. **Update**: The permission check runs against the *existing* owner. The owner can then `PATCH {"user": <other_id>}` and move the object to another user. The owner loses the ability to edit it, and the object now appears under someone else's name.

  The existing tests (`tests/forums/test_views_threads.py:16-27`) send `"user": user.id` explicitly, so this contract is being exercised rather than caught.
- **Current Code**:
```python
# api/serializers.py
class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')

class ThreadSerializer(serializers.ModelSerializer):
    posts = PostSerializer(many=True, read_only=True)

    class Meta:
        model = Thread
        fields = ('id', 'title', 'text', 'forum', 'user', 'posts', 'added', 'edited')

# api/views.py
class ThreadViewSet(viewsets.ModelViewSet):
    permission_classes = (IsOwnerOrReadOnly & IsAuthenticatedOrReadOnly,)
    queryset = Thread.objects.all().order_by('-added')
    serializer_class = ThreadSerializer
```
- **Improved Version**:
```python
# api/serializers.py
class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
        # Ownership and bookkeeping fields are set by the server, never by the client.
        read_only_fields = ('user', 'upvotes', 'added', 'edited')

class ThreadSerializer(serializers.ModelSerializer):
    ...
    class Meta:
        model = Thread
        fields = ('id', 'title', 'text', 'forum', 'user', 'posts', 'added', 'edited')
        read_only_fields = ('user', 'added', 'edited')

# api/views.py
class ThreadViewSet(viewsets.ModelViewSet):
    ...
    def perform_create(self, serializer):
        # The author is always the authenticated caller.
        serializer.save(user=self.request.user)

class PostViewSet(viewsets.ModelViewSet):
    ...
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
```
  DRF silently ignores read-only fields in the input, so the existing tests that send `"user"` will keep passing. Add a regression test that posts `"user": <other_user_id>` and asserts that `resp.data["user"] == request_user.id`.

### Issue #2: Unbounded nested serializers cause N+1 queries and very large payloads

- **Category**: Performance
- **Severity**: Critical
- **Location**: `api/serializers.py:15`, `api/serializers.py:25`; `api/views.py:16`, `api/views.py:22`
- **Explanation**: `ForumSerializer` nests `ThreadSerializer(many=True)`, which nests `PostSerializer(many=True)`, and neither viewset prefetches anything. The results:
  - `GET /api/forums/` (one page of 10 forums) runs 1 query for the page, 1 for the count, 1 query per forum for its threads, and 1 query per thread for its posts. That is `2 + F + T` queries, where T is the number of threads in those forums, which may be thousands.
  - `GET /api/threads/` runs `2 + 10` queries per page (one `posts` query per thread).
  - The nested lists are **not paginated**. One forum response includes every thread in that forum and every post in each thread, including the full Markdown `text`. As the forum grows, response size and serialization time grow without limit, and a single anonymous request can put heavy load on the database and web worker (a denial-of-service risk).
- **Current Code**:
```python
# api/serializers.py
class ThreadSerializer(serializers.ModelSerializer):
    posts = PostSerializer(many=True, read_only=True)
    ...

class ForumSerializer(serializers.ModelSerializer):
    threads = ThreadSerializer(many=True, read_only=True)
    ...

# api/views.py
class ForumViewSet(viewsets.ModelViewSet):
    queryset = Forum.objects.all().order_by('title')

class ThreadViewSet(viewsets.ModelViewSet):
    queryset = Thread.objects.all().order_by('-added')
```
- **Improved Version** (quick fix: remove the N+1 and keep the current response shape):
```python
# api/views.py
class ForumViewSet(viewsets.ModelViewSet):
    # Three queries total per page (forums, threads, posts), whatever the row counts.
    queryset = Forum.objects.prefetch_related('threads__posts')

class ThreadViewSet(viewsets.ModelViewSet):
    queryset = Thread.objects.prefetch_related('posts')
```
  **Improved Version** (structural fix, recommended: stop nesting unbounded collections and return counts instead):
```python
# api/serializers.py
class ForumSerializer(serializers.ModelSerializer):
    thread_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Forum
        fields = ('id', 'title', 'description', 'thread_count')

class ThreadListSerializer(serializers.ModelSerializer):
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Thread
        fields = ('id', 'title', 'forum', 'user', 'post_count', 'added', 'edited')
        read_only_fields = ('user', 'added', 'edited')

# api/views.py
from django.db.models import Count

class ForumViewSet(viewsets.ModelViewSet):
    queryset = Forum.objects.annotate(thread_count=Count('threads'))
    serializer_class = ForumSerializer

class ThreadViewSet(viewsets.ModelViewSet):
    ...
    def get_queryset(self):
        qs = Thread.objects.annotate(post_count=Count('posts'))
        if self.action == 'retrieve':
            qs = qs.prefetch_related('posts')
        return qs

    def get_serializer_class(self):
        # Compact list view; full nested posts only on detail.
        return ThreadListSerializer if self.action == 'list' else ThreadSerializer
```
  Clients that need a forum's threads or a thread's posts should get them through the paginated `/api/threads/?forum=<id>` and `/api/posts/?thread=<id>` endpoints (add a `filterset_fields` or a `get_queryset` filter). This changes the API contract, so check for consumers first. The `localhost:3000` CORS entry suggests there may be a frontend client.

---

## Important

### Issue #3: `upvotes` is client-writable

- **Category**: Security / Best Practice
- **Severity**: Important
- **Location**: `api/serializers.py:11`
- **Explanation**: `upvotes` is a denormalized counter that should only change through the upvote flow (the `UpVote` model and the web `PostUpvote` view). Because it is a writable field, anyone can create a post with `"upvotes": 100000`, and the owner can `PATCH` it at any time. The counter then disagrees with the `UpVote` rows, and ranking or reputation based on it can no longer be trusted.
- **Current Code**:
```python
fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
```
- **Improved Version**:
```python
fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
read_only_fields = ('user', 'upvotes', 'added', 'edited')  # same change as Issue #1
```

### Issue #4: Owners can move posts between threads and threads between forums

- **Category**: Best Practice / Security
- **Severity**: Important
- **Location**: `api/serializers.py:11` (`thread`), `api/serializers.py:21` (`forum`)
- **Explanation**: `thread` and `forum` must be writable on create, but they stay writable on update too. A post owner can `PATCH {"thread": <any_id>}` to move their post into an unrelated thread. The subscribers of that thread are not notified, and the post appears out of context. A thread owner can move a thread into any forum. The web UI does not allow either action, so the API is more permissive than the application intends. The cache invalidation hooks also clear only the *new* `thread_id`/`forum_id` key (`forums/models.py:55-56`, `forums/models.py:123-124`), so the old thread or forum cache keeps serving stale data.
- **Current Code**:
```python
class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
```
- **Improved Version**:
```python
class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
        read_only_fields = ('user', 'upvotes', 'added', 'edited')

    def validate_thread(self, value):
        # Allow setting the thread on create only; reject moving an existing post.
        if self.instance is not None and value != self.instance.thread:
            raise serializers.ValidationError('A post cannot be moved to another thread.')
        return value

# Same pattern for ThreadSerializer.validate_forum.
```

### Issue #5: API permissions for Thread and Post ignore moderator model permissions, unlike the web views

- **Category**: Best Practice / Security (authorization consistency)
- **Severity**: Important
- **Location**: `api/views.py:21`, `api/views.py:27`; `api/permissions.py:10-17`
- **Explanation**: Setting `permission_classes` replaces the global `DjangoModelPermissionsOrAnonReadOnly` (`project/settings/base.py:197-199`). The web views allow "owner **or** has `forums.delete_thread` / `forums.change_thread`" (see CLAUDE.md URL table), but the API allows **only** the owner. Moderators and staff cannot moderate through the API, so the two interfaces enforce different authorization rules. A rule change made in one place is easy to forget in the other.

  *Assumption*: moderators are expected to have the same powers in the API as in the web UI. If the API is intentionally owner-only, document that in the permission class instead.
- **Current Code**:
```python
class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user
```
- **Improved Version**:
```python
class IsOwnerOrModeratorOrReadOnly(permissions.BasePermission):
    """
    Read for everyone; write for the object's `user` or for users holding
    the matching Django model permission (e.g. forums.change_post).
    """
    perms_map = {
        'PUT': 'change', 'PATCH': 'change', 'DELETE': 'delete',
    }

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if obj.user_id == request.user.id:  # compare ids, avoids loading the user row
            return True
        action = self.perms_map.get(request.method)
        opts = obj._meta
        return bool(action) and request.user.has_perm(
            f'{opts.app_label}.{action}_{opts.model_name}'
        )
```

### Issue #6: `UserViewSet` is a full read/write `ModelViewSet` with no password handling, and staff can rewrite anyone's email

- **Category**: Security
- **Severity**: Important
- **Location**: `api/views.py:32-35`; `api/serializers.py:33-54`
- **Explanation**:
  - `IsAdminUser` checks `is_staff`, not `is_superuser`. Any staff member can `PATCH /api/users/<superuser_id>/ {"email": "attacker@..."}`, then use the password reset flow on that address and take over the superuser account. This is a staff-to-superuser privilege escalation. Changing `email` here also skips allauth's `EmailAddress` verification.
  - `POST /api/users/` creates a `CustomUser` without going through `set_password`. `password` is not among the serializer fields, so the user is saved with an empty password, bypasses allauth's signup and email verification, and still sets off the `send_welcome_mail` hook (`users/models.py:10-22`).
  - `DELETE /api/users/<id>/` cascades to every thread, post, upvote and notification of that user (`on_delete=CASCADE` in `forums/models.py`), with no confirmation step.

  *Assumption*: the endpoint exists so admins can look up users. If write access is needed, it should go through a dedicated serializer with explicit password and email handling.
- **Current Code**:
```python
class UserViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAdminUser,)
    queryset = CustomUser.objects.all().order_by('username')
    serializer_class = UserSerializer
```
- **Improved Version**:
```python
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Admin-only, read-only user directory. Account changes go through allauth / Django admin."""
    permission_classes = (IsAdminUser,)
    queryset = CustomUser.objects.order_by('username')
    serializer_class = UserSerializer
```
  Also add `read_only_fields = ('date_joined', 'last_login')` to `UserSerializer` in case the viewset is made writable again later.

---

## Minor

### Issue #7: `api-auth` URL is missing its trailing slash, so the login URL becomes `/api/api-authlogin/`

- **Category**: Best Practice (bug)
- **Severity**: Minor
- **Location**: `api/urls.py:18`
- **Explanation**: `include()` joins the prefix to the child patterns directly. `rest_framework.urls` defines `login/` and `logout/`, so the resulting paths are `/api/api-authlogin/` and `/api/api-authlogout/`. The browsable API still works because it uses `reverse('rest_framework:login')`, but the URLs are malformed, and anyone who types `/api/api-auth/login/` (the documented DRF convention) gets a 404.
- **Current Code**:
```python
path('api-auth', include('rest_framework.urls')),
```
- **Improved Version**:
```python
path('api-auth/', include('rest_framework.urls')),
```

### Issue #8: `ForumViewSet` relies implicitly on the global default permission class

- **Category**: Readability / Best Practice
- **Severity**: Minor
- **Location**: `api/views.py:15-17`
- **Explanation**: The effective rule is `DjangoModelPermissionsOrAnonReadOnly` from `project/settings/base.py:197-199`: writes require `forums.add_forum`, `forums.change_forum` or `forums.delete_forum`. That behavior is correct, but it is invisible in the view. CLAUDE.md describes it as "write authenticated", which suggests a looser rule than the one actually enforced. Declaring it explicitly makes the security intent clear and protects it if the global default ever changes.
- **Current Code**:
```python
class ForumViewSet(viewsets.ModelViewSet):
    queryset = Forum.objects.all().order_by('title')
    serializer_class = ForumSerializer
```
- **Improved Version**:
```python
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

class ForumViewSet(viewsets.ModelViewSet):
    # Read: anyone. Write: users with forums.add/change/delete_forum.
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)
    queryset = Forum.objects.all()
    serializer_class = ForumSerializer
```

### Issue #9: Redundant `order_by()` calls, and one silently reverses the model's ordering

- **Category**: Readability
- **Severity**: Minor
- **Location**: `api/views.py:16`, `api/views.py:22`, `api/views.py:28`, `api/views.py:34`
- **Explanation**: `Forum` (`title`) and `Thread` (`-added`) already have this ordering in `Meta.ordering` (`forums/models.py:30`, `forums/models.py:50`), so the calls duplicate it. `PostViewSet` orders by `-added` while `Post.Meta.ordering` is `added` (`forums/models.py:75`). As a result, `/api/posts/` is newest-first while nested `posts` inside a thread are oldest-first. If that difference is intended, add a comment saying so. Otherwise remove the duplicate calls. `.all()` before `.order_by()` is also unnecessary.
- **Current Code**:
```python
queryset = Forum.objects.all().order_by('title')
queryset = Thread.objects.all().order_by('-added')
queryset = Post.objects.all().order_by('-added')
```
- **Improved Version**:
```python
queryset = Forum.objects.all()            # Meta.ordering = ['title']
queryset = Thread.objects.all()           # Meta.ordering = ['-added']
queryset = Post.objects.order_by('-added')  # Newest first in the flat feed (intentional)
```

### Issue #10: `IsOwnerOrReadOnly` docstring contradicts the implementation

- **Category**: Readability
- **Severity**: Minor
- **Location**: `api/permissions.py:7` vs `api/permissions.py:16-17`
- **Explanation**: The docstring says the model must have an `owner` attribute, but the code reads `obj.user`. Someone relying on the docstring and adding an `owner` field would get an `AttributeError`. Comparing `obj.user_id == request.user.id` also avoids a lazy load of the related user row.
- **Current Code**:
```python
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` attribute.
    """
    ...
        return obj.user == request.user
```
- **Improved Version**:
```python
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has a `user` foreign key.
    """
    ...
        return obj.user_id == request.user.id
```

### Issue #11: Commented-out code in serializers

- **Category**: Readability
- **Severity**: Minor
- **Location**: `api/serializers.py:10`, `api/serializers.py:16`, `api/serializers.py:20`, `api/serializers.py:29`, `api/serializers.py:36-45`
- **Explanation**: Each serializer keeps an old `fields` tuple (and a `user_name` field) as comments. The `UserSerializer` block (`:36-45`) repeats the live tuple almost exactly. Git history already keeps these versions, and the comments make it harder to see which fields are really exposed, which matters in a data-exposure review.
- **Current Code**:
```python
        # fields = ('url', 'id', 'text', 'thread', 'upvotes', 'user')
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
```
- **Improved Version**:
```python
        fields = ('id', 'text', 'thread', 'upvotes', 'user', 'added', 'edited')
```

### Issue #12: Empty stub modules, and no API tests for the security-sensitive behavior

- **Category**: Best Practice
- **Severity**: Minor
- **Location**: `api/tests.py:1-3`, `api/admin.py:1-3`, `api/models.py:1-3`
- **Explanation**: These are unedited `startapp` stubs. The API tests actually live in `tests/forums/test_views_*.py`, so `api/tests.py` suggests there is no coverage when there is some. None of the existing tests cover the risks in Issues #1, #3, #4, #5 or #6. Delete the stubs (or add a pointer comment) and add a `tests/api/` module with regression tests for those issues.
- **Current Code**:
```python
from django.test import TestCase

# Create your tests here.
```
- **Improved Version** (for example, `tests/api/test_permissions.py`):
```python
@pytest.mark.django_db
def test_cannot_create_post_as_another_user(add_user, get_user_client, add_thread):
    me = add_user('me', 'me@example.com', 'pw')
    other = add_user('other', 'other@example.com', 'pw')
    thread = add_thread(...)
    resp = get_user_client(me).post(
        '/api/posts/', {'text': 'hi', 'thread': thread.id, 'user': other.id, 'upvotes': 999},
        format='json',
    )
    assert resp.status_code == 201
    assert resp.data['user'] == me.id
    assert resp.data['upvotes'] == 0


@pytest.mark.django_db
def test_forum_list_query_count_is_constant(client, django_assert_max_num_queries, ...):
    # create several forums/threads/posts, then:
    with django_assert_max_num_queries(5):
        client.get('/api/forums/')
```
  (Fixture names follow `tests/forums/conftest.py`. Adjust them to the actual fixture signatures.)

---

## Quick Wins

1. **Make `user` and `upvotes` read-only and set the author on the server** (Issues #1 and #3). Add `read_only_fields` to `PostSerializer` and `ThreadSerializer`, and add `perform_create(... user=self.request.user)` to `ThreadViewSet` and `PostViewSet`. This is about 6 lines and closes the impersonation and vote-tampering holes without breaking existing tests.
2. **Add `prefetch_related` to the Forum and Thread viewsets** (Issue #2, quick fix). `Forum.objects.prefetch_related('threads__posts')` and `Thread.objects.prefetch_related('posts')` turn the N+1 into a constant number of queries. After that, plan the structural change: counts instead of unbounded nested lists.
3. **Change `UserViewSet` to `ReadOnlyModelViewSet`** (Issue #6). This removes the staff-to-superuser email takeover path and the password-less user creation, and it is a one-word change.
