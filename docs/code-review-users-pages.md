# Code Review: `users/` and `pages/` apps

**Date:** 2026-09-24
**Scope:** Every non-migration Python file in `users/` and `pages/`. I read the migrations only to check the database schema.
**Stack verified from `uv.lock`:** Django 4.2.29, django-allauth 0.63.6, django-lifecycle 1.2.7

## Code Review Summary

- **Files Reviewed**:
  - `users/__init__.py`, `users/apps.py`, `users/models.py`, `users/forms.py`, `users/admin.py`, `users/tests.py`
  - `pages/__init__.py`, `pages/apps.py`, `pages/models.py`, `pages/admin.py`, `pages/views.py`, `pages/urls.py`, `pages/tests.py`
  - Read for context only: `users/migrations/0001_initial.py`, `users/migrations/0002_alter_customuser_first_name.py`, `forums/signals.py`, `forums/models.py`, `project/views.py`, `project/utils.py`, `project/settings/base.py`, `templates/home.html`
- **Total Issues Found**: 13 (Critical: 1 | Important: 6 | Minor: 6)
- **Overall Assessment**: `pages/` is small and clean. `HomePageView` and its URL conf are fine as written. `users/` needs more work. The welcome email is sent synchronously inside `save()`. Login is email-only, but the database does not require email to be unique or even present. The admin forms have a `Meta` inheritance bug and never show the email field when you add a user. Several tests either always pass or don't test what their names say.

Things that are already done well:
- In `users/models.py:7`, `LifecycleModelMixin` comes before `AbstractUser` in the class bases, which is the correct order.
- `users/forms.py` and `users/admin.py` use `get_user_model()` instead of importing the concrete model.
- In `pages/views.py`, a plain `TemplateView` is the right tool for a static page.

---

## Critical

### Issue #1: Welcome email is sent synchronously inside `save()`, before the transaction commits

