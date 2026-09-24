# Code Review: `forums/` app

**Date:** 2026-09-24
**Scope:** Every non-migration Python file in `forums/` (`models.py`, `views.py`, `urls.py`, `forms.py`, `tasks.py`, `signals.py`, `admin.py`, `apps.py`, `templatetags/class_name.py`, `management/commands/create_moderators_group.py`), plus the templates in `templates/forums/` that these views render.

## Code Review Summary

- **Files reviewed**: `forums/models.py`, `forums/views.py`, `forums/urls.py`, `forums/forms.py`, `forums/tasks.py`, `forums/signals.py`, `forums/admin.py`, `forums/apps.py`, `forums/templatetags/class_name.py`, `forums/management/commands/create_moderators_group.py`, `templates/forums/*.html`
- **Total issues found**: 20 (Critical: 3 | Important: 8 | Minor: 9)
- **Overall assessment**: The app follows Django's structure well. It uses class-based views consistently, references `settings.AUTH_USER_MODEL` correctly, and uses lifecycle hooks for cache invalidation. However, some state-changing actions are exposed over GET, there are several permission bugs, and there are real N+1 and cache-staleness problems in the list, detail, and search pages.

### What is already done well

- Every `method="post"` form in `templates/forums/` includes `{% csrf_token %}` (`forum_form.html:10`, `forum_update_form.html:10`, `thread_form.html:20`, `thread_update_form.html:34`, `post_form.html:33`, `post_delete_form.html:9`, `thread_delete_form.html:9`, `userprofile_form.html:17`).
- Every user foreign key uses `settings.AUTH_USER_MODEL` (`forums/models.py:41-44, 66-69, 145-149, 164-167, 179`).
- `UserProfileForm` lists its fields explicitly instead of using `'__all__'` (`forums/forms.py:10-22`).
- `ThreadDetail` already uses `select_related('user')` / `prefetch_related('user__profile')` for posts (`forums/views.py:101-106`).
- The `class_name` template filter (`forums/templatetags/class_name.py:6-8`) is small and correct.

---

## Critical

### Issue #1: `PostUpvote` changes state over GET, allows unlimited and self-upvotes, and has a race condition

- **Category**: Security / Best Practice / Performance
- **Severity**: Critical
- **Location**: `forums/views.py:226-237`, `templates/forums/thread_detail.html:118-127`, `forums/models.py:162-174`
- **Explanation**:
  1. **CSRF via GET.** The upvote runs in `get()`. Django's CSRF protection only covers unsafe methods (POST, PUT, DELETE). Any third-party page can embed `<img src="https://yoursite/forums/thread/1/post/5/upvote">`, and every logged-in visitor's browser will then cast an upvote. Link prefetchers and crawlers can also trigger it.
  2. **No one-vote-per-user rule.** Nothing stops the same user from upvoting over and over. Each request adds 1 and creates another `UpVote` row. The template hides the button on the user's own posts (`thread_detail.html:121`), but the view doesn't check this, so users can still upvote themselves by entering the URL directly.
  3. **Lost updates.** `post.upvotes += 1; post.save()` is a read-modify-write in Python. When two requests run at the same time, both read N and both write N+1.
  4. **500 on bad IDs.** `Post.objects.get(id=...)` raises `DoesNotExist`, which becomes a 500 error instead of a 404. The view also never checks that the post belongs to the thread `tpk`.
  5. `upvote.save()` right after `objects.create()` is an extra UPDATE query. `model = Post` does nothing on a plain `View`.
- **Current code** (`forums/views.py:226-237`):
```python
class PostUpvote(LoginRequiredMixin, View):
    model = Post

    def get(self, request, **kwargs):
        post = Post.objects.get(id=self.kwargs['pk'])
        post.upvotes += 1
        post.save()
        upvote = UpVote.objects.create(post=post, user=self.request.user)
        upvote.save()
        return HttpResponseRedirect(
            reverse_lazy('thread_detail', kwargs={'pk': self.kwargs['tpk']})
        )
```
- **Improved version**:
```python
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect


class PostUpvote(LoginRequiredMixin, View):
    http_method_names = ['post']  # GET now returns 405; CSRF middleware protects POST

    def post(self, request, tpk, pk):
        # 404 instead of 500, and the post must belong to the thread in the URL
        post = get_object_or_404(Post, pk=pk, thread_id=tpk)

        if post.user_id != request.user.id:  # enforce "no self-upvote" server-side
            with transaction.atomic():
                _, created = UpVote.objects.get_or_create(post=post, user=request.user)
                if created:
                    # Atomic increment in SQL: no lost updates
                    Post.objects.filter(pk=post.pk).update(upvotes=F('upvotes') + 1)
            # .update() bypasses lifecycle hooks, so invalidate the cache manually
            cache.delete(f'post_objects_thread_{tpk}')

        return redirect('thread_detail', pk=tpk)
```
  Template (`thread_detail.html:122-123`), replacing the link with a form:
