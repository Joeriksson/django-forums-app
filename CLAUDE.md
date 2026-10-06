# CLAUDE.md

## Project Overview

Django-based discussion forum platform with forums, threads, posts, user authentication, REST API, and email notifications. Built with Django 5.2, Python 3.12, and managed with `uv`.

## Development Setup

### Using Docker (Recommended)

```bash
make dev_build   # Build and start all containers
make dev         # Start containers (already built)
make dev_logs    # View logs
make dev_down    # Stop containers
```

### Manual Setup

1. Copy `.env.example` to `.env` and fill it in (see below)
2. Install dependencies: `uv sync`
3. Apply migrations: `python manage.py migrate --settings=project.settings.development`
4. Create superuser: `python manage.py createsuperuser --settings=project.settings.development`
5. Run server: `python manage.py runserver --settings=project.settings.development`

Server runs at `http://127.0.0.1:8000`

## Production Deployment

Production runs `docker-compose-prod.yml` on a VPS behind a reverse proxy container (Caddy). The stack publishes no ports: only `web` joins the shared `forum_proxy` network, where the proxy reaches it as `forum-web:8000`. The network is external: created once on the server (`docker network create forum_proxy`), and by CI before its compose step. See `docs/deployment-vps.md` for the proxy config, the `.env` checklist, first deploy, updates, backups and troubleshooting.

The `Dockerfile` installs only runtime dependencies by default (`ARG UV_SYNC_FLAGS=--no-dev`); `docker-compose-dev.yml` passes an empty value so dev images also get the dev group (pytest etc.). `.dockerignore` keeps `.env`, `.git` and `.venv` out of the image; compose passes `.env` in at runtime via `env_file`. It also leaves out `docs/`, the root `*.md` files and the compose files, so an update that changes only those doesn't rebuild the image or restart the containers.

The image runs as the unprivileged user `app` (uid 1000); the code and the venv belong to root, so the app can't write under `/code` or `/opt/venv` in production: anything it must write goes to `/tmp`. In development the mounted repo belongs to the host user, normally also uid 1000, so files written by the containers (migrations) get the right owner; with another host uid, add `user:` to the services in `docker-compose-dev.yml`. Redis gets its password from a config file written at container start, not from its command line, and runs as `redis`. Production has no `celery-beat` service (nothing is scheduled); the dev one keeps its schedule file in `/tmp`.

gunicorn's settings are in `gunicorn.conf.py` (address, 2 workers with 4 threads each; `WEB_CONCURRENCY` changes the worker count; its control socket is off, since it would be a file in `/code`). The compose command for `web` is `migrate --noinput` and then just `gunicorn project.wsgi` (flags on the command line would win over the file): migrations run at every start of `web`, which waits for a healthy `db`; a failed one makes the container exit. `celery` doesn't migrate.

