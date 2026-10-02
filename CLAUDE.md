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

Production runs `docker-compose-prod.yml` on a VPS behind a reverse proxy container (Caddy). The stack publishes no ports: only `web` joins the shared `forum_proxy` network, where the proxy reaches it as `forum-web:8000`. See `docs/deployment-vps.md` for the proxy config, the `.env` checklist, first deploy, updates, backups and troubleshooting.

The `Dockerfile` installs only runtime dependencies by default (`ARG UV_SYNC_FLAGS=--no-dev`); `docker-compose-dev.yml` passes an empty value so dev images also get the dev group (pytest etc.). `.dockerignore` keeps `.env`, `.git` and `.venv` out of the image; compose passes `.env` in at runtime via `env_file`.

The image runs as the unprivileged user `app` (uid 1000); the code and the venv belong to root, so the app can't write under `/code` or `/opt/venv` in production: anything it must write goes to `/tmp`. In development the mounted repo belongs to the host user, normally also uid 1000, so files written by the containers (migrations) get the right owner; with another host uid, add `user:` to the services in `docker-compose-dev.yml`. Redis gets its password from a config file written at container start, not from its command line, and runs as `redis`. Production has no `celery-beat` service (nothing is scheduled); the dev one keeps its schedule file in `/tmp`.

gunicorn's settings are in `gunicorn.conf.py` (address, 2 workers with 4 threads each; `WEB_CONCURRENCY` changes the worker count; its control socket is off, since it would be a file in `/code`). The compose command is just `gunicorn project.wsgi`: flags on the command line would win over the file.

uv is pinned to an exact version (`COPY --from=ghcr.io/astral-sh/uv:<version>` in the `Dockerfile`). `make audit` doesn't cover it, so bump it when upgrading dependencies, and check uv's release notes for security fixes.

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
  utils.py         # send_mail helper (BCC via the configured email backend)

forums/            # Core app — Forum, Thread, Post, UpVote, Notification, UserProfile models
  models.py        # All core models; a django-lifecycle hook on Post sends the notifications
  views.py         # Class-based views (ListView, DetailView, CreateView, etc.)
  urls.py          # Forum URL patterns
  forms.py         # SearchForm
  tasks.py         # Celery tasks (send_notifications_task)
  throttling.py    # Posting, search and preview limits: DRF throttles, shared by the web views and the API
  signals.py       # Django signals (if any)
  templatetags/    # Custom template tags (class_name)

users/             # Custom user model (email-based auth)
  models.py        # CustomUser extends AbstractUser; sends welcome email on create
  audit.py         # Security log: log_event, signal receivers, refused-request middleware
  tasks.py         # Celery task send_welcome_email_task

pages/             # Static pages (home, etc.)
api/               # Django REST Framework API
  views.py         # ModelViewSet for Forum, Thread, Post, User
  serializers.py   # No nested lists: Forum has thread_count, Thread has post_count
  urls.py          # DRF router + schema endpoint
  permissions.py   # IsOwnerOrModeratorOrReadOnly custom permission