```html
<form method="post" action="{% url 'post_upvote' thread.id post.id %}" class="d-inline">
    {% csrf_token %}
    <button type="submit" class="btn btn-outline-secondary p-1">+</button>
</form>
```
  Also see Issue #5 (a unique constraint on `UpVote`), which enforces one vote per user at the database level.

---

### Issue #2: `ThreadUpdate` checks a permission that doesn't exist, and template permission checks don't match the views

- **Category**: Best Practice / Security (authorization correctness)
- **Severity**: Critical (functional bug in authorization)
- **Location**: `forums/views.py:130`, `templates/forums/forum_detail.html:30, 34`, `forums/management/commands/create_moderators_group.py:9`
- **Explanation**: Django creates the permissions `add_`, `change_`, `delete_`, and `view_` for each model. `forums.update_thread` is not one of them, and no migration or `Meta.permissions` defines it (I checked `forums/migrations/`). Because of this, `has_perm('forums.update_thread')` always returns `False`. The Moderators group gets `change_thread` from `create_moderators_group.py:9`, yet moderators still can't edit other users' threads. The comment on line 123 (`# permission_required = 'forums.change_thread'`) shows the intended name.
  In addition, `forum_detail.html` decides whether to show the thread "Delete" and "Update" buttons using `perms.forums.delete_forum` and `perms.forums.change_forum`, but the views check `delete_thread` and `update_thread`. So users with forum permissions see buttons that return 403, and users with only thread permissions don't see buttons they're allowed to use. `CLAUDE.md` repeats the wrong permission name.
- **Current code** (`forums/views.py:126-133`):
```python
    def test_func(self):
        """
        User must be author to update
        """
        if self.request.user.has_perm('forums.update_thread'):
            return True
        obj = self.get_object()
        return obj.user == self.request.user
```
  (`templates/forums/forum_detail.html:30, 34`)
```html
{% if thread.user == user or perms.forums.delete_forum %}
...
{% if thread.user == user or perms.forums.change_forum %}
```
- **Improved version**:
```python
    def test_func(self):
        """Allow the thread author, or anyone with the built-in change_thread permission."""
        if self.request.user.has_perm('forums.change_thread'):  # real Django codename
            return True
        return self.get_object().user_id == self.request.user.id
```
```html
{% if thread.user == user or perms.forums.delete_thread %}
...
{% if thread.user == user or perms.forums.change_thread %}
```
  Add a regression test: a user in the Moderators group can GET and POST `thread_update` for another user's thread.

---

### Issue #3: `ForumCreate` crashes with a 500 for anonymous users

- **Category**: Best Practice / Correctness
- **Severity**: Critical
- **Location**: `forums/views.py:57-77`
- **Explanation**: `login_url = ''` is falsy. When an anonymous user requests `/forums/add/`, `PermissionRequiredMixin.handle_no_permission()` calls `get_login_url()`. That goes into the `else` branch and raises `NotImplementedError`, which becomes an unhandled 500 (and a Sentry event in production). The overridden method is a near-copy of Django's own `AccessMixin.get_login_url()`, but it no longer falls back to `settings.LOGIN_URL`. `LOGIN_URL` isn't set in `project/settings/base.py`, so Django's default `/accounts/login/` would apply, and that path is correct for allauth.
- **Current code**:
```python
class ForumCreate(PermissionRequiredMixin, CreateView):
    model = Forum
    fields = '__all__'
    permission_required = 'forums.add_forum'
    success_url = reverse_lazy('forum_list')
    login_url = ''

    def get_login_url(self):
        """
        Override this method to override the login_url attribute.
        """
        if login_url := self.login_url:
            return str(login_url)
        else:
            raise NotImplementedError(
                ...
            )
```
- **Improved version**:
```python
class ForumCreate(PermissionRequiredMixin, CreateView):
    model = Forum
    fields = ('title', 'description')  # explicit fields; see Minor notes below
    permission_required = 'forums.add_forum'
    success_url = reverse_lazy('forum_list')
    # No login_url / get_login_url override: Django falls back to settings.LOGIN_URL
    # (default '/accounts/login/', which is allauth's login page).
```
  Add a test: an anonymous GET to `forum_add` returns 302 to the login page.

---

## Important

### Issue #4: `ThreadNotification` toggles the subscription over GET and returns a 500 for missing threads