- **Location**: `users/models.py:10-22`
- **Category**: Best Practice / Performance
- **Severity**: Critical
- **Explanation**: `send_welcome_mail` runs as an `after_create` hook. That means it runs inside `CustomUser.save()`, after the row is inserted and after the `post_save` receivers in `forums/signals.py` have created the `UserProfile`. This has three effects:
  1. **An SMTP/SendGrid failure breaks the request after the user already exists.** `msg.send()` raises (the default is `fail_silently=False`). The exception comes out of `save()`, so the signup (allauth), admin add, or social login fails with a 500. The user and profile rows have already been written, so the person ends up with a half-created account and an error page.
  2. **The email can go out for a user who is later rolled back.** The admin `add_view` runs in `transaction.atomic()`. If something later in that transaction fails (see Issue #5), the insert is rolled back but the email has already been sent.
  3. **Signup latency.** Every signup blocks on a network round trip to the mail provider. The project already has Celery for this (`forums/tasks.py`), and `Post.notify_subscribers` already offloads its email that way. The welcome email doesn't.

  django-lifecycle 1.2.x supports `on_commit=True` on hooks, which defers the callback until the surrounding transaction commits. Combining that with a Celery task fixes all three problems.
- **Current Code**:
```python
class CustomUser(LifecycleModelMixin, AbstractUser):
    pass

    @hook('after_create')
    def send_welcome_mail(self):
        subject, from_email = 'Welcome to Wildvasa Forums', 'info@wildvasa.com'

        to = (self.email,)

        text_content = 'Thank you for registering at Wildvasa forums'

        msg = EmailMultiAlternatives(
            subject=subject, body=text_content, from_email=from_email, to=to
        )

        msg.send()
```
- **Improved Version**:
```python
# users/tasks.py
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

WELCOME_SUBJECT = 'Welcome to Wildvasa Forums'
WELCOME_BODY = 'Thank you for registering at Wildvasa forums'


@shared_task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_welcome_email_task(email):
    send_mail(
        subject=WELCOME_SUBJECT,
        message=WELCOME_BODY,
        from_email=settings.DEFAULT_FROM_EMAIL,  # see Issue #9
        recipient_list=[email],
    )


# users/models.py
from django.contrib.auth.models import AbstractUser
from django_lifecycle import AFTER_CREATE, LifecycleModelMixin, hook


class CustomUser(LifecycleModelMixin, AbstractUser):
    @hook(AFTER_CREATE, on_commit=True)  # runs only after the INSERT is committed
    def send_welcome_mail(self):
        """Queue a welcome email for newly registered users."""
        if not self.email:  # e.g. createsuperuser without an email
            return
        from users.tasks import send_welcome_email_task  # avoid import cycles

        send_welcome_email_task.delay(self.email)
```
  Note: because of `on_commit=True`, tests that use `TestCase` (which wraps each test in a transaction that never commits) must use `self.captureOnCommitCallbacks(execute=True)` to check `mail.outbox`.

---

## Important

### Issue #2: The database doesn't require email to be unique or present, even though login is email-only

- **Location**: `users/models.py:7-8` (schema in `users/migrations/0001_initial.py:33`); related settings in `project/settings/base.py:184-187`
- **Category**: Best Practice / Security
- **Severity**: Important
- **Explanation**: The project authenticates by email (`ACCOUNT_AUTHENTICATION_METHOD = 'email'`, `ACCOUNT_UNIQUE_EMAIL = True`). `CustomUser` inherits `AbstractUser.email`, which is `EmailField(blank=True)` with no unique constraint. `ACCOUNT_UNIQUE_EMAIL` is only checked by allauth's own forms. Other paths skip that check: the Django admin (`CustomUserChangeForm` exposes `email`), `createsuperuser`, the shell, fixtures (`make dev_export_data`/`loaddata`), and any future API write endpoint. Any of them can store a duplicate or empty email. A duplicate makes "log in by email" ambiguous. An empty email produces an account that can't log in through the email-only flow. For an identity field, the database should enforce the rule.

  Assumption: `username` is kept on purpose (the API orders users by `username` and the admin lists it), so I'm not proposing `USERNAME_FIELD = 'email'`. I'm only proposing a constraint on `email`.
- **Current Code**:
```python
class CustomUser(LifecycleModelMixin, AbstractUser):
    pass
```
- **Improved Version**:
```python
from django.db import models
from django.db.models.functions import Lower


class CustomUser(LifecycleModelMixin, AbstractUser):
    # Email is the login identifier, so require it and let the DB enforce it.
    email = models.EmailField('email address', unique=True)

    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'
        constraints = [
            # Case-insensitive uniqueness: Foo@x.com and foo@x.com are the same user.
            models.UniqueConstraint(Lower('email'), name='users_customuser_email_ci_unique'),
        ]
```
  This needs a migration. Before applying it, run a data migration or manual check for existing blank or duplicate emails (for example `CustomUser.objects.values(Lower('email')).annotate(n=Count('id')).filter(n__gt=1)`), or the migration will fail on PostgreSQL.

### Issue #3: `class Meta(UserCreationForm)` inherits from the form class, not its `Meta`

- **Location**: `users/forms.py:6` and `users/forms.py:12`
- **Category**: Best Practice (latent bug)
- **Severity**: Important
- **Explanation**: `class Meta(UserCreationForm):` makes `Meta` a subclass of the form class itself, not of `UserCreationForm.Meta`. It looks like it works because `model` and `fields` are set explicitly. But everything else defined on the parent `Meta` is lost. In Django 4.2, `UserCreationForm.Meta` and `UserChangeForm.Meta` both declare `field_classes = {"username": UsernameField}`. `UsernameField` applies Unicode NFKC normalization and sets `autocapitalize="none"`/`autocomplete="username"`. Without it, the admin forms treat `username` as a plain `CharField`, so visually identical usernames can differ at the Unicode level. It also means any future change Django makes to the parent `Meta` won't reach these forms.
- **Current Code**:
```python
class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm):
        model = get_user_model()
        fields = ('email', 'username',)


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm):
        model = get_user_model()
        fields = ('email', 'username',)
```
- **Improved Version**:
```python
class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):  # inherit field_classes (UsernameField)
        model = get_user_model()
        fields = ('email', 'username')


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = ('email', 'username')
```

### Issue #4: The admin "Add user" page never shows the email field

- **Location**: `users/admin.py:15-28`
- **Category**: Best Practice
- **Severity**: Important
- **Explanation**: `add_form = CustomUserCreationForm` lists `email`, but `UserAdmin` builds the add form from `add_fieldsets`. In Django 4.2 that is only `("username", "password1", "password2")`. `CustomUserAdmin` doesn't override `add_fieldsets`, so the email field is dropped from the form. As a result, every user created in the admin:
  - has an empty email and can't log in, because authentication is email-only;
  - never gets a welcome email (`EmailMessage.send()` silently skips empty recipients);
  - gets around the allauth uniqueness check. See Issue #2 for the related constraint problem.
- **Current Code**:
```python
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'is_staff', 'is_active', 'date_joined']
```
- **Improved Version**:
```python
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'is_staff', 'is_active', 'date_joined']
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )
```

### Issue #5: The profile inline on the "Add user" page conflicts with the profile-creating signal

- **Location**: `users/admin.py:11-12`, `users/admin.py:19` (conflicts with `forums/signals.py:9-12`)
- **Category**: Best Practice (bug)
- **Severity**: Important
- **Explanation**: `UserProfileInline` appears on both the change and add views. When an admin adds a user, `save_model()` saves the user first. The `post_save` receiver `create_user_profile` then creates a `UserProfile` automatically. After that, the admin saves the inline formset. If the admin filled in any profile field on the add page, the formset tries to `INSERT` a second `UserProfile` for the same user. `UserProfile.user` is a `OneToOneField` with a unique index, so this raises `IntegrityError`, the whole add transaction rolls back, and Issue #1 means the welcome email may already be out. There's a second problem: the inline has the default `can_delete=True`, which lets an admin delete the profile. `save_user_profile` then quietly re-creates it on the next save.
- **Current Code**:
```python
class UserProfileInline(admin.StackedInline):
    model = UserProfile
```
- **Improved Version**:
```python
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False  # the profile's lifecycle is owned by the post_save signal


class CustomUserAdmin(UserAdmin):
    ...
    inlines = [UserProfileInline]

    def get_inline_instances(self, request, obj=None):
        # The profile is created by the post_save signal, so only show the inline
        # when editing an existing user. Showing it on "add" can cause an IntegrityError.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)
```

### Issue #6: `test_homepage_url_resolves_homepageview` always passes

- **Location**: `pages/tests.py:25-27`
- **Category**: Best Practice (test quality)
- **Severity**: Important
- **Explanation**: In Django 4.2, `View.as_view()` deliberately leaves `__name__` unchanged ("view_class should be used to robustly determine the name of the view instead"). Every class-based view's resolved function therefore has `__name__ == 'view'`. The assertion compares `'view' == 'view'` and would still pass if `/` were routed to any other class-based view. Use `view_class` instead.
- **Current Code**:
```python
def test_homepage_url_resolves_homepageview(self):
    view = resolve('/')
    self.assertEqual(view.func.__name__, HomePageView.as_view().__name__)
```
- **Improved Version**:
```python
def test_homepage_url_resolves_homepageview(self):
    match = resolve('/')
    self.assertIs(match.func.view_class, HomePageView)
```

### Issue #7: The `users` tests miss the main behavior: profile update view, owner-only permission, and welcome email

- **Location**: `users/tests.py:63-73`, `users/tests.py:75-95`
- **Category**: Best Practice (test quality)
- **Severity**: Important
- **Explanation**:
  - `test_userprofile_update` (lines 75-95) never calls the view. It sets attributes on a model instance, calls `.save()`, and reads them back, which only tests the Django ORM. Form validation, the `UserProfileForm` field list, and the `success_url` redirect are all untested.
  - Nothing checks that user A can't edit user B's profile. That owner check (`test_func` in `project/views.py:14-19`) is the only authorization protecting the endpoint.
  - The comment on line 64 says an anonymous user "should redirect to login page", but the test only checks `302`. In fact, `UserProfileUpdate.handle_no_permission` (`project/views.py:21-22`) overrides the handler for **both** `LoginRequiredMixin` and `UserPassesTestMixin`, so anonymous users are sent to `home`, not the login page. The test passes, but the behavior doesn't match the comment. Either the comment or the view is wrong, and a weak assertion hides it.
  - Nothing tests that the welcome email is sent (Issue #1).
- **Current Code**:
```python
def test_userprofile_template(self):
    # if user not logged in should redirect to login page
    self.response = self.client.get(self.url)
    self.assertEqual(self.response.status_code, 302)
    ...

def test_userprofile_update(self):
    # Update users profile info
    user_profile = UserProfile.objects.get(user_id=self.user.id)
    user_profile.first_name = 'Julle'
    ...
    user_profile.save()
```
- **Improved Version**:
```python
from django.core import mail


def test_anonymous_user_is_redirected(self):
    response = self.client.get(self.url)
    # Assert the actual target; change to reverse('account_login') if the view is fixed.
    self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)

def test_owner_can_update_profile_via_view(self):
    self.client.force_login(self.user)
    response = self.client.post(self.url, {
        'first_name': 'Julle', 'last_name': 'Julgran', 'bio': 'The users bio',
        'location': '', 'gender': Gender.MALE, 'web_site': 'https://mysite.com',
        'github_url': 'https://github.com/julle', 'signature': 'Regards julle',
    })
    self.assertRedirects(response, reverse('home'), fetch_redirect_response=False)
    self.user.profile.refresh_from_db()
    self.assertEqual(self.user.profile.first_name, 'Julle')

def test_other_user_cannot_edit_profile(self):
    other = get_user_model().objects.create_user(
        username='other', email='other@test.com', password='testpass123'
    )
    self.client.force_login(other)
    response = self.client.post(self.url, {'first_name': 'Hacked', 'gender': 'N'})
    self.assertEqual(response.status_code, 302)
    self.user.profile.refresh_from_db()
    self.assertNotEqual(self.user.profile.first_name, 'Hacked')


class WelcomeMailTests(TestCase):
    def test_welcome_mail_sent_on_create(self):
        get_user_model().objects.create_user(
            username='new', email='new@test.com', password='x'
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['new@test.com'])

    def test_no_welcome_mail_on_update(self):
        user = get_user_model().objects.create_user(
            username='new', email='new@test.com', password='x'
        )
        mail.outbox.clear()
        user.first_name = 'Changed'
        user.save()
        self.assertEqual(len(mail.outbox), 0)
```
  (If Issue #1 is adopted with `on_commit=True`, wrap the create calls in `with self.captureOnCommitCallbacks(execute=True):`.)

---

## Minor

### Issue #8: Redundant `pass` and a string hook name in `CustomUser`

- **Location**: `users/models.py:8`, `users/models.py:10`
- **Category**: Readability
- **Severity**: Minor
- **Explanation**: `pass` is only needed when a class body is otherwise empty. Here it sits in front of a method and does nothing. The hook uses the string `'after_create'`, while `forums/models.py:13-16` imports the `AFTER_CREATE` constant. The constant is consistent with the rest of the codebase, and a typo in it fails at import time instead of silently never firing.
- **Current Code**:
```python
class CustomUser(LifecycleModelMixin, AbstractUser):
    pass

    @hook('after_create')
    def send_welcome_mail(self):
```
- **Improved Version**:
```python
from django_lifecycle import AFTER_CREATE, LifecycleModelMixin, hook


class CustomUser(LifecycleModelMixin, AbstractUser):
    @hook(AFTER_CREATE)
    def send_welcome_mail(self):
        """Send a welcome email to newly registered users."""
```

### Issue #9: Hardcoded sender and subject, and `EmailMultiAlternatives` with no alternatives

- **Location**: `users/models.py:2`, `users/models.py:12`, `users/models.py:16-20`
- **Category**: Best Practice / Readability
- **Severity**: Minor
- **Explanation**: `'info@wildvasa.com'` is hardcoded, but the project already defines `DEFAULT_FROM_EMAIL` (`project/settings/base.py:189`), so each environment can't set its own sender. The subject and body are inline magic strings. `EmailMultiAlternatives` is for messages with an HTML or other alternative part. None is attached here, so `django.core.mail.send_mail` (or `EmailMessage`) states the intent more clearly. The code in Issue #1 fixes all of these. Note that `DEFAULT_FROM_EMAIL` is currently the placeholder `'noreply@email.com'` in both `base.py` and `production.py`, so set it to the real sender before you switch.
- **Current Code**:
```python
subject, from_email = 'Welcome to Wildvasa Forums', 'info@wildvasa.com'
...
msg = EmailMultiAlternatives(
    subject=subject, body=text_content, from_email=from_email, to=to
)
```
- **Improved Version**:
```python
from django.conf import settings
from django.core.mail import send_mail

WELCOME_SUBJECT = 'Welcome to Wildvasa Forums'
WELCOME_BODY = 'Thank you for registering at Wildvasa forums'

send_mail(WELCOME_SUBJECT, WELCOME_BODY, settings.DEFAULT_FROM_EMAIL, [self.email])
```

### Issue #10: Redundant `model` attribute and a commented-out line in the admin

- **Location**: `users/admin.py:18`, `users/admin.py:21`, `users/admin.py:31`
- **Category**: Readability
- **Severity**: Minor
- **Explanation**: `ModelAdmin` gets its model from `admin.site.register(...)`, so `model = CustomUser` on line 18 does nothing and could mislead readers. The commented-out `list_filter` on line 21 is dead code that line 23 supersedes. The `@admin.register` decorator keeps the registration next to the class.
- **Current Code**:
```python
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'is_staff', 'is_active', 'date_joined']
    # list_filter = ('date_joined',)
...
admin.site.register(CustomUser, CustomUserAdmin)
```
- **Improved Version**:
```python
@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    inlines = [UserProfileInline]
    list_display = ['email', 'username', 'is_staff', 'is_active', 'date_joined']
    list_filter = (...)
```

### Issue #11: `SignupPageTests.test_signup_form` doesn't test the signup form

- **Location**: `users/tests.py:32-50`
- **Category**: Best Practice (test quality) / Readability
- **Severity**: Minor
- **Explanation**: `setUp` creates a user directly with `create_user` (line 37), and `test_signup_form` then checks that this user exists. The signup form is never submitted, so the allauth signup flow, email-only signup, and the welcome-email trigger are all untested, and the test name is misleading. `test_signup_template` doesn't need that user either. The test also runs three separate queries (`.all().count()`, then `.all()[0]` twice) where one would do.
- **Current Code**:
```python
def setUp(self):
    self.user = get_user_model().objects.create_user(self.username, self.email)
    url = reverse('account_signup')
    self.response = self.client.get(url)

def test_signup_form(self):
    self.assertEqual(get_user_model().objects.all().count(), 1)
    self.assertEqual(get_user_model().objects.all()[0].username, self.username)
    self.assertEqual(get_user_model().objects.all()[0].email, self.email)
```
- **Improved Version**:
```python
def test_signup_form_creates_user(self):
    response = self.client.post(reverse('account_signup'), {
        'email': self.email,
        'password1': 'S3cure-pass-123',
    })
    self.assertEqual(response.status_code, 302)
    user = get_user_model().objects.get()  # exactly one user, one query
    self.assertEqual(user.email, self.email)
```

### Issue #12: Test naming and state handling in `users/tests.py`

- **Location**: `users/tests.py:10`, `users/tests.py:21`, `users/tests.py:55-56`, `users/tests.py:61`, `users/tests.py:65-69`
- **Category**: Readability
- **Severity**: Minor
- **Explanation**:
  - Line 55 binds the user **class** to the lowercase name `user` (`user = get_user_model()`) and then sets `self.user` to an instance on the next line, which is easy to misread. Lines 10 and 21 use a capitalized local `User`, which PEP 8 reserves for classes. That works here, but a module-level `User = get_user_model()` would be clearer and avoid repeating it.
  - Line 61 is commented-out dead code.
  - Test methods assign the response to `self.response` (lines 65, 69), which leaks per-test state onto the instance. A local variable is enough.
  - `self.client.login(username=..., password=...)` (line 68) re-runs password hashing. `self.client.force_login(self.user)` is faster and doesn't depend on which auth backend accepts `username`.
- **Current Code**:
```python
def setUp(self):
    user = get_user_model()
    self.user = user.objects.create_user(...)
    ...
    self.client.login(username='julle', password='testpass123')
    self.response = self.client.get(self.url)
```
- **Improved Version**:
```python
User = get_user_model()  # module level


class EditProfilePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(...)
        self.url = reverse('user_profile_edit', args=(self.user.profile.id,))

    def test_userprofile_template(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        ...
```

### Issue #13: Placeholder boilerplate files in `pages/`

- **Location**: `pages/models.py:1-3`, `pages/admin.py:1-3`
- **Category**: Readability
- **Severity**: Minor
- **Explanation**: Both files contain only the `startapp` template (`# Create your models here.` / `# Register your models here.`) and an unused import. `pages` has no models, so these files add noise and unused imports (`models`, `admin`). You can safely delete them. Django doesn't require `models.py` or `admin.py`.
- **Current Code**:
```python
from django.db import models

# Create your models here.
```
- **Improved Version**:
```python
# Delete pages/models.py and pages/admin.py. Neither is needed for an app without models.
```

---

## Related observations outside the requested scope (not counted)

I came across these while checking how the user model is wired in. They directly affect `users/`, but the code lives elsewhere:
- `forums/signals.py:15-20`: `save_user_profile` runs on **every** `CustomUser` save. That includes the `last_login` update allauth performs on each login. Each time it runs an extra `SELECT` plus an `UPDATE` of the unchanged profile, and on create it duplicates the work of `create_user_profile`. Consider combining the two receivers into one that only acts when `created`.
- `project/views.py:14-19`: `test_func` calls `self.get_object()`, and `UpdateView.get()`/`post()` call it again, so the profile is fetched twice per request. Also, as noted in Issue #7, overriding `handle_no_permission` sends anonymous users to `home` instead of the login page.

---

## Quick Wins

1. **Make the welcome email non-blocking and commit-safe (Issue #1)**: switch to `@hook(AFTER_CREATE, on_commit=True)` and send through a Celery task using `settings.DEFAULT_FROM_EMAIL`. After that, a mail-provider outage can no longer turn a signup into a 500, and rolled-back users never get an email.
2. **Fix the admin user forms (Issues #3, #4, #5)**: change `Meta(UserCreationForm)` to `Meta(UserCreationForm.Meta)`, add `email` to `add_fieldsets`, and hide the profile inline on the add view. These are small edits to two files, and they fix admin-created users having no email as well as a possible `IntegrityError`.
3. **Enforce case-insensitive unique email in the database (Issue #2)**: email is the login identity, so it needs a DB constraint and not only an allauth form check. Clean up existing duplicate or blank emails before you migrate.