tests/             # pytest test suite
templates/         # HTML templates (extends _base.html)
static/            # Static file sources (CSS, Font Awesome, bootstrap-social, highlight.js, EasyMDE); collected into staticfiles/ at image build, not committed
```

## Data Models

### Forum
- `title` (CharField, max 200)
- `description` (CharField, max 500)
- Ordered by `title`

### Thread
- `title` (CharField, max 300)
- `text` (TextField — Markdown, max 20 000 characters)
- `added`, `edited` (DateTimeField)
- `forum` (ForeignKey → Forum)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Ordered by `-added`

### Post
- `text` (TextField — Markdown, max 20 000 characters)
- `upvotes` (IntegerField, default 0)
- `added`, `edited` (DateTimeField)
- `thread` (ForeignKey → Thread)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Ordered by `added`
- **Lifecycle hooks**:
  - `notify_subscribers` (AFTER_CREATE, after the commit): queues `send_notifications_task` via Celery (skipped in CI). Only active subscribers whose address is verified (allauth's `EmailAddress`) get the mail, so test subscribers need `verify_email`. Tests need `django_capture_on_commit_callbacks(execute=True)` to see it run

### UserProfile
- One-to-one with AUTH_USER_MODEL
- Fields: `first_name`, `last_name`, `bio`, `location`, `gender` (TextChoices), `web_site`, `github_url`, `signature` (max 500 characters)
- The `max_length` of the text fields and the signature (`MAX_TEXT_LENGTH`, `MAX_SIGNATURE_LENGTH` in `forums/models.py`) is checked by the forms and the API, not by the database; the editor preview refuses longer text too

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
- `send_welcome_mail` lifecycle hook fires after the user creation commits (`on_commit=True`) and queues `send_welcome_email_task`

### Invitation (`users.Invitation`)
- `email`, `key` (random, unique), `invited_by`, `created`, `sent_at`, `accepted_at`, `accepted_by`
- Valid while unused and younger than `INVITATION_EXPIRY_DAYS` (7, in `base.py`): `Invitation.objects.valid()` / `is_valid()`
- Created in the Django admin (needs `users.add_invitation`). The add form (`InvitationAdminForm`) refuses addresses with an account or a pending invitation. Saving queues `send_invitation_email_task` on commit; the *Resend invitation* action calls `renew()` (new key, expiry restarts) and sends again. `get_link()` builds the link from `SITE_URL`
- The link `/accounts/invite/<key>/` stores the key in the session (`Invitation.SESSION_KEY`) and stashes the address as verified, then redirects to signup. While signup is closed, it opens signup for that address only: the signup form refuses other addresses, and a GitHub signup needs the address among GitHub's verified emails. allauth's `user_signed_up` signal marks it used (`users/models.py`)

## URL Structure

```
/                          → pages (home)
/forums/                   → ForumsList
/forums/<pk>/              → ForumDetail (20 threads per page, newest first; ?page=<n>)
/forums/add/               → ForumCreate (requires forums.add_forum permission)
/forums/<pk>/update/       → ForumUpdate (requires forums.change_forum permission)
/forums/<pk>/add/          → ThreadCreate (login required)
/forums/<fpk>/delete/<pk>  → ThreadDelete (owner or forums.delete_thread)
/forums/thread/<pk>        → ThreadDetail (25 posts per page, oldest first; ?page=<n> or ?page=last)
/forums/thread/<pk>/update/→ ThreadUpdate (owner or forums.change_thread)
/forums/thread/<pk>/notify → ThreadNotification (toggle subscription)
/forums/thread/<pk>/post   → PostCreate (then the thread's last page)
/forums/thread/<tpk>/post/<pk>/delete  → PostDelete
/forums/thread/<tpk>/post/<pk>/upvote  → PostUpvote
/forums/search/            → SearchResultsView (?q= of at least 3 characters; the 50 newest posts and 50 newest threads; 20 a minute)
/forums/preview/           → MarkdownPreview (POST, login required: Markdown text → HTML for the editor's preview)

/api/forums/               → ForumViewSet (read for anyone; write needs forums.add/change/delete_forum)
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

The Redis cache (`CACHES` in `base.py`) is still used by allauth's rate limits. If Redis is down, the login, signup and password reset pages fail with a 500 rather than run without rate limits: a deliberate choice. Tests use an in-memory cache, cleared around every test (root `conftest.py`).

## Authentication & Permissions

- `django-allauth` handles auth with email-only login (no username required)
- **Email addresses must be confirmed** (`ACCOUNT_EMAIL_VERIFICATION = 'mandatory'` in `base.py`, every environment): signup mails a link and logs nobody in before it is used. allauth checks at every login, so an account made without signup (`createsuperuser`, the admin) gets the mail at its first login; in development the link is printed to the console. Invitation and GitHub signups arrive verified. Tests that log in through the login form need the `verify_email` fixture (root `conftest.py`); `force_login` and API tokens don't
- GitHub OAuth social login is configured (`allauth.socialaccount.providers.github`)
- Two-factor login (`allauth.mfa`, needs the `django-allauth[mfa]` extra): optional for every user, an authenticator app (TOTP) plus recovery codes, no passkeys (`MFA_SUPPORTED_TYPES` in `base.py`). Users turn it on under *Two-factor authentication* in the user menu; after that both password and GitHub logins ask for a code. allauth refuses setup while the account has an unverified email address
- allauth's rate limits (failed logins, signups, password resets) are partly per client address. Production sets `ALLAUTH_TRUSTED_PROXY_COUNT = 1`, so the address comes from the last `X-Forwarded-For` entry (the one the reverse proxy adds) instead of the proxy's own. Production only: without a proxy the header can be forged. A second proxy in front needs a count of 2
- allauth pages without a template of our own (the two-factor pages) get the site layout from `templates/allauth/layouts/base.html`, which extends `_base.html`
- The API is throttled (`REST_FRAMEWORK` in `base.py`): 60 requests a minute per address for anonymous clients, 120 per user when logged in; over that it answers 429, which the security log records as `denied status=429`. `NUM_PROXIES` is `0` in `base.py` and `1` in production, like `ALLAUTH_TRUSTED_PROXY_COUNT`; a second proxy needs 2. The counters are in the cache, so the API fails while Redis is down. DRF reads the rates at import: tests change them with the `rates` fixture in `tests/forums/conftest.py`
- **Posting limit**: a user may create 5 threads or posts a minute and 30 an hour (`posting_burst`, `posting_hour` in `DEFAULT_THROTTLE_RATES`), counted together for the website and the API, staff and moderators included. `forums/throttling.py` has the two DRF throttles; `PostingLimitMixin` in `forums/views.py` (the form comes back with status 429 and the text kept; forms with errors don't count) and in `api/views.py` (on `create`) use them. A new view that creates threads or posts needs the mixin too
- **Search and preview limits**: 20 searches a minute per user (per address for visitors; searches too short to run don't count) and 30 Markdown previews a minute per user (`search`, `preview` in `DEFAULT_THROTTLE_RATES`; `SearchThrottle`, `PreviewThrottle` in `forums/throttling.py`). Over the limit the search page says so with status 429 and runs no query; the editor shows that the preview could not be loaded
- Session + Token authentication for the REST API. The API has no login page of its own (DRF's `api-auth/` would skip the two-factor step): log in on the site
- **Staff and moderators must use two-factor authentication** while `STAFF_REQUIRE_MFA` is on (default; off in development). It applies to every privileged user (`users.security.is_privileged`): staff, superusers, and anyone holding a permission, directly or through a group such as Moderators. Members have no permissions:
  - `admin.site.login` is wrapped in allauth's `secure_admin_login` (`project/urls.py`), so the admin uses allauth's login with its code prompt
  - `users.security.StaffMFAMiddleware` redirects a privileged user without an authenticator app to `mfa_index` from every page except those under `/accounts/` (login, logout, address confirmation, the two-factor pages); under `/api/` it answers 403 instead. Recovery codes alone don't count
  - `api.authentication.NonStaffTokenAuthentication` refuses tokens of privileged accounts (403): they use the API with a session
  - `python manage.py remove_mfa <email>` deletes a user's authenticators (lost phone); the user then logs in with the password alone and sets it up again. Switching `DJANGO_STAFF_REQUIRE_MFA` off doesn't help there: login still asks for the code
  - The admin's user form (`CustomUserChangeForm.clean`) refuses staff status, superuser status, a group or a permission for an account without an authenticator app: whoever logs in to such an account gets to set one up, so rights must come after it. The user list has a *Two-factor* column. `createsuperuser` bypasses the form: set that account up right away
  - Tests: privileged users need the `add_totp` fixture (root `conftest.py`) to use the site; `get_user_client` gives them a session instead of a token
- Permission checks: Django model permissions for forum creation and editing; `UserPassesTestMixin` for thread edit/delete and post delete (owner, or a user with `forums.change_thread` / `forums.delete_thread` / `forums.delete_post`)
- **Moderators group**: created by migration `forums/0016_moderators_group` with exactly `change_thread`, `delete_thread` and `delete_post`, so members can edit and delete other users' threads and delete their posts, on the website and through the API. Add users to it in the Django admin, once they have an authenticator app
- Custom API permission: `IsOwnerOrModeratorOrReadOnly` — safe methods allowed for anyone; write allowed for the owner (`obj.user == request.user`) or a user with the matching model permission (`change_<model>` for PUT/PATCH, `delete_<model>` for DELETE), same as the web views

## Logging

`LOGGING` in `base.py` sends everything from INFO up to stdout with a timestamp (container clock, UTC); errors are still mailed to `DJANGO_ADMINS`. In production the containers log to the host's journal (`logging: *journald` in `docker-compose-prod.yml`), so logs survive container recreation; retention is set in the server's `journald.conf` (see `docs/deployment-vps.md`).

The **security log** is the `security` logger: one line per event, `event key=value ...`, with user ids and the client address (the one allauth's rate limits use). Write to it with `users.audit.log_event(event, request, **fields)`; pass text a visitor typed through `quoted()`. Never log passwords, codes, tokens, invitation keys or email addresses of accounts (only the address typed at a failed login).

- `users/audit.py`: signal receivers for login, logout, failed login, signup, password and email changes, two-factor changes and wrong codes; `DeniedRequestLogMiddleware` logs every 401, 403 and 429 response; `log_moderation(request, action, obj)` logs a change to a thread or post by someone other than its author
- Moderation is logged by `ThreadUpdate`, `ThreadDelete`, `PostDelete` (`forums/views.py`) and `ModerationLogMixin` (`api/views.py`): a new view that edits or deletes other users' content must call `log_moderation` too
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
| `ENVIRONMENT` | `development`, `production`, `CI`, or `test` |
| `DJANGO_SETTINGS_MODULE` | `project.settings.development` for local/Docker dev (otherwise `manage.py` uses `base`, Celery uses `production`) |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Production SMTP server and login. All three are required: production refuses to start (`ImproperlyConfigured`) if any is missing, unless `DJANGO_EMAIL_CONSOLE=true` |
| `DJANGO_EMAIL_CONSOLE` | Production only: `true` to print mail to the console instead of SMTP, e.g. for trying out the production compose file locally |
| `EMAIL_PORT` / `EMAIL_USE_TLS` | Optional SMTP settings (default: `587`, `true` for STARTTLS) |
| `DEFAULT_FROM_EMAIL` | Optional sender address (default: `EMAIL_HOST_USER`) |
| `DJANGO_ADMINS` | Optional: comma-separated email addresses that Django's default logging mails the traceback of every 500 when `DEBUG=False`. Empty means no error mails. Addresses only: Django never uses the name, and Django 6 drops the `(name, address)` pairs `base.py` still builds for 5.2 |
| `REDIS_URL` | Redis URL (default: `redis://redis:6379/0`). The database number is replaced: cache uses `/0`, Celery uses `/1`. Set automatically by `docker-compose-prod.yml` |
| `REDIS_LOCALHOST` | Set to `true` when using local Redis |
| `POSTGRES_PASSWORD` | `docker-compose-prod.yml` only (required): Postgres password; also used to build `DATABASE_URL`. Use URL-safe characters |
| `REDIS_PASSWORD` | `docker-compose-prod.yml` only (required): Redis password; also used to build `REDIS_URL`. Use URL-safe characters |
| `ADMIN_URL` | Custom admin path (default: `nimda`) |
| `DJANGO_SIGNUP_OPEN` | `true` lets anyone sign up (email or GitHub). Closed by default; `development.py` and `test.py` open it. `users/adapters.py` decides: signup is open if this is true or the session holds a valid invitation, which then limits signup to the invited address (`AccountAdapter.clean_email` on the signup pages, `SocialAccountAdapter.is_open_for_signup` for GitHub). The navbar hides the link via `{% signup_is_open %}` (`users/templatetags/signup.py`) |
| `DJANGO_STAFF_REQUIRE_MFA` | Staff, moderators and anyone else with a permission need an authenticator app to use the site, and their API tokens are refused (`settings.STAFF_REQUIRE_MFA`). Default `true`; `development.py` defaults to `false` |
| `DJANGO_SITE_URL` | The site's public address, for links in emails (`settings.SITE_URL`; used by `Invitation.get_link()` and `Post.notify_subscribers`). Required in production, where it must be `https` without a path (`ImproperlyConfigured` otherwise); elsewhere it defaults to `http://127.0.0.1:8000`. |
| `DJANGO_ALLOWED_HOSTS` | Production only: comma-separated hosts, e.g. `forum.example.com`. Also sets `CSRF_TRUSTED_ORIGINS`. If empty, every request gets a 400 |
| `DJANGO_SECURE_HSTS_SECONDS` | Production HSTS max-age (default: `3600`) |
| `WEB_CONCURRENCY` | Production only: number of gunicorn worker processes (default: `2`), read by `gunicorn.conf.py` |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | Opt-in HSTS flags (default: `false`) |

## Services

- **PostgreSQL**: Database (host: `db` in Docker, `localhost` for CI; credentials: `postgres/postgres` in dev and CI, `POSTGRES_PASSWORD` in production)
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
- **markdown-it-py + nh3** — render thread and post text (`forums/markdown.py`, template filter `render_markdown`). Raw HTML in the text is off, so it shows as text; nh3 then keeps only the listed tags, attributes and URL schemes (`http`, `https`, `mailto`). A new Markdown feature needs both the parser rule and the tag in `ALLOWED_TAGS`. Code blocks on the thread page are coloured by highlight.js, a single file kept in `static/js/highlight.min.js` (`make audit` doesn't cover it: replace the file to upgrade)
- **EasyMDE** — Markdown editor on the thread and post forms: `templates/forums/_editor.html` loads `static/js/easymde.min.js`, its stylesheet and our `static/js/editor.js` (toolbar, settings). The preview button posts the text to `/forums/preview/`, so it shows what the saved text will look like. Without JavaScript the plain textarea still works. Like highlight.js it is a file in `static/` that `make audit` doesn't cover; it loads nothing from other sites (its spell checker and Font Awesome download are off). To upgrade it:
  1. Replace the two `easymde.min.*` files with the ones from the new npm package (check its integrity hash) and read the release notes for renamed options and anything new that loads from another site
  2. The tests don't run JavaScript, so check in a browser, logged in, on the new thread, new post and edit thread pages: the toolbar is on one line with all icons, the preview matches the saved result, the Markdown hint under the field is hidden, an empty text shows the form error, and the edit page loads the saved text
  3. If the toolbar wraps, see the `button.table` rule in `_editor.html` (EasyMDE's class name clashes with Bootstrap's `.table`)
- **django-allauth** — authentication + GitHub OAuth
- **djangorestframework** — REST API
- **inflection, uritemplate, pyyaml** — needed by DRF's OpenAPI schema (`/api/schema/`); nothing imports them directly, so keep them in the main dependencies
- **django-redis** — Redis cache backend
- **celery** — async task queue
- **whitenoise** — static file serving. `base.py` uses `CompressedManifestStaticFilesStorage`: `collectstatic` (in the `Dockerfile`) adds a content hash to each file name and gzips it, so browsers cache static files forever and still get new ones after a deploy. With `DEBUG=False`, a `{% static %}` path that doesn't exist makes the page fail with a 500 (`tests/test_static_files.py` checks the project templates). Development and test settings use Django's plain `StaticFilesStorage`, since there is no manifest there
- **django-debug-toolbar** — in the dev dependency group, loaded only by `development.py`; the production image doesn't install it
- **uv** — package/project manager (replaces pip/pipenv)
- **pytest + pytest-django + pytest-xdist** — parallel test runner

## CI/CD

GitHub Actions workflow (`.github/workflows/django.yml`) runs on push/PR to `master`:
1. Starts PostgreSQL and Redis as service containers
2. Installs deps with `uv sync`
3. Runs `pytest` (parallel via `pytest-xdist`)

A push or PR that changes only `*.md` files or `docs/` doesn't start the workflow (`paths-ignore`); one other changed file runs everything. This relies on master having no required status checks: a skipped workflow never reports, so a required check would block docs-only PRs.

A separate `audit` job runs `make audit` and fails on any vulnerability not in `AUDIT_IGNORE`.

A `prod-image` job builds the production image, starts it with production settings and fake env values (no database, Redis or secrets needed), runs `check --deploy --fail-level WARNING`, runs `gunicorn --check-config` (nothing else in CI starts gunicorn), checks that the container doesn't run as root, that no dev package (debug toolbar, pytest) is in the image and that `{% static %}` URLs are hashed. Any deploy warning fails it; the HSTS opt-ins `security.W005` / `security.W021` are silenced in `production.py`. The workflow token is read-only (`permissions: contents: read`), and the repo is public: never add real secrets or build args with secrets to CI.

## Architecture Notes

- `AUTH_USER_MODEL = 'users.CustomUser'` — always reference `settings.AUTH_USER_MODEL` in ForeignKey, not the model directly
- `DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'` — integer PKs (not BigAutoField)
- `SITE_ID = 1` — required by `django.contrib.sites`, which allauth uses for the site name in its emails. Our own email links use `SITE_URL`, not the *Sites* domain
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