- **Category**: Security / Best Practice
- **Severity**: Important
- **Location**: `forums/views.py:240-257`, `templates/forums/thread_detail.html:41-44`
- **Explanation**: This has the same CSRF-over-GET problem as Issue #1. A third-party page can subscribe or unsubscribe a logged-in user from any thread, which can cause unwanted emails. `Thread.objects.get(...)` raises a 500 for an invalid pk. The walrus expression evaluates the whole queryset only to check truthiness. `notification.save()` after `create()` is a redundant query.
- **Current code**:
```python
    def get(self, request, **kwargs):
        thread = Thread.objects.get(id=self.kwargs['pk'])
        if existing_notification := Notification.objects.filter(
            thread=thread, user=self.request.user
        ):
            existing_notification.delete()
        else:
            notification = Notification.objects.create(
                thread=thread, user=self.request.user
            )

            notification.save()
```
- **Improved version**:
```python
class ThreadNotification(LoginRequiredMixin, View):
    http_method_names = ['post']

    def post(self, request, pk):
        thread = get_object_or_404(Thread, pk=pk)
        deleted, _ = Notification.objects.filter(thread=thread, user=request.user).delete()
        if not deleted:  # there was no subscription, so create one
            Notification.objects.create(thread=thread, user=request.user)
        return redirect('thread_detail', pk=pk)
```
  In the template, render the Subscribe/Subscribed buttons as a `<form method="post">` with `{% csrf_token %}`.

---

### Issue #5: No uniqueness constraints on `UpVote(post, user)` or `Notification(thread, user)`

- **Category**: Best Practice / Data integrity
- **Severity**: Important
- **Location**: `forums/models.py:162-174`, `forums/models.py:177-187`
- **Explanation**: Both are "one row per user per object" relationships, but the database allows duplicates. Application-level checks alone are race-prone: a double-click can create two rows. Duplicate `Notification` rows can make a subscriber appear twice in the BCC list, and duplicate `UpVote` rows inflate vote counts. A `UniqueConstraint` also gives you the composite index that lookups like `Notification.objects.filter(thread=..., user=...)` in `views.py:114-116` and `views.py:245-247` need.
- **Current code**:
```python
class UpVote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    added = models.DateTimeField(auto_now_add=True)
    ...
    class Meta:
        ordering = ['added']
```
- **Improved version**:
```python
class UpVote(models.Model):
    ...
    class Meta:
        ordering = ['added']
        constraints = [
            models.UniqueConstraint(fields=['post', 'user'], name='unique_upvote_per_user'),
        ]


class Notification(models.Model):
    ...
    class Meta:
        ordering = ['added']
        constraints = [
            models.UniqueConstraint(fields=['thread', 'user'], name='unique_subscription_per_user'),
        ]
```
  Remove existing duplicates in a data migration **before** the constraint migration runs, or the migration will fail on production data.

---

### Issue #6: N+1 COUNT queries on the forum list page

- **Category**: Performance
- **Severity**: Important
- **Location**: `templates/forums/forum_list.html:36`, `forums/views.py:27-30`
- **Explanation**: `{{ forum.threads.count }}` runs a separate `SELECT COUNT(*)` for each forum in the loop. With F forums that's F+1 queries on the site's landing page. One annotated query does the same work.
- **Current code**:
```python
class ForumsList(ListView, FormView):
    model = Forum
    context_object_name = 'forum_list'
    form_class = SearchForm
```
```html
threads: {{ forum.threads.count }}
```
- **Improved version**:
```python
from django.db.models import Count


class ForumsList(ListView, FormView):
    model = Forum
    context_object_name = 'forum_list'
    form_class = SearchForm

    def get_queryset(self):
        # One query with a GROUP BY instead of one COUNT per forum
        return Forum.objects.annotate(thread_count=Count('threads'))
```
```html
threads: {{ forum.thread_count }}
```

---

### Issue #7: `ForumDetail` loads every post just to count them, and its cache is never invalidated when posts change

- **Category**: Performance / Correctness
- **Severity**: Important
- **Location**: `forums/views.py:37-54`, `forums/models.py:120-124`, `templates/forums/forum_detail.html:39-40`
- **Explanation**:
  1. `.prefetch_related('posts')` fetches **every post, including the full Markdown text**, for every thread in the forum. The template only needs `thread.posts.all.count`. That payload is then pickled into Redis.
  2. `.prefetch_related('user')` on a ForeignKey runs a second query. `select_related` would use a JOIN. `user__profile` is a reverse one-to-one relation, so it can also go through `select_related`.
  3. **Stale data:** `Post.invalidate_cache` only deletes `post_objects_thread_<id>`. The cached forum thread list (`thread_objects_forum_<forum_id>`) holds a snapshot of posts, so after someone replies, "number of posts" stays wrong until the default 300-second cache timeout expires. The same happens after a profile edit, because the cached users and profiles are frozen.
  4. `cache.set()` receives a lazy queryset. It works because pickling forces evaluation, but that behavior is implicit. Wrapping it in `list(...)` makes it clear.
  5. `forum=self.kwargs['pk']` duplicates `self.object`, which `DetailView` has already loaded.