uv is pinned to an exact version (`COPY --from=ghcr.io/astral-sh/uv:<version>` in the `Dockerfile`). `make audit` doesn't cover it, so bump it when upgrading dependencies, and check uv's release notes for security fixes. The same goes for the other images, pinned to patch versions (`python:3.12.15-slim` in the `Dockerfile`; `postgres:16.15` and `redis:8.10-alpine` in both compose files and in CI, kept equal), and for the GitHub Actions, pinned to commit SHAs with the version in a comment (`.github/workflows/django.yml`; find a tag's commit with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, and for an annotated tag follow it to its commit). No Dependabot: bump them by hand.

## Running Tests

```bash
# Docker
make dev_pytest        # Run pytest

# Manual
pytest -v --disable-warnings
```

Tests use `project.settings.test` settings. Coverage and pytest configuration are in `pyproject.toml`. Tests run in parallel (`-n auto`) via `pytest-xdist`. A `RemovedInDjango60Warning` fails the test that triggers it (`filterwarnings` in `pyproject.toml`).

### Test Structure

```
conftest.py                      # Autouse fixtures for every test: clear the cache, record notification tasks; add_totp, verify_email, security_log
tests/
├── test_pages.py                # Home page
├── test_users.py                # User model, signup
├── test_account_pages.py, test_email_verification.py, test_user_*.py, test_email_senders.py, test_*settings.py
└── forums/
    ├── conftest.py              # Factory fixtures (add_user, add_forum, add_thread, add_post, get_user_client)
    ├── test_models.py           # Model unit tests
    ├── test_serializers.py      # DRF serializer tests
    ├── test_views_web.py        # Web pages, create and delete views
    ├── test_display_names.py    # Names shown to others: profile name or "Member <id>", never the username
    ├── test_views_profile.py, test_views_upvote_subscribe.py, test_permissions.py
    ├── test_views_forums.py, test_views_threads.py, test_views_posts.py  # API CRUD
    └── test_api_*.py            # API ownership, moderation, nesting, users, URLs
```

All tests live under `tests/` (`testpaths` in `pyproject.toml`); there are no `tests.py` files in the apps.

## Key Commands (Makefile)

```bash
make dev_web_exec cmd='python manage.py migrate'          # Run management commands
make dev_web_exec cmd='python manage.py createsuperuser'
make dev_export_data                                       # Export DB as JSON fixture
make dev_redis_exec cmd='redis-cli'                        # Access Redis CLI
make audit                                                 # Check uv.lock for known vulnerabilities (runs on the host)
```

`make audit` runs `pip-audit` on the locked dependencies, dev ones included. Known vulnerabilities that can't be fixed yet are listed in `AUDIT_IGNORE` in the `Makefile`; remove each entry with the upgrade that fixes it.

`manage.py` defaults to `project.settings.base`, which has no `EMAIL_BACKEND` (falls back to SMTP on localhost, so e.g. `createsuperuser` fails when the welcome mail hook fires). Set `DJANGO_SETTINGS_MODULE=project.settings.development` in `.env`, or pass `--settings=project.settings.development` to management commands.

## Project Structure

```
project/           # Django project settings and configuration
  settings/
    base.py        # Shared config (installed apps, middleware, REST, cache, Celery)
    development.py # Local dev overrides
    test.py        # Test settings (used by pytest and CI)
    production.py  # Production settings
  celery.py        # Celery app definition
  urls.py          # Root URL configuration
  utils.py         # send_mail helper (BCC via the configured email backend), queue_task, site_language
  middleware.py    # ContentSecurityPolicyMiddleware: the CSP header from SECURE_CSP; SiteLanguageMiddleware: the page's language

forums/            # Core app — Forum, Thread, Post, UpVote, Notification, UserProfile models
  models.py        # All core models; a django-lifecycle hook on Post sends the notifications
  views.py         # Class-based views (ListView, DetailView, CreateView, etc.)
  urls.py          # Forum URL patterns
  forms.py         # SearchForm
  tasks.py         # Celery tasks (send_notifications_task)
  activity.py      # Reply counts, latest activity and last repliers for the forum and thread lists
  throttling.py    # Posting, search and preview limits: DRF throttles, shared by the web views and the API
  search.py        # Full-text search over threads and replies (one UNION, sorted and paged); SearchForm is in forms.py
  signals.py       # Django signals (if any)
  templatetags/    # Template tags: when (dates), markdown, nav (the header's current section)

users/             # Custom user model (email-based auth)
  models.py        # CustomUser extends AbstractUser; sends welcome email on create
  encryption.py    # Encrypts two-factor secrets (encrypt_secret, decrypt_secret); key: MFA_ENCRYPTION_KEY
  audit.py         # Security log: log_event, signal receivers, refused-request middleware
  tasks.py         # Celery task send_welcome_email_task

pages/             # Home (visitors: the name, a way in, an invitation note while signup is closed, a drawn landscape; members: the forum list), the latest conversations, and SiteSettings (models.py; context_processors.py)
api/               # Django REST Framework API (mounted only with DJANGO_API_ENABLED)
  views.py         # ModelViewSet for Forum, Thread, Post, User
  serializers.py   # No nested lists: Forum has thread_count, Thread has post_count
  urls.py          # DRF router + schema endpoint
  permissions.py   # IsOwnerOrModeratorOrReadOnly custom permission

tests/             # pytest test suite
templates/         # HTML templates (extends _base.html)
static/            # Static file sources (our CSS and JS, fonts, icons, the favicon, highlight.js, EasyMDE); collected into staticfiles/ at image build, not committed
```

## Data Models

### Forum
- `title` (CharField, max 200)
- `description` (CharField, max 500)
- `posting` (`Posting` choices, default `open`): who may add to the forum. `open`: every member; `moderators_start`: only moderators start threads, members reply; `moderators_only`: members read. A moderator is anyone with `forums.change_thread`, as for announcements. Set on the forum's add and edit forms and in the admin. The rule is `Forum.can_start_thread(user)` and `Forum.can_reply(user)`; `is_closed` tells whether it isn't open. On the website `ClosedForumMixin` (`forums/views.py`) makes `ThreadCreate` and `PostCreate` answer 403 before the form, so a refused post doesn't count against the posting limit; a new view that creates threads or posts needs it too. The forum page says *Closed* and who can post (`posting_note`), the forum list marks the row, and *New thread* and *Reply* show only to those who may use them (`can_start_thread`, `can_reply` in the context). Closing stops new content only: members still edit and delete their own, upvote and subscribe. The API follows the same rule on create: `ThreadSerializer.validate_forum` and `PostSerializer.validate_thread` answer 400, and the forum endpoint shows `posting`, writable with the forum permissions. A refused API create still counts against the posting limit (DRF throttles before it validates); on the website it doesn't. Tests: `tests/forums/test_closed_forums.py`
- Ordered by `title`

### Thread
- `title` (CharField, max 300)
- `text` (TextField — Markdown, max 20 000 characters)
- `added` (DateTimeField); `edited` (DateTimeField, empty until the title or text is changed, see *Edited mark*)
- `forum` (ForeignKey → Forum)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Ordered by `-added`

### Post
- `text` (TextField — Markdown, max 20 000 characters)
- `upvotes` (IntegerField, default 0)
- `added` (DateTimeField); `edited` (DateTimeField, empty until the text is changed, see *Edited mark*)
- `thread` (ForeignKey → Thread)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Ordered by `added`
- **Lifecycle hooks**:
  - `notify_subscribers` (AFTER_CREATE, after the commit): queues `send_notifications_task` via Celery (skipped in CI). Only active subscribers whose address is verified (allauth's `EmailAddress`) get the mail, so test subscribers need `verify_email`. Tests need `django_capture_on_commit_callbacks(execute=True)` to see it run

### Edited mark
- `Thread.edited` and `Post.edited` are empty until the text (or a thread's title) changes: the `mark_edited` lifecycle hook (BEFORE_UPDATE) sets the time, so the website, the API and the admin behave alike. Other saves don't count (a moderator's announcement mark), nor does a form saved unchanged. A `queryset.update()` skips the hook, and so does `save(update_fields=...)` without `edited`
- `edited_by` is who made that change, when it is known: code that saves a change for a user sets `obj.editor = request.user` first (`ThreadUpdate`, `PostUpdate`, the API's `ModerationLogMixin`, `EditorAdminMixin` in `forums/admin.py`), and the hook copies it only when the text changed. A new view that edits texts must set it too. When it isn't the author (`edited_by_moderator`), the line ends *by a moderator*, for moderators and superusers alike, without a name: the security log has it. It follows the last change, so the author's next edit makes the line plain again; so does deleting the editor's account. Not in the API
- The thread page shows *Edited 5 Oct 2026, 14:32* under the text (`templates/forums/_edited.html`), for the opening post and for replies (*… by a moderator* when someone else changed it). The API gives `edited` as `null` for a text never changed. Migration `forums/0022` cleared the times that were set at creation. Tests: `tests/forums/test_edited_mark.py`
- Members change their own replies with *Edit* on the thread page (`PostUpdate`), also in a closed forum; an edit doesn't count against the posting limit and sends no notification. Tests: `tests/forums/test_post_edit.py`

### UserProfile
- One-to-one with AUTH_USER_MODEL
- Fields: `first_name`, `last_name`, `bio`, `location`, `gender` (TextChoices), `web_site`, `github_url`, `signature` (max 500 characters)
- The `max_length` of the text fields and the signature (`MAX_TEXT_LENGTH`, `MAX_SIGNATURE_LENGTH` in `forums/models.py`) is checked by the forms and the API, not by the database; the editor preview refuses longer text too

### Announcements
- `Thread.announcement` (BooleanField): kept at the top of its forum page, in its own list on every page and outside the pagination, and listed first under its forum in the forum list; the thread page's label says *Announcement*. Per forum, no limit
- Set by anyone with `forums.change_thread` (moderators, superusers): a checkbox on the new and edit thread forms (`AnnouncementFieldMixin` in `forums/views.py`), shown to them only, so an author's edit keeps a moderator's mark. A moderator marking someone else's thread is logged as moderation. The API shows the field to all and refuses a change by anyone else (`ThreadSerializer.validate_announcement`). Tests: `tests/forums/test_announcements.py`

### Search
- PostgreSQL full-text search in English word forms (`SEARCH_CONFIG = 'english'` in `forums/models.py`): `THREAD_SEARCH_VECTOR` (title weight A, text B) and `POST_SEARCH_VECTOR` (text B), with GIN indexes on exactly those expressions (migration `forums/0020`). A query must use these constants, or PostgreSQL scans every row
- `forums/search.py`: `matches()` turns the form's data into one UNION of thread and reply rows (kind, id, added, rank), filtered by forum, author, dates and kind and sorted by rank or date; `load()` loads one page's objects and gives each reply its number and thread page. Words use web search syntax (`"phrase"`, `-word`); they need 3 characters unless a filter is set
- Matched words are marked in the excerpts: `load()` gets them from `ts_headline` (`SearchHeadline`) in the same query, marked with two private-use characters (`START`, `STOP` in `forums/search.py`, removed from the text first so members can't type them), then renders the Markdown and strips the tags (which escapes), and only then turns the markers into `<mark>`. Titles are not highlighted: `ts_headline` treats text as HTML and may drop parts that look like tags, so a title would not show as typed
- The filters are in a `<details>` toggle, *Filters (n)* with the number in use: folded on a phone unless a filter is in use; `static/js/search.js` opens it on wider screens
- `SearchForm` (`forums/forms.py`): the author list shows display names, with the member number for names that occur twice. Page links keep the search (`{% querystring %}` in `templates/forums/_pages.html`, which needs `request` passed into the include). Tests: `tests/forums/test_search.py`

### UpVote
- `post` (ForeignKey → Post)
- `user` (ForeignKey → AUTH_USER_MODEL)
- `added` (DateTimeField)

### Notification
- `thread` (ForeignKey → Thread)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Users subscribe to threads to receive email notifications on new posts

### CustomUser (`users.CustomUser`)
- Extends `AbstractUser`
- Uses **email** for authentication (not username); the database requires it to be non-empty and unique ignoring case (migration `users/0003`)
- **Names shown to others** come from `user.display_name`: the profile's first and last name if set, otherwise `Member <id>`. Never print `{{ user }}` or `username` on a page or in a mail that someone else sees: allauth derives the username from the email address (`anna.berg@example.com` → `anna.berg`). It stays in the database and is visible to staff in the admin and the users API. `has_profile_name` tells whether a name is set; the new thread and new post forms remind members without one (`templates/forums/_posting_as.html`). Profile names are not unique. Queries that list authors need `select_related('user__profile')`
- `send_welcome_mail` lifecycle hook fires after the user creation commits (`on_commit=True`) and queues `send_welcome_email_task`

### SiteSettings (`pages.SiteSettings`)
- One record (pk 1, created by migration `pages/0001`), edited under *Site settings* in the admin, which opens it from the list and allows no adding or deleting: `title` (the site's name), `tagline` and `invitation_note` (the visitors' home page), and the numbers `recent_threads` (3), `latest_threads` (15), `threads_per_page` (20) and `posts_per_page` (25), each with limits checked by the admin form (not by the database)
- Read it with `SiteSettings.for_request(request)` in views: loaded once per request and shared with the templates, which get it as `site_settings` from `pages.context_processors.site_settings`, lazily: one query on a page that uses it. `SiteSettings.load()` (the defaults if the record is missing) outside a request, e.g. in tasks. No cache, so every gunicorn worker sees a change at once. `500.html` is rendered without context processors: `_base.html` falls back to `Wildvasa`
- Saving copies the title into the *Sites* display name. allauth's emails (`AccountAdapter.send_mail`, `format_email_subject`), the welcome and invitation emails and the name in authenticator apps (`MFAAdapter.get_totp_issuer`) read the title from `SiteSettings`, not from *Sites*, whose per-process cache would keep an old name until a restart
- Tests: `tests/test_site_settings.py`; other tests change it with the `site_settings` fixture (root `conftest.py`), e.g. `site_settings(posts_per_page=2)`

### Invitation (`users.Invitation`)
- `email`, `key` (random, unique), `invited_by`, `created`, `sent_at`, `accepted_at`, `accepted_by`
- Valid while unused and younger than `INVITATION_EXPIRY_DAYS` (7, in `base.py`): `Invitation.objects.valid()` / `is_valid()`
- Created in the Django admin (needs `users.add_invitation`). The add form (`InvitationAdminForm`) refuses addresses with an account or a pending invitation. Saving queues `send_invitation_email_task` on commit; the *Resend invitation* action calls `renew()` (new key, expiry restarts) and sends again. `get_link()` builds the link from `SITE_URL`
- The link `/accounts/invite/<key>/` stores the key in the session (`Invitation.SESSION_KEY`) and stashes the address as verified, then redirects to signup. While signup is closed, it opens signup for that address only: the signup form shows the address read-only (`InvitedSignupForm` in `users/forms.py`, set in `ACCOUNT_FORMS`) and refuses other addresses, and a GitHub signup needs the address among GitHub's verified emails. allauth's `user_signed_up` signal marks it used (`users/models.py`)

## URL Structure

```
/                          → HomePageView (for a visitor the name and a login link; for a member the forum list, ForumsList, under a Recent activity box with the threads with the newest activity (3 by default, *Site settings*): `latest_threads()` in forums/activity.py, also used by /latest/)
/latest/                   → LatestView (the threads with the latest activity, 15 by default (*Site settings*); login required)
/search/                   → SearchView (words and filters as GET parameters, 20 results a page; login required; 20 searches a minute)
# Everything under /forums/ needs a login
/forums/                   → redirect to / (the forum list's old address)
/forums/<pk>/              → ForumDetail (threads newest first, 20 per page by default (*Site settings*); ?page=<n>)
/forums/add/               → ForumCreate (requires forums.add_forum permission)
/forums/<pk>/update/       → ForumUpdate (requires forums.change_forum permission)
/forums/<pk>/add/          → ThreadCreate (login required)
/forums/<fpk>/delete/<pk>  → ThreadDelete (owner or forums.delete_thread)
/forums/thread/<pk>        → ThreadDetail (posts oldest first, 25 per page by default (*Site settings*); ?page=<n> or ?page=last)
/forums/thread/<pk>/update/→ ThreadUpdate (owner or forums.change_thread)
/forums/thread/<pk>/notify → ThreadNotification (toggle subscription)
/forums/thread/<pk>/post   → PostCreate (then the thread's last page)
/forums/thread/<tpk>/post/<pk>/update/ → PostUpdate (owner or forums.change_post; then back to the reply on its page)
/forums/thread/<tpk>/post/<pk>/delete  → PostDelete
/forums/thread/<tpk>/post/<pk>/upvote  → PostUpvote
/forums/search/            → redirect to /search/, keeping the query string
/forums/preview/           → MarkdownPreview (POST, login required: Markdown text → HTML for the editor's preview)

# /api/ exists only while DJANGO_API_ENABLED is true (default: off; on in development and tests)
/api/forums/               → ForumViewSet (read for members; write needs forums.add/change/delete_forum)
/api/threads/              → ThreadViewSet (IsOwnerOrModeratorOrReadOnly); ?forum=<id> filters
/api/posts/                → PostViewSet (IsOwnerOrModeratorOrReadOnly); ?thread=<id> filters
/api/users/                → UserViewSet (read-only, staff only via IsAdminUser)
/api/schema/               → OpenAPI schema (YAML; ?format=openapi-json for JSON)

/accounts/invite/<key>/    → accept_invitation (valid link: opens signup for the invited address)
/accounts/2fa/             → allauth.mfa (set up an authenticator app, recovery codes; code prompt at login)
/accounts/                 → django-allauth (login, signup, social auth)
/user_profile/<pk>         → UserProfileUpdate
/<ADMIN_URL>/              → Django admin (default: /nimda/); logs in through /accounts/login/
/__debug__/                → Django Debug Toolbar (DEBUG only)
```

## Caching

The forum and thread pages are not cached: each loads one page of threads or posts, with authors and counts, in a single query. Don't cache model instances with their users: that puts email addresses and password hashes in Redis.

The Redis cache (`CACHES` in `base.py`) is still used by allauth's rate limits and the DRF throttles. It stores JSON, not django-redis' default pickle (`SERIALIZER`), so write access to Redis doesn't mean code execution in the web process: cache only values JSON can hold. `VERSION` is part of every key; raise it when the format of cached values changes, so old values are left to expire unread. If Redis is down, the login, signup and password reset pages fail with a 500 rather than run without rate limits: a deliberate choice. Tests use an in-memory cache, cleared around every test (root `conftest.py`).

## Authentication & Permissions

- **Reading needs a login**: the forum is for its members. The forum, thread, latest and search pages have `LoginRequiredMixin` (the forum list is the members' home page) and send visitors to the login page (which leads back afterwards); only the home page and the account pages are open. In the API everything needs a login (`IsAuthenticated` is the default permission in `REST_FRAMEWORK`, the API root and the schema included); visitors get 403. A new view that shows forum content needs the mixin too. Tests: `tests/forums/test_login_required.py`; other tests read as the `reader` fixture (`tests/forums/conftest.py`) or with `reader_client()` (`tests/forums/clients.py`). A logged-in page costs seven queries before its own (session, user, two for permissions, profile, GitHub account, site settings)

- `django-allauth` handles auth with email-only login (no username required)
- **Email addresses must be confirmed** (`ACCOUNT_EMAIL_VERIFICATION = 'mandatory'` in `base.py`, every environment): signup mails a link and logs nobody in before it is used. allauth checks at every login, so an account made without signup (`createsuperuser`, the admin) gets the mail at its first login; in development the link is printed to the console. Invitation and GitHub signups arrive verified. Tests that log in through the login form need the `verify_email` fixture (root `conftest.py`); `force_login` and API tokens don't
- GitHub OAuth social login is configured (`allauth.socialaccount.providers.github`)
- Two-factor login (`allauth.mfa`, needs the `django-allauth[mfa]` extra): optional for every user, an authenticator app (TOTP) plus recovery codes, no passkeys (`MFA_SUPPORTED_TYPES` in `base.py`). Users turn it on under *Two-factor authentication* in the user menu; after that both password and GitHub logins ask for a code. allauth refuses setup while the account has an unverified email address
- Two-factor secrets are encrypted in the database: `users.adapters.MFAAdapter` (`MFA_ADAPTER`) encrypts the authenticator secret and the recovery-code seed with `users/encryption.py` (Fernet, values stored as `fernet:<token>`). There is no cleartext fallback: an unencrypted value is refused, and a wrong key raises `InvalidToken`. Migration `users/0006` encrypted the rows that existed. Code that reads `Authenticator.data` directly gets ciphertext: go through allauth (`authenticator.wrap()`) or `decrypt_secret`
- allauth's rate limits (failed logins, signups, password resets) are partly per client address. Production sets `ALLAUTH_TRUSTED_PROXY_COUNT = 1`, so the address comes from the last `X-Forwarded-For` entry (the one the reverse proxy adds) instead of the proxy's own. Production only: without a proxy the header can be forged. A second proxy in front needs a count of 2
- allauth's pages are allauth's own templates (wording included: "Sign in", "Sign out"), styled through our overrides of its elements in `templates/allauth/elements/` (form, fields, field, button, …: the site's form and button markup) and its layouts in `templates/allauth/layouts/` (`base.html` adds `css/account.css`; `entrance.html` is the narrow column for signing in and up; `manage.html` adds the links between Email, Password and Two-factor). Only `account/signup_closed.html` and `account/invitation_invalid.html` are ours. allauth names users with `ACCOUNT_USER_DISPLAY` (`users.adapters.user_display`: `display_name`, never the username). The GitHub button is the `provider` element, with GitHub's mark from `static/icons/github.svg` (Octicons, MIT, `static/icons/LICENSE-octicons`)
- The API is throttled (`REST_FRAMEWORK` in `base.py`): 120 requests a minute per user (visitors are refused with 403 before anything is counted, so the 60 a minute per address for anonymous clients is only a fallback); over that it answers 429, which the security log records as `denied status=429`. `NUM_PROXIES` is `0` in `base.py` and `1` in production, like `ALLAUTH_TRUSTED_PROXY_COUNT`; a second proxy needs 2. The counters are in the cache, so the API fails while Redis is down. DRF reads the rates at import: tests change them with the `rates` fixture in `tests/forums/conftest.py`
- **Posting limit**: a user may create 5 threads or posts a minute and 30 an hour (`posting_burst`, `posting_hour` in `DEFAULT_THROTTLE_RATES`), counted together for the website and the API, staff and moderators included. `forums/throttling.py` has the two DRF throttles; `PostingLimitMixin` in `forums/views.py` (the form comes back with status 429 and the text kept; forms with errors don't count) and in `api/views.py` (on `create`) use them. A new view that creates threads or posts needs the mixin too
- **Search and preview limits**: 20 searches a minute per user (searches that don't run, the empty form or too few characters, don't count) and 30 Markdown previews a minute per user (`search`, `preview` in `DEFAULT_THROTTLE_RATES`; `SearchThrottle`, `PreviewThrottle` in `forums/throttling.py`). Over the limit the search page says so with status 429 and runs no query; the editor shows that the preview could not be loaded
- The REST API is off unless `DJANGO_API_ENABLED=true`. Code outside `api/` must not `reverse()` its routes: they may not exist (`users/security.py` uses the fixed `API_PATH`). Tests of the off state reload the URL configuration with the `api_off` fixture in `tests/test_api_switch.py`
- Session + Token authentication for the REST API. The API has no login page of its own (DRF's `api-auth/` would skip the two-factor step): log in on the site
- **Staff and moderators must use two-factor authentication** while `STAFF_REQUIRE_MFA` is on (default; off in development). It applies to every privileged user (`users.security.is_privileged`): staff, superusers, and anyone holding a permission, directly or through a group such as Moderators. Members have no permissions:
  - `admin.site.login` is wrapped in allauth's `secure_admin_login` (`project/urls.py`), so the admin uses allauth's login with its code prompt
  - `users.security.StaffMFAMiddleware` redirects a privileged user without an authenticator app to `mfa_index` from every page except those under `/accounts/` (login, logout, address confirmation, the two-factor pages); under `/api/` it answers 403 instead. Recovery codes alone don't count
  - `api.authentication.NonStaffTokenAuthentication` refuses tokens of privileged accounts (403): they use the API with a session
  - `python manage.py remove_mfa <email>` deletes a user's authenticators (lost phone); the user then logs in with the password alone and sets it up again. Switching `DJANGO_STAFF_REQUIRE_MFA` off doesn't help there: login still asks for the code
  - The admin's user form (`CustomUserChangeForm.clean`) refuses staff status, superuser status, a group or a permission for an account without an authenticator app: whoever logs in to such an account gets to set one up, so rights must come after it. The user list has a *Two-factor* column. `createsuperuser` bypasses the form: set that account up right away
  - Tests: privileged users need the `add_totp` fixture (root `conftest.py`) to use the site; `get_user_client` gives them a session instead of a token. A test that submits an authenticator code gets it from the `totp_code` fixture, which holds allauth's clock still: with the real clock the code can expire between making and checking it
- Permission checks: Django model permissions for forum creation and editing; `UserPassesTestMixin` for thread edit/delete and post edit/delete (owner, or a user with `forums.change_thread` / `forums.delete_thread` / `forums.change_post` / `forums.delete_post`)
- **Moderators group**: created by migration `forums/0016_moderators_group` with exactly `change_thread`, `delete_thread` and `delete_post`, so members can edit and delete other users' threads and delete their posts, on the website and through the API. They can't rewrite someone else's reply: that needs `forums.change_post`, which the group doesn't have. Add users to it in the Django admin, once they have an authenticator app
- Custom API permission: `IsOwnerOrModeratorOrReadOnly`, always combined with `IsAuthenticated` — safe methods allowed for any member; write allowed for the owner (`obj.user == request.user`) or a user with the matching model permission (`change_<model>` for PUT/PATCH, `delete_<model>` for DELETE), same as the web views

## Logging

`LOGGING` in `base.py` sends everything from INFO up to stdout with a timestamp in UTC (`project.utils.UTCFormatter`: the pages' `TIME_ZONE` would otherwise move the log's clock too); errors are still mailed to `DJANGO_ADMINS`. In production the containers log to the host's journal (`logging: *journald` in `docker-compose-prod.yml`), so logs survive container recreation; retention is set in the server's `journald.conf` (see `docs/deployment-vps.md`).

The **security log** is the `security` logger: one line per event, `event key=value ...`, with user ids and the client address (the one allauth's rate limits use). Write to it with `users.audit.log_event(event, request, **fields)`; pass text a visitor typed through `quoted()`. Never log passwords, codes, tokens, invitation keys or email addresses of accounts (only the address typed at a failed login).

- `users/audit.py`: signal receivers for login, logout, failed login, signup, password and email changes, two-factor changes and wrong codes; `DeniedRequestLogMiddleware` logs every 401, 403 and 429 response; `log_moderation(request, action, obj)` logs a change to a thread or post by someone other than its author
- Moderation is logged by `ThreadUpdate`, `ThreadDelete`, `PostUpdate`, `PostDelete` (`forums/views.py`) and `ModerationLogMixin` (`api/views.py`): a new view that edits or deletes other users' content must call `log_moderation` too
- Invitations: created and resent (`users/admin.py`), used (`users/models.py`), invalid link (`users/views.py`)
- `remove_mfa` logs itself; other changes in the Django admin are only in the admin's history
- Tests: the `security_log` fixture (root `conftest.py`) returns the lines written during the test

## Async Tasks (Celery)

- Broker: Redis. There is no result backend (`CELERY_TASK_IGNORE_RESULT`): the tasks only send mail and nothing reads their results
- Queue mail tasks with `project.utils.queue_task(task, *args)`, not `.delay()`: if Redis is unreachable it logs an error (mailed to `DJANGO_ADMINS`) and the request carries on without the mail, since the post, user or invitation is already saved. Queuing gives up after 2 to 6 seconds (`CELERY_BROKER_TRANSPORT_OPTIONS`, `CELERY_TASK_PUBLISH_RETRY_POLICY` in `base.py`). The mail is not sent later
- `send_notifications_task`: sends BCC email to thread subscribers when a new post is created; retries up to 3 times on failure
- `send_welcome_email_task` (`users/tasks.py`): sends the welcome email to a new user; retries up to 3 times on failure
- `send_invitation_email_task` (`users/tasks.py`): sends an invitation's link (templates in `templates/users/`) and sets `sent_at`; sends nothing if the invitation is no longer valid; same retries
- Outside production, `CELERY_TASK_ALWAYS_EAGER = True` and `CELERY_TASK_EAGER_PROPAGATES = True`: tasks run synchronously in the web process and their errors are raised there, so the Celery worker is idle in dev
- Tasks skipped entirely in CI (`os.environ.get('CI')` check in `Post.notify_subscribers`)

## Environment Variables

`.env.example` lists every variable with comments; copy it to `.env`. `DEBUG` is not read from the environment: each settings module sets it.

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key. Production refuses to start (`ImproperlyConfigured`) with fewer than 50 characters, fewer than 5 different ones, or a `django-insecure-` key |
| `DJANGO_MFA_ENCRYPTION_KEY` | Fernet key (32 bytes, base64) that encrypts two-factor secrets in the database (`settings.MFA_ENCRYPTION_KEY`). Required in production (`ImproperlyConfigured` otherwise); elsewhere it is derived from `SECRET_KEY`, so a new dev `SECRET_KEY` makes the dev database's second factors unreadable (`remove_mfa`). Changing it has the same effect in production |
| `ENVIRONMENT` | `development`, `production`, `CI`, or `test` |
| `DJANGO_SETTINGS_MODULE` | `project.settings.development` for local/Docker dev (otherwise `manage.py` uses `base`, Celery uses `production`) |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Production SMTP server and login. All three are required: production refuses to start (`ImproperlyConfigured`) if any is missing, unless `DJANGO_EMAIL_CONSOLE=true` |
| `DJANGO_EMAIL_CONSOLE` | Production only: `true` to print mail to the console instead of SMTP, e.g. for trying out the production compose file locally |
| `EMAIL_PORT` / `EMAIL_USE_TLS` | Optional SMTP settings (default: `587`, `true` for STARTTLS) |
| `DEFAULT_FROM_EMAIL` | Optional sender address (default: `EMAIL_HOST_USER`) |
| `DJANGO_ADMINS` | Optional: comma-separated email addresses that Django's default logging mails the traceback of every 500 when `DEBUG=False`. Empty means no error mails. Addresses only: Django never uses the name, and Django 6 drops the `(name, address)` pairs `base.py` still builds for 5.2 |
| `REDIS_URL` | Redis URL (default: `redis://redis:6379/0`). The database number is replaced: cache uses `/0`, Celery uses `/1`. Set automatically by `docker-compose-prod.yml` |
| `REDIS_LOCALHOST` | Set to `true` when using local Redis |
| `POSTGRES_PASSWORD` | `docker-compose-prod.yml` only (required): password of the Postgres superuser, for maintenance; the app doesn't use it |
| `POSTGRES_APP_PASSWORD` | `docker-compose-prod.yml` only (required): password of the app's database role `forum`; used to build `DATABASE_URL`. Use URL-safe characters |
| `REDIS_PASSWORD` | `docker-compose-prod.yml` only (required): Redis password; also used to build `REDIS_URL`. Use URL-safe characters |
| `ADMIN_URL` | Custom admin path (default: `nimda`) |
| `DJANGO_TIME_ZONE` | The zone dates and times are shown in, for every member: a tz database name such as `Europe/Paris` (`settings.TIME_ZONE`; default `UTC`). An unknown name stops the app at start. Logs stay in UTC |
| `DJANGO_LANGUAGE` | The interface's language for visitors who haven't chosen another: `en` (default) or `sv` (`settings.LANGUAGE_CODE`). Another value stops the app at start (`ImproperlyConfigured`). See *Languages* |
| `DJANGO_SIGNUP_OPEN` | `true` lets anyone sign up (email or GitHub). Closed by default; `development.py` and `test.py` open it. `users/adapters.py` decides: signup is open if this is true or the session holds a valid invitation, which then limits signup to the invited address (`AccountAdapter.clean_email` on the signup pages, `SocialAccountAdapter.is_open_for_signup` for GitHub). The navbar hides the link via `{% signup_is_open %}` (`users/templatetags/signup.py`) |
| `DJANGO_CSP_REPORT_ONLY` | `true` makes the Content Security Policy report-only (browsers log violations instead of blocking). Default `false`: enforced everywhere, development and tests included |
| `DJANGO_API_ENABLED` | `true` mounts the REST API under `/api/` (`settings.API_ENABLED`, read by `project/urls.py`). Off by default, so production has no API unless asked for: every `/api/` path is a 404. `development.py` defaults to on and `test.py` sets it on. The `api` app, DRF and the token table stay installed either way, and the website's posting, search and preview limits (DRF throttles) don't depend on it |
| `DJANGO_STAFF_REQUIRE_MFA` | Staff, moderators and anyone else with a permission need an authenticator app to use the site, and their API tokens are refused (`settings.STAFF_REQUIRE_MFA`). Default `true`; `development.py` defaults to `false` |
| `DJANGO_SITE_URL` | The site's public address, for links in emails (`settings.SITE_URL`; used by `Invitation.get_link()` and `Post.notify_subscribers`). Required in production, where it must be `https` without a path (`ImproperlyConfigured` otherwise); elsewhere it defaults to `http://127.0.0.1:8000`. |
| `DJANGO_ALLOWED_HOSTS` | Production only: comma-separated hosts, e.g. `forum.example.com`. Also sets `CSRF_TRUSTED_ORIGINS`. If empty, every request gets a 400 |
| `DJANGO_SECURE_HSTS_SECONDS` | Production HSTS max-age (default: `3600`) |
| `WEB_CONCURRENCY` | Production only: number of gunicorn worker processes (default: `2`), read by `gunicorn.conf.py` |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | Opt-in HSTS flags (default: `false`) |

## Services

- **PostgreSQL**: Database (host: `db` in Docker, `localhost` for CI; credentials: `postgres/postgres` in dev and CI). In production the app connects as the role `forum`, which owns the database `forum` and has no other rights; `docker/postgres/create-app-role.sh` creates both when the volume is first created. A migration that needs a superuser (`CREATE EXTENSION`) won't run there: CI's `prod-image` job runs the migrations as that role
- **Redis**: cache for the login rate limits, and Celery message broker (password-protected and not published in `docker-compose-prod.yml`)
- **Celery**: Async task queue for email notifications
- **Email**: SMTP in production (required, see `EMAIL_*` above); console backend in development
- **Whitenoise**: Static file serving

## Settings Modules

- `project.settings.base` — Shared configuration (all environments inherit this)
- `project.settings.development` — Local development
- `project.settings.test` — Testing (used by pytest, configured in `pyproject.toml`). CI uses it too; `ENVIRONMENT=CI` switches the database in `base.py`
- `project.settings.production` — Production deployment

## Key Dependencies

- **Django 5.2** — web framework
- **django-lifecycle** — model hooks (`@hook` decorator) for the notification and welcome emails
- **markdown-it-py + nh3** — render thread and post text (`forums/markdown.py`, template filter `render_markdown`). Raw HTML in the text is off, so it shows as text; nh3 then keeps only the listed tags, attributes and URL schemes (`http`, `https`, `mailto`). A new Markdown feature needs both the parser rule and the tag in `ALLOWED_TAGS`. Images load only from `https://` addresses: every reader's browser fetches them, so not over `http`. Any other image (`http`, relative, protocol-relative) is rendered as a link to it by the parser's `image` rule, and the sanitiser drops a non-`https` `src` as a second line; a poster can still see the addresses of those who read an `https` image, which is accepted. Code blocks on the thread page are coloured by highlight.js, a single file kept in `static/js/highlight.min.js` (`make audit` doesn't cover it: replace the file to upgrade)
- **EasyMDE** — Markdown editor on the thread and post forms: `templates/forums/_editor.html` loads `static/js/easymde.min.js`, its stylesheet and our `static/js/editor.js` (toolbar, settings). The preview button posts the text to `/forums/preview/`, so it shows what the saved text will look like. Without JavaScript the plain textarea still works. Like highlight.js it is a file in `static/` that `make audit` doesn't cover; it loads nothing from other sites (its spell checker and Font Awesome download are off). Its toolbar buttons are defined in `editor.js` with the class `icon` instead of Font Awesome's; `editor.css` draws each from `static/icons/` (Lucide SVG files, ISC licence in `static/icons/LICENSE`; `make audit` doesn't cover them), named after the button. A new button needs its icon file and a line in `editor.css`. To upgrade it:
  1. Replace the two `easymde.min.*` files with the ones from the new npm package (check its integrity hash) and read the release notes for renamed options and anything new that loads from another site
  2. The tests don't run JavaScript, so check in a browser, logged in, on the new thread, new post and edit thread pages: the toolbar is on one line with all icons, the preview matches the saved result, the Markdown hint under the field is hidden, an empty text shows the form error, and the edit page loads the saved text
- **django-allauth** — authentication + GitHub OAuth
- **cryptography** — Fernet encryption of the two-factor secrets (`users/encryption.py`)
- **djangorestframework** — REST API
- **inflection, uritemplate, pyyaml** — needed by DRF's OpenAPI schema (`/api/schema/`); nothing imports them directly, so keep them in the main dependencies
- **django-redis** — Redis cache backend
- **celery** — async task queue
- **whitenoise** — static file serving. `base.py` uses `CompressedManifestStaticFilesStorage`: `collectstatic` (in the `Dockerfile`) adds a content hash to each file name and gzips it, so browsers cache static files forever and still get new ones after a deploy. With `DEBUG=False`, a `{% static %}` path that doesn't exist makes the page fail with a 500 (`tests/test_static_files.py` checks the project templates). Development and test settings use Django's plain `StaticFilesStorage`, since there is no manifest there
- **django-debug-toolbar** — in the dev dependency group, loaded only by `development.py`; the production image doesn't install it
- **uv** — package/project manager (replaces pip/pipenv)
- **pytest + pytest-django + pytest-xdist** — parallel test runner

### Files kept from other projects

`make audit` checks only `uv.lock`. These files are copies in the repo: watch their projects' security notes and replace them by hand, checking the npm package's integrity hash where there is one.

| File | Version | Source | Licence |
|---|---|---|---|
| `static/js/highlight.min.js` | 11.11.2 | highlight.js | BSD-3-Clause |
| `static/js/easymde.min.js`, `static/css/easymde.min.css` | 2.21.0 | npm `easymde` (upgrade steps above) | MIT |
| `static/fonts/literata*.woff2` | 3.103 | Literata variable fonts, Latin subset made with fontTools | OFL 1.1 |
| `static/fonts/schibsted-grotesk.woff2` | 1.1 | Schibsted Grotesk variable font, Latin subset made with fontTools | OFL 1.1 |
| `static/icons/*.svg` except `github.svg` | 1.51.0 | npm `lucide-static` | ISC |
| `static/icons/github.svg` | 19.38.0 | npm `@primer/octicons` (`mark-github-16.svg`) | MIT |

## CI/CD

GitHub Actions workflow (`.github/workflows/django.yml`) runs on push/PR to `master`:
1. Starts PostgreSQL and Redis as service containers
2. Installs deps with `uv sync`
3. Runs `pytest` (parallel via `pytest-xdist`)

A push or PR that changes only `*.md` files or `docs/` doesn't start the workflow (`paths-ignore`); one other changed file runs everything. This relies on master having no required status checks: a skipped workflow never reports, so a required check would block docs-only PRs.

A separate `audit` job runs `make audit` and fails on any vulnerability not in `AUDIT_IGNORE`.

A `prod-image` job builds the production image, starts it with production settings and fake env values (no Redis or secrets needed) next to a Postgres set up by the production init script, runs `check --deploy --fail-level WARNING`, runs the migrations as the app's database role and checks that role has no special rights, runs `gunicorn --check-config`, checks that the container doesn't run as root, that `/api/` isn't routed, that no dev package (debug toolbar, pytest) is in the image and that `{% static %}` URLs are hashed. It then starts the whole stack with `docker compose -f docker-compose-prod.yml up` and a fake `.env`, the way the server does, and checks that `web` serves the home page (so its command migrated and started gunicorn) and that the Celery worker answers a ping through Redis. Any deploy warning fails it; the HSTS opt-ins `security.W005` / `security.W021` are silenced in `production.py`. The workflow token is read-only (`permissions: contents: read`), and the repo is public: never add real secrets or build args with secrets to CI.

## Front end

The pages use hand-written CSS: no Bootstrap, no jQuery, no icon font, nothing from a CDN. Forms are drawn by Django (`{{ form }}`), not crispy-forms.

- **`static/css/base.css`** is the site's stylesheet: colour and type tokens as CSS custom properties (`--ground`, `--surface`, `--ink`, `--quiet`, `--rule`, `--spruce`, `--lichen`, `--danger`), each colour written as `light-dark(light, dark)`, element defaults, the header and the user menu. Use the tokens, never a literal colour, so both palettes keep working
- **Light and dark**: the page's `color-scheme` picks the value: the system setting, unless the switch in the header (`.theme-toggle`, a moon or a sun from `static/icons/`) set `data-theme` on `<html>`. `static/js/theme.js` loads in `<head>` before the stylesheets and without `defer`, so a saved choice (`localStorage`, per browser, not on the account) applies before the page draws; it also shows the button, which is `hidden` without JavaScript. A new colour that differs between the palettes must be a `light-dark()` token: a `prefers-color-scheme` block would ignore the switch (`tests/test_theme_toggle.py`). The favicon follows the system setting only
- **Typefaces** are files in `static/fonts/` (SIL Open Font License, licence texts next to them): Literata (`--serif`) for titles and post text, Schibsted Grotesk (`--sans`) for the interface. They are Latin subsets with a weight range of 400 to 700, made from the upstream variable fonts with fontTools; `make audit` doesn't cover them
- **Layout**: `_base.html` has the header (`.site-header`) with the menu (*Forums*, *Latest*; the current section has `aria-current="page"`, set from `SECTIONS` by URL name in `forums/templatetags/nav.py`: a new page or menu item goes there; `tests/test_navigation.py`), the user menu and `<main class="wrap site-main">`. The menu is a `<details class="menu">`, so it works without JavaScript; `static/js/menu.js` only closes it on a click elsewhere or Escape
- **Lists** of forums and threads are `<ul class="rows">` with `.row` items inside one `.panel` per list, whose `.panel__head` row names the columns (`templates/forums/_thread_head.html` for thread lists; hidden on a phone). Forum rows (`.forum-row`, in `forum_list.html`) list two threads under the description, announcements first, then the most active, in a *Latest* box on the page's ground (`.forum-row__recent`), with the counts on the right. Thread rows (`.thread-row`, `templates/forums/_thread_row.html`; `show_forum` and `show_actions` are optional) put the replies and the last reply in columns, which fold into lines under the title on a phone (`.row-label` names them there). The data comes from `forums/activity.py`: `with_activity()` and `add_last_repliers()` for threads, `with_counts()` and `add_top_threads()` (a window function) for forums; each adds a fixed number of queries (`tests/forums/test_directory.py`). Page links are `templates/forums/_pages.html`, above and below the list. A member is shown with `templates/forums/_person.html`: a monogram disc (`user.monogram`: initials or the member number; `user.monogram_tone`: one of six colours, by id) and the display name
- **Where am I**: every forum page below the forum list starts with `templates/forums/_trail.html` (Forums › forum › thread; include it with `only`), and the forum and thread pages have a `.kicker` label (Forum, Thread) above the title (`tests/forums/test_trail.py`)
- **Thread page**: each post is a panel (`.post`, `static/css/thread.css`) headed by its author, time and number: the opening post is #1 (`.post--opening`, anchor `#opening`), replies are numbered on across pages (with 25 posts a page, the first reply on page 2 is #27), each number links to `?page=<n>#post-<id>`. Reply and Subscribe (`templates/forums/_thread_actions.html`) and the page links come at both ends; signatures are `templates/forums/_signature.html` (`tests/forums/test_post_panels.py`). `static/js/thread.js` colours the code blocks and wraps each in a `.code-block` with a *Copy* button (plain text to the clipboard; no button where the browser has no `navigator.clipboard`, i.e. on plain http outside localhost)
- **Dates** in lists use the `when` filter (`forums/templatetags/when.py`): "5 minutes ago", "yesterday", "4 days ago", then a date
- **Template comments**: `{# #}` works on one line only, and a longer one is printed on the page; use `{% comment %}` (`tests/test_no_inline_code.py` checks)
- **Buttons** are `.button` (plus `.button--quiet`, `.button--danger`). Bare `<button>` elements are not styled, because the editor's toolbar has its own; `tests/test_template_markup.py` fails on a `<button>` without the class or a Bootstrap class name in a template
- **Error pages** `403.html`, `404.html`, `500.html`: a title, one line and a link home. Django renders `500.html` without a request, so nothing in `_base.html` may need one (`tests/test_error_pages.py`)
- **Favicon**: `static/favicon.svg`, a W in a spruce disc like the members' monograms, with its own dark colours under `prefers-color-scheme`. Its light colours are attributes, since the CSP blocks the SVG's `<style>` when the file is opened on its own
- The tests don't run a browser. After changing styles, look at the pages in light and dark and at phone width

## Architecture Notes

- **Content Security Policy**: `project/middleware.py` adds the header to every response from `SECURE_CSP` in `base.py` (enforced; `DJANGO_CSP_REPORT_ONLY=true` moves the policy to `SECURE_CSP_REPORT_ONLY`, which only reports in the browser console). Scripts, styles and fonts from our own origin only (nothing comes from a CDN), `data:` and `https:` images, GitHub as a form target (the login redirect), no framing, and no `'unsafe-inline'`. Anything loaded from another site (a font, a CDN, an embedded frame) must be added to `_CSP` or browsers block it; `tests/test_csp.py` fails if a project template loads a script, style, image or frame from another site. The settings are named like Django 6's built-in CSP support, which replaces the middleware at that upgrade. Known and accepted: Django's debug 404 page and DRF's browsable API page each lose an inline style. The tests don't run a browser: after changing the policy or adding scripts, open the pages and look for violations in the console
- **No inline code in templates**: no `<script>` without `src`, no `<style>` block, no `style=` or `on...=` attribute (`tests/test_no_inline_code.py` checks the project templates). Scripts and styles go into files under `static/` (`css/base.css` for every page, `css/thread.css` and `js/thread.js` for the thread page, `css/editor.css` for the editor); pass values to a script with `data-` attributes, as `_editor.html` does.

- `AUTH_USER_MODEL = 'users.CustomUser'` — always reference `settings.AUTH_USER_MODEL` in ForeignKey, not the model directly
- `DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'` — integer PKs (not BigAutoField)
- `TIME_ZONE` comes from `DJANGO_TIME_ZONE` (default `UTC`): dates and times on the pages, in the admin and in emails are shown in that one zone for every member, summer time included; the database stores UTC (`USE_TZ`). `test.py` fixes it to `UTC`, so the tests don't follow the developer's `.env`; a test of another zone sets `settings.TIME_ZONE`
- **Languages**: `LANGUAGES` in `base.py` lists the interface's languages (`en`, `sv`); `LANGUAGE_CODE` (`DJANGO_LANGUAGE`) is the site's. `project.middleware.SiteLanguageMiddleware` activates the one in Django's language cookie if it is in the list, otherwise the site's; unlike Django's `LocaleMiddleware` it ignores the browser's `Accept-Language`, and it deactivates the language after the response. The admin (every address under `reverse('admin:index')`) is always English, also on a Swedish site: its login is allauth's page, which follows the visitor. No language prefixes in URLs. The notification, welcome and invitation mails are in the site's language: a Celery worker has no other, and in development, where tasks run inside the request, the tasks wrap their texts in `project.utils.site_language()`; so does `Post.notify_subscribers` for the author's name (`Member <id>`). A new mail to someone other than the one making the request needs it too (`tests/test_mail_language.py`). allauth's own mails (address confirmation, password reset) answer the visitor and follow their choice. `test.py` fixes `en`. **Marking texts**: every text a member sees goes through gettext. A text set when a module is imported (a model field's name or help text, a choice, a form label, a view's `success_message`) needs `gettext_lazy`, or it is translated once at import; a text made during a request uses `gettext`, a count `ngettext`, and values go in with `%(name)s`, not an f-string. Model fields shown in forms have a `verbose_name` for that reason (lowercase; Django capitalises the label), which costs a migration without SQL (`forums/0024`). `__str__`, the admin and the security log stay English, as do the API's error texts. In a template every text is inside `{% translate %}` or `{% blocktranslate %}` (`{% load i18n %}` in each file, includes too): a sentence with a link or a value is one `blocktranslate` with the address from `{% url ... as %}`, a count uses `{% blocktranslate count %}` (not `pluralize`), and a text passed to an include is made first with `{% translate ... as %}`. `tests/test_templates_translated.py` fails on a word left outside those tags in any template, pages and mails. `_base.html` sets `<html lang>` from the page's language with `{% get_current_language %}`, which needs no request (`500.html`). **Texts in scripts**: a script has no texts of its own. The template that loads it passes each one, translated, as a `data-` attribute on the script tag, and the script reads them from `document.currentScript.dataset` into a variable named `text` (`_editor.html` for `editor.js`: button titles and the preview's messages; `thread_detail.html` for `thread.js`: the Copy button). A new text needs both; `tests/forums/test_script_texts.py` fails when a script reads one its template doesn't pass, or has a text in quotes. Work in progress: the Python code, every template and the scripts are marked, there is no `locale/` catalog and no switcher, so `sv` only changes Django's and allauth's own texts. Tests: `tests/test_language.py`, `tests/forums/test_translatable.py` (its `marked` fixture puts every translated text in brackets)
- `SITE_ID = 1` — required by `django.contrib.sites`. Its display name follows `SiteSettings.title` (saved there, never edited in *Sites*); its domain is set in *Sites*. Our own email links use `SITE_URL`, not the *Sites* domain
- CORS: `development.py` allows `localhost:3000` / `127.0.0.1:3000` (for a local frontend client); production allows no other origin
- Admin URL is configurable via `ADMIN_URL` env var (defaults to `nimda`) as a security measure

## General Rules

Before writing any code, describe your approach and wait for approval.

If the requirements I give you are ambiguous, ask clarifying questions before writing any code.

After you finish writing any code, list the edge cases and suggest test cases to cover them.

If a task requires changes to more than 3 files, stop and break it into smaller tasks first.

When there's a bug, start by writing a test that reproduces it, then fix it until the test passes.

Every time I correct you, reflect on what you did wrong and come up with a plan to never make the same mistake again.

Never push to remote repositories. When changes are ready to push, tell the user to run `git push` instead.

Always ask for approval before committing. Show the user what will be committed and wait for confirmation.