- **Current code**:
```python
        thread_objects = cache.get(f'thread_objects_forum_{self.kwargs["pk"]}')

        if thread_objects is None:
            thread_objects = (
                Thread.objects.filter(forum=self.kwargs['pk'])
                .prefetch_related('user')
                .prefetch_related('user__profile')
                .prefetch_related('posts')
            )
            cache.set(f'thread_objects_forum_{self.kwargs["pk"]}', thread_objects)
```
- **Improved version**:
```python
THREAD_CACHE_KEY = 'thread_objects_forum_{forum_id}'


class ForumDetail(DetailView):
    model = Forum
    context_object_name = 'forum'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cache_key = THREAD_CACHE_KEY.format(forum_id=self.object.pk)

        threads = cache.get(cache_key)
        if threads is None:
            threads = list(  # evaluate explicitly before caching
                self.object.threads
                .select_related('user__profile')      # one JOIN instead of 2 extra queries
                .annotate(post_count=Count('posts'))  # count in SQL, don't load post text
            )
            cache.set(cache_key, threads)

        context['threads'] = threads
        return context
```
  In `Post.invalidate_cache` (`models.py:123-124`), also invalidate the parent forum's list:
```python
    def invalidate_cache(self):
        cache.delete_many([
            f'post_objects_thread_{self.thread_id}',
            f'thread_objects_forum_{self.thread.forum_id}',  # post counts shown on forum page
        ])
```
  Template: `number of posts: {{ thread.post_count }}`.

---

### Issue #8: `SearchResultsView` returns `None` or a one-shot iterator, causes N+1 queries in its template, and never supplies the search form

- **Category**: Performance / Best Practice / Readability
- **Severity**: Important
- **Location**: `forums/views.py:260-275`, `templates/forums/post_search_results_form.html:12, 24, 29, 37, 42`
- **Explanation**:
  1. `get_queryset()` returns `None` when `q` is empty, and otherwise returns an `itertools.chain`. Neither is a queryset. `chain` can only be consumed once, and anything that calls `len()` or paginates it will break.
  2. The template reads `object.thread.title`, `object.user`, `object.forum.title`, and `object.user`. Without `select_related`, each result triggers 1–2 extra queries, and `Thread.__str__`/`user` adds more.
  3. The results are unbounded. A one-letter query like `q=a` loads every post and thread into memory. An `icontains` search always scans the full table, so capping the result count matters.
  4. The template renders `{{ form }}` (line 12), but this view never puts a `form` in the context, so the search box on the results page renders empty.
  5. The input bypasses `SearchForm` validation (including `max_length=200`) by reading `request.GET` directly.
- **Current code**:
```python
    def get_queryset(self):  # new
        query = self.request.GET.get('q')

        if not query:
            return

        post = Post.objects.filter(Q(text__icontains=query))
        thread = Thread.objects.filter(
            Q(title__icontains=query) | Q(text__icontains=query)
        )
        return chain(post, thread)
```
- **Improved version**:
```python
MAX_SEARCH_RESULTS = 50


class SearchResultsView(ListView):
    template_name = 'forums/post_search_results_form.html'

    def get_queryset(self):
        self.form = SearchForm(self.request.GET or None)
        if not self.form.is_valid():
            return []
        query = self.form.cleaned_data['q']

        posts = (
            Post.objects.filter(text__icontains=query)
            .select_related('thread', 'user')          # used by the template
        )[:MAX_SEARCH_RESULTS]
        threads = (
            Thread.objects.filter(Q(title__icontains=query) | Q(text__icontains=query))
            .select_related('forum', 'user')           # used by the template
        )[:MAX_SEARCH_RESULTS]
        return [*posts, *threads]  # a concrete list: reusable and len()-able

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.form  # the template renders {{ form }}
        return context
```
  For larger datasets, the commented-out `SearchVector` approach (`views.py:277-283`) with a `GinIndex` is the right next step on PostgreSQL.

---

### Issue #9: `Post.notify_subscribers` hardcodes the URL scheme and environment check, and filters in Python

- **Category**: Best Practice / Performance / Readability
- **Severity**: Important
- **Location**: `forums/models.py:77-98`
- **Explanation**:
  1. `'http://'` is hardcoded, so production emails link over plain HTTP.
  2. `os.environ.get('CI')` inside a model couples domain logic to the process environment. A settings flag, such as `FORUMS_SEND_NOTIFICATIONS = False` in `ci.py`, is easier to discover and override in tests (`override_settings`).
  3. The author is filtered out in Python by comparing `notification_user.user != self.user`, which loads full user rows. `.exclude(...).values_list('user__email', flat=True)` does it in one narrow query.
  4. `task = ...` is assigned and never used. A task is enqueued even when the recipient list is empty.
  5. `reverse_lazy` is unnecessary at runtime. Plain `reverse` is correct here.
  6. The hook enqueues the task inside the request. If the save is ever wrapped in `transaction.atomic()`/`ATOMIC_REQUESTS`, a Celery worker could run before the commit. `transaction.on_commit` guards against that.
- **Current code**:
```python
    @hook(AFTER_CREATE)
    def notify_subscribers(self):
        if not os.environ.get('CI'):
            url = reverse_lazy('thread_detail', args=(self.thread_id,))
            full_url = ''.join(
                ['http://', str(Site.objects.get_current().domain), str(url)]
            )

            notification_users = Notification.objects.filter(thread=self.thread).select_related('user')
            email_addresses = [
                notification_user.user.email
                for notification_user in notification_users
                if notification_user.user != self.user
            ]

            task = send_notifications_task.delay(
                ...
            )
```
- **Improved version**:
```python
    @hook(AFTER_CREATE)
    def notify_subscribers(self):
        if not getattr(settings, 'FORUMS_SEND_NOTIFICATIONS', True):
            return

        email_addresses = list(
            Notification.objects.filter(thread_id=self.thread_id)
            .exclude(user_id=self.user_id)              # filter in SQL
            .values_list('user__email', flat=True)      # fetch only what we need
        )
        if not email_addresses:
            return

        scheme = getattr(settings, 'SITE_URL_SCHEME', 'https')
        domain = Site.objects.get_current().domain
        full_url = f'{scheme}://{domain}{reverse("thread_detail", args=(self.thread_id,))}'

        transaction.on_commit(lambda: send_notifications_task.delay(
            self.thread_id, self.thread.title, self.user.username, full_url, email_addresses,
        ))
```
  **Test impact:** `tests/forums/test_models.py:96` uses `monkeypatch.delenv('CI')`. That test would switch to `settings.FORUMS_SEND_NOTIFICATIONS = True`. With `on_commit`, it would also need `django_capture_on_commit_callbacks(execute=True)`.

---

### Issue #10: `tasks.py` hardcodes the sender address and contains dead code

- **Category**: Best Practice / Readability
- **Severity**: Important
- **Location**: `forums/tasks.py:6-8`, `forums/tasks.py:12-26`
- **Explanation**: `'info@wildvasa.com'` bypasses `settings.DEFAULT_FROM_EMAIL`, which is defined in `project/settings/base.py:189`. You can't change the sender per environment, and it may not match the SendGrid-verified sender. `my_scheduled_task` is a demo stub that uses `print`. The only schedule that mentions it is commented out and points to `project.tasks`, not `forums.tasks` (`base.py:317-322`). The `thread_id` parameter is accepted but never used. The task has no retry, so a transient SMTP or SendGrid failure silently drops the notification.
- **Current code**:
```python
@shared_task
def my_scheduled_task():
    print('A scheduled task just ran')


@shared_task
def send_notifications_task(
    thread_id, thread_title, user_name, full_url, email_addresses
):
    subject, from_email = f'New post added by {user_name}', 'info@wildvasa.com'
    bcc = email_addresses
    ...
    send_mail(subject, from_email, bcc, text_content)
```
- **Improved version**:
```python
from celery import shared_task
from django.conf import settings

from project.utils import send_mail


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_notifications_task(thread_id, thread_title, user_name, full_url, email_addresses):
    """Email thread subscribers (BCC) that a new post was added."""
    subject = f'New post added by {user_name}'
    text_content = f'A new post was added to thread "{thread_title}"\n\nUrl: {full_url}\n\n'
    send_mail(subject, settings.DEFAULT_FROM_EMAIL, email_addresses, text_content)
```
  Keep `thread_id` only if you plan to use it, for example in logging. Otherwise remove it from the signature and from the caller (`models.py:93`).

---

### Issue #11: The admin changelists have N+1 queries, and the upvote filter is wrong

- **Category**: Performance / Correctness
- **Severity**: Important
- **Location**: `forums/admin.py:6-29`, `forums/models.py:46-47, 71-72`
- **Explanation**: `PostAdmin.list_display` includes `'thread'`, which renders `Thread.__str__`. That method interpolates `self.user` (`models.py:47`), so each row triggers a thread query, then a user query, then another query for the `'user'` column: roughly 3 queries per row, or about 300 per page of 100. `ThreadAdmin` has the same problem with `forum` and `user`. `list_select_related` fixes this.
  `('upvotes', admin.BooleanFieldListFilter)` is applied to an `IntegerField`. Its "Yes"/"No" options filter `upvotes__exact=1` / `0`, so "Yes" means "exactly one upvote". The admin also searches by `user__username`, but users log in by email.
- **Current code**:
```python
class PostAdmin(admin.ModelAdmin):
    search_fields = ('user__username',)
    list_display = ('thread', 'added', 'edited', 'user', 'upvotes')
    list_filter = (
        ('added', admin.DateFieldListFilter),
        ('edited', admin.DateFieldListFilter),
        ('upvotes', admin.BooleanFieldListFilter),
    )
```
- **Improved version**:
```python
class PostAdmin(admin.ModelAdmin):
    search_fields = ('user__email', 'user__username')
    list_display = ('thread', 'added', 'edited', 'user', 'upvotes')
    list_select_related = ('thread__user', 'user')  # one JOINed query per page
    list_filter = (
        ('added', admin.DateFieldListFilter),
        ('edited', admin.DateFieldListFilter),
        # remove the boolean filter, or write a SimpleListFilter for "has upvotes" (upvotes__gt=0)
    )


class ThreadAdmin(admin.ModelAdmin):
    search_fields = ('user__email', 'user__username', 'title')
    list_display = ('title', 'forum', 'added', 'edited', 'user')
    list_select_related = ('forum', 'user')
    ...


class NotificationAdmin(admin.ModelAdmin):
    ...
    list_select_related = ('thread__user', 'user')
```

---

## Minor

### Issue #12: `UserProfile.gender` is a `TextField` with `max_length=1`

- **Category**: Best Practice
- **Severity**: Minor
- **Location**: `forums/models.py:154-156`
- **Explanation**: `TextField.max_length` is only enforced by the form widget, not by the database. A single-character code with `choices` belongs in a `CharField`, which stores it as `varchar(1)` and enforces the limit. The commented-out old choice constants (`models.py:135-144`) can be removed now that `Gender` exists.
- **Current code**:
```python
    gender = models.TextField(
        max_length=1, choices=Gender.choices, default=Gender.NOTPROVIDED
    )
```
- **Improved version** (requires a migration):
```python
    gender = models.CharField(
        max_length=1, choices=Gender.choices, default=Gender.NOTPROVIDED
    )
```

---

### Issue #13: Redundant profile signals add a SELECT and an UPDATE to every user save

- **Category**: Performance / Readability
- **Severity**: Minor
- **Location**: `forums/signals.py:9-20`
- **Explanation**: Two receivers do overlapping work. `save_user_profile` runs on **every** user save, including the `last_login` update on each login. It evaluates a whole queryset to check existence and then re-saves an unchanged profile, costing 2 extra queries each time. The two receivers also reference the user model differently (`CustomUser` vs `get_user_model()`). One receiver using `get_or_create` covers both cases.
- **Current code**:
```python
@receiver(post_save, sender=CustomUser, dispatch_uid="create_user_profile")
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=get_user_model(), dispatch_uid="save_user_profile")
def save_user_profile(sender, instance, **kwargs):
    user_profile = UserProfile.objects.filter(user=instance)
    if not user_profile:
        UserProfile.objects.create(user=instance)
    instance.profile.save()
```
- **Improved version**:
```python
from django.conf import settings


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="ensure_user_profile")
def ensure_user_profile(sender, instance, created, **kwargs):
    """Every user has exactly one profile; create it lazily if it's missing."""
    if created:
        UserProfile.objects.create(user=instance)
    elif not hasattr(instance, 'profile'):  # legacy users without a profile
        UserProfile.objects.get_or_create(user=instance)
```

---

### Issue #14: `ThreadDetail` builds an unused `voted` queryset, and the thread object makes extra queries

- **Category**: Performance / Readability
- **Severity**: Minor
- **Location**: `forums/views.py:90-117`, `templates/forums/thread_detail.html:32, 57-77`
- **Explanation**: `context['voted']` (`views.py:113`) holds *all* of the user's upvotes across the site, and `thread_detail.html` never references `voted`. It's lazy, so it costs no query today, but it's misleading dead code. The thread itself is fetched without `select_related`, so `thread.forum.id` (line 32) and `thread.user.profile.*` (lines 57-77) cost 3 extra queries. `thread.forum_id` avoids one of them entirely. `subscribed` only needs a boolean.
- **Current code**:
```python
        if self.request.user.is_authenticated:
            context['voted'] = UpVote.objects.filter(user=self.request.user)
            context['subscribed'] = Notification.objects.filter(
                thread=self.kwargs['pk'], user=self.request.user
            )
```
- **Improved version**:
```python
class ThreadDetail(DetailView):
    model = Thread
    context_object_name = 'thread'

    def get_queryset(self):
        return super().get_queryset().select_related('forum', 'user__profile')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ...
        if self.request.user.is_authenticated:
            context['subscribed'] = Notification.objects.filter(
                thread=self.object, user=self.request.user
            ).exists()
        return context
```
  Template line 32: `{% url 'forum_detail' thread.forum_id %}`.

---

### Issue #15: `PostDelete` and `ThreadDelete` don't check that the object belongs to the parent in the URL

- **Category**: Best Practice
- **Severity**: Minor
- **Location**: `forums/views.py:164-180`, `forums/views.py:207-223`, `forums/urls.py:33, 35-39`
- **Explanation**: `/forums/thread/<tpk>/post/<pk>/delete` looks up the post by `pk` alone. Any `tpk` works, and after deletion the user is redirected to that (possibly unrelated) thread. `ThreadDelete` has the same issue with `fpk`. Owner and permission checks still apply, so this isn't a security hole, but the URLs are inconsistent and the redirects can be wrong.
- **Current code**:
```python
class PostDelete(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    template_name_suffix = '_delete_form'
```
- **Improved version**:
```python
class PostDelete(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    template_name_suffix = '_delete_form'

    def get_queryset(self):
        # Mismatched thread/post pair -> 404
        return super().get_queryset().filter(thread_id=self.kwargs['tpk'])
```
  (Do the same for `ThreadDelete`, filtering on `forum_id=self.kwargs['fpk']`.)

---

### Issue #16: `ThreadCreate` looks up the forum twice and has a typo in the success message

- **Category**: Readability / Performance
- **Severity**: Minor
- **Location**: `forums/views.py:139-161`
- **Explanation**: `get_object_or_404(Forum, ...)` runs in both `get_context_data` and `form_valid`. When a form is invalid, it runs twice in one request. Loading it once in `setup()`/`dispatch()` is simpler. `"successfullty"` is a user-visible typo. `context_object_name = 'thread'` does nothing on a `CreateView` before the object exists. `PostCreate` (`views.py:183-204`) has the same double-fetch pattern for `Thread`.
- **Current code**:
```python
    success_message = "Thread was created successfullty"

    def get_context_data(self, **kwargs):
        context = super(ThreadCreate, self).get_context_data(**kwargs)
        context['forum'] = get_object_or_404(Forum, pk=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.forum = get_object_or_404(Forum, pk=self.kwargs['pk'])
        return super(ThreadCreate, self).form_valid(form)
```
- **Improved version**:
```python
class ThreadCreate(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = Thread
    fields = ['title', 'text']
    success_message = "Thread was created successfully"

    def dispatch(self, request, *args, **kwargs):
        self.forum = get_object_or_404(Forum, pk=kwargs['pk'])  # fetched once
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(forum=self.forum, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.forum = self.forum
        return super().form_valid(form)
```

---

### Issue #17: `Post.__str__` embeds the full Markdown body and a user lookup

- **Category**: Readability / Performance
- **Severity**: Minor
- **Location**: `forums/models.py:71-72` (and `46-47`, `170-171`, `183-184`)
- **Explanation**: Wherever a `Post` is stringified (admin, `UpVote.__str__`, logs, `post_upvote_form.html:7`), the entire post body is printed and `self.user` triggers a query. Truncating the text keeps it readable. `Thread.__str__` and `UpVote.__str__` chain several of these lookups.
- **Current code**:
```python
    def __str__(self):
        return f'Post: {self.text} - (submitted by {self.user})'
```
- **Improved version**:
```python
from django.utils.text import Truncator

    def __str__(self):
        return f'Post #{self.pk}: {Truncator(self.text).chars(50)}'
```

---

### Issue #18: Commented-out code, Python 2-style `super()`, and no-op attributes

- **Category**: Readability
- **Severity**: Minor
- **Location**: `forums/models.py:7, 35, 40, 60, 100-118, 135-144`; `forums/views.py:123, 168, 211, 262, 265, 277-283`; `forums/views.py:39, 96, 147, 158, 190, 201`; `forums/views.py:227, 241`; `forums/views.py:59, 82`
- **Explanation**: About 40 lines of commented-out code (the old email implementation, old field definitions, old permission attributes) make the real logic harder to scan, and git history already keeps them. `super(ClassName, self)` can be `super()` in Python 3. `model = ...` on plain `View` subclasses (`PostUpvote`, `ThreadNotification`) does nothing. `# new` on `views.py:265` is a tutorial leftover. `fields = '__all__'` on `ForumCreate`/`ForumUpdate` is safe today but will silently expose any field added to `Forum` in the future. Listing `('title', 'description')` is more defensive.
- **Current code** (example):
```python
        # Call the base implementation
        context = super(ForumDetail, self).get_context_data(**kwargs)
```
- **Improved version**:
```python
        context = super().get_context_data(**kwargs)
```

---

### Issue #19: `create_moderators_group` has a redundant `__init__` and a codename lookup that isn't scoped to a content type

- **Category**: Readability / Best Practice
- **Severity**: Minor
- **Location**: `forums/management/commands/create_moderators_group.py:16-17, 23-45`
- **Explanation**: The `__init__` override only calls `super()` and can be removed. `Permission.objects.get(codename=codename)` isn't scoped to the model's content type. If another app ever defines a model with the same name (for example `post`), this raises `MultipleObjectsReturned`, which isn't caught. Iterating with `.items()` also removes the repeated dict indexing. `group.__str__()` can be written as `{group}`.
- **Current code**:
```python
    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
    ...
        for group_name in GROUPS_PERMISSIONS:
            group, created = Group.objects.get_or_create(name=group_name)
            for model_cls in GROUPS_PERMISSIONS[group_name]:
                for perm_name in GROUPS_PERMISSIONS[group_name][model_cls]:
                    codename = f"{perm_name}_{model_cls._meta.model_name}"
                    try:
                        perm = Permission.objects.get(codename=codename)
```
- **Improved version**:
```python
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = "Create default groups"

    def handle(self, *args, **options):
        for group_name, model_perms in GROUPS_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            for model_cls, actions in model_perms.items():
                content_type = ContentType.objects.get_for_model(model_cls)
                for action in actions:
                    codename = f"{action}_{model_cls._meta.model_name}"
                    try:
                        perm = Permission.objects.get(content_type=content_type, codename=codename)
                    except Permission.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"{codename} not found"))
                        continue
                    group.permissions.add(perm)
                    self.stdout.write(f"Adding {codename} to group {group}")
```

---

### Issue #20: Dead or incorrect templates and small markup problems

- **Category**: Readability
- **Severity**: Minor
- **Location**: `templates/forums/post_upvote_form.html:1-14`, `templates/forums/forums.html:1-16`, `templates/forums/post_search_results_form.html:1, 11`, `templates/forums/forum_list.html:16`, `templates/forums/forum_detail.html:24-55`
- **Explanation**:
  - `post_upvote_form.html` is never rendered, because `PostUpvote` is a plain `View` with no template. Its content is also wrong ("Are you sure you want to delete this thread?", `post.title` doesn't exist). `forums.html` isn't referenced anywhere I could find. Delete both, or repurpose `post_upvote_form.html` for the POST confirmation in Issue #1.
  - `post_search_results_form.html:1` has `<!DOCTYPE html>` *before* `{% extends %}`. Django discards it, so it's misleading.
  - `action={% url 'search_results' %}` is unquoted (`post_search_results_form.html:11`, `forum_list.html:16`). Use `action="{% url 'search_results' %}"`.
  - `forum_detail.html` nests `<a>` delete/update buttons inside the thread-card `<a>` (lines 24, 31, 35). Nested anchors are invalid HTML, and browsers split them unpredictably.
- **Current code**:
```html
<!DOCTYPE html>
{% extends '_base.html' %}
...
<form action={% url 'search_results' %} method='get' ...>
```
- **Improved version**:
```html
{% extends '_base.html' %}
...
<form action="{% url 'search_results' %}" method="get" ...>
```

---

## Quick Wins

1. **Make upvote and subscribe POST-only with server-side checks** (Issues #1, #4, #5). Switch `PostUpvote` and `ThreadNotification` to `post()` behind `{% csrf_token %}` forms. Use `get_object_or_404`, `get_or_create`, and `F('upvotes') + 1`, and add `UniqueConstraint`s. This closes the CSRF-via-GET hole, stops vote stuffing and self-votes, and fixes the lost-update race.
2. **Fix the broken permission checks** (Issues #2, #3). Replace `forums.update_thread` with `forums.change_thread` (`views.py:130`), align the `perms.forums.*` checks in `forum_detail.html:30, 34`, and delete `ForumCreate`'s `login_url = ''`/`get_login_url` override so anonymous users are redirected instead of getting a 500. Each is a one- or two-line change with a clear regression test.
3. **Remove the N+1 queries and stale counts on the main pages** (Issues #6, #7, #8). Annotate `thread_count` / `post_count` with `Count(...)` instead of calling `.count` in templates or prefetching all posts. Invalidate `thread_objects_forum_<id>` from `Post.invalidate_cache`, and add `select_related` plus a result cap to search.
