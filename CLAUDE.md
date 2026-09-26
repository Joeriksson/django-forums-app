# CLAUDE.md

## Project Overview

Django-based discussion forum platform with forums, threads, posts, user authentication, REST API, and email notifications. Built with Django 4.2, Python 3.12, and managed with `uv`.

## Development Setup

### Using Docker (Recommended)

```bash
make dev_build   # Build and start all containers
make dev         # Start containers (already built)
make dev_logs    # View logs
make dev_down    # Stop containers
```

### Manual Setup

1. Create a `.env` file with required variables (see below)
2. Install dependencies: `uv sync`
3. Apply migrations: `python manage.py migrate --settings=project.settings.development`
4. Create superuser: `python manage.py createsuperuser --settings=project.settings.development`
5. Run server: `python manage.py runserver --settings=project.settings.development`

Server runs at `http://127.0.0.1:8000`

## Running Tests

```bash
# Docker
make dev_pytest        # Run pytest
make dev_test          # Run Django test runner (parallel)

# Manual
pytest tests/ -v --disable-warnings
python manage.py test --settings=project.settings.test --parallel
```

Tests use `project.settings.test` settings. Coverage and pytest configuration are in `pyproject.toml`. Tests run in parallel (`-n auto`) via `pytest-xdist`.

### Test Structure

```
tests/
└── forums/
    ├── conftest.py              # Fixtures (users, forums, threads, posts)
    ├── test_models.py           # Model unit tests
    ├── test_serializers.py      # DRF serializer tests
    ├── test_views_forums.py     # Forum view tests
    ├── test_views_posts.py      # Post view tests
    └── test_views_threads.py    # Thread view tests
```

There are also legacy test files: `forums/tests.py`, `users/tests.py`, `pages/tests.py`, `api/tests.py`.

## Key Commands (Makefile)

```bash
make dev_web_exec cmd='python manage.py migrate'          # Run management commands
make dev_web_exec cmd='python manage.py createsuperuser'
make dev_web_exec cmd='python manage.py collectstatic --noinput'
make dev_export_data                                       # Export DB as JSON fixture
make dev_redis_exec cmd='redis-cli'                        # Access Redis CLI
```

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
  models.py        # All core models with django-lifecycle hooks and Redis cache invalidation
  views.py         # Class-based views (ListView, DetailView, CreateView, etc.)
  urls.py          # Forum URL patterns
  forms.py         # SearchForm
  tasks.py         # Celery tasks (send_notifications_task)
  signals.py       # Django signals (if any)
  templatetags/    # Custom template tags (class_name)
  management/      # Custom management commands

users/             # Custom user model (email-based auth)
  models.py        # CustomUser extends AbstractUser; sends welcome email on create

pages/             # Static pages (home, etc.)
api/               # Django REST Framework API
  views.py         # ModelViewSet for Forum, Thread, Post, User
  serializers.py   # Nested serializers (Thread includes Posts, Forum includes Threads)
  urls.py          # DRF router + schema endpoint
  permissions.py   # IsOwnerOrReadOnly custom permission

tests/             # pytest test suite
templates/         # HTML templates (extends _base.html)
static/            # Static files (CSS)
```

## Data Models

### Forum
- `title` (CharField, max 200)
- `description` (CharField, max 500)
- Ordered by `title`

### Thread
- `title` (CharField, max 300)
- `text` (MartorField — Markdown)
- `added`, `edited` (DateTimeField)
- `forum` (ForeignKey → Forum)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Ordered by `-added`
- **Lifecycle hooks**: invalidates Redis cache key `thread_objects_forum_<forum_id>` on save/delete/create

### Post
- `text` (MartorField — Markdown)
- `upvotes` (IntegerField, default 0)
- `added`, `edited` (DateTimeField)
- `thread` (ForeignKey → Thread)
- `user` (ForeignKey → AUTH_USER_MODEL)
- Ordered by `added`
- **Lifecycle hooks**:
  - `notify_subscribers` (AFTER_CREATE): triggers `send_notifications_task` via Celery (skipped in CI)
  - `invalidate_cache` (AFTER_SAVE/DELETE/CREATE): invalidates `post_objects_thread_<thread_id>`

### UserProfile
- One-to-one with AUTH_USER_MODEL
- Fields: `first_name`, `last_name`, `bio`, `location`, `gender` (TextChoices), `web_site`, `github_url`, `signature`

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
- Uses **email** for authentication (not username)
- `send_welcome_mail` lifecycle hook fires on user creation

## URL Structure

```
/                          → pages (home)
/forums/                   → ForumsList
/forums/<pk>/              → ForumDetail
/forums/add/               → ForumCreate (requires forums.add_forum permission)
/forums/<pk>/update/       → ForumUpdate (requires forums.change_forum permission)
/forums/<pk>/add/          → ThreadCreate (login required)
/forums/<fpk>/delete/<pk>  → ThreadDelete (owner or forums.delete_thread)
/forums/thread/<pk>        → ThreadDetail
/forums/thread/<pk>/update/→ ThreadUpdate (owner or forums.change_thread)
/forums/thread/<pk>/notify → ThreadNotification (toggle subscription)
/forums/thread/<pk>/post   → PostCreate
/forums/thread/<tpk>/post/<pk>/delete  → PostDelete
/forums/thread/<tpk>/post/<pk>/upvote  → PostUpvote
/forums/search/            → SearchResultsView

/api/forums/               → ForumViewSet (read-only anon, write authenticated)
/api/threads/              → ThreadViewSet (IsOwnerOrReadOnly)
/api/posts/                → PostViewSet (IsOwnerOrReadOnly)
/api/users/                → UserViewSet (IsAdminUser only)
/api/schema/               → OpenAPI schema
/api/api-auth              → DRF browsable API login

/accounts/                 → django-allauth (login, signup, social auth)
/user_profile/<pk>         → UserProfileUpdate
/<ADMIN_URL>/              → Django admin (default: /nimda/)
/martor/                   → Martor markdown endpoints
/__debug__/                → Django Debug Toolbar (DEBUG only)
```

## Caching

Redis is used for object-level caching:
- `thread_objects_forum_<forum_id>` — cached queryset of threads for a forum
- `post_objects_thread_<thread_id>` — cached queryset of posts for a thread

Cache is invalidated automatically via `django-lifecycle` hooks on model save/delete/create.

## Authentication & Permissions

- `django-allauth` handles auth with email-only login (no username required)
- GitHub OAuth social login is configured (`allauth.socialaccount.providers.github`)
- Session + Token authentication for the REST API
- Permission checks: Django model permissions for forum creation; `UserPassesTestMixin` (owner check) for thread/post edit/delete
- Custom API permission: `IsOwnerOrReadOnly` — safe methods allowed for anyone, write requires `obj.user == request.user`

## Async Tasks (Celery)

- Broker and result backend: Redis
- `send_notifications_task`: sends BCC email to thread subscribers when a new post is created
- Outside production, `CELERY_TASK_ALWAYS_EAGER = True` and `CELERY_TASK_EAGER_PROPAGATES = True`: tasks run synchronously in the web process and their errors are raised there, so the Celery worker is idle in dev
- Tasks skipped entirely in CI (`os.environ.get('CI')` check in `Post.notify_subscribers`)

## Environment Variables

Required in a `.env` file:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `ENVIRONMENT` | `development`, `production`, `CI`, or `test` |
| `DJANGO_SETTINGS_MODULE` | `project.settings.development` for local/Docker dev (otherwise `manage.py` uses `base`, Celery uses `production`) |
| `DEBUG` | `True` for development |
| `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Production SMTP server and login. When all three are set, production sends via SMTP; otherwise it uses the console backend |
| `EMAIL_PORT` / `EMAIL_USE_TLS` | Optional SMTP settings (default: `587`, `true` for STARTTLS) |
| `DEFAULT_FROM_EMAIL` | Optional sender address (default: `EMAIL_HOST_USER`) |
| `SENTRY_KEY` | Error tracking (optional, production only) |
| `SENTRY_PROJECT` | Error tracking (optional, production only) |
| `ADMIN1` | Admin contact, format: `Name, email@example.com` |
| `ADMIN2` | Admin contact, format: `Name, email@example.com` |
| `REDIS_URL` | Redis URL (default: `redis://redis:6379/0`) |
| `REDIS_LOCALHOST` | Set to `true` when using local Redis |
| `ADMIN_URL` | Custom admin path (default: `nimda`) |
| `DJANGO_ALLOWED_HOSTS` | Production only: comma-separated hosts, e.g. `forum.example.com`. Also sets `CSRF_TRUSTED_ORIGINS`. If empty, every request gets a 400 |
| `DJANGO_SECURE_HSTS_SECONDS` | Production HSTS max-age (default: `3600`) |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | Opt-in HSTS flags (default: `false`) |

## Services

- **PostgreSQL**: Database (host: `db` in Docker, `localhost` for CI; credentials: `postgres/postgres`)
- **Redis**: Caching and Celery message broker
- **Celery**: Async task queue for email notifications
- **Email**: SMTP in production when `EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` are set, console backend otherwise
- **Sentry**: Error tracking in production
- **Whitenoise**: Static file serving

## Settings Modules

- `project.settings.base` — Shared configuration (all environments inherit this)
- `project.settings.development` — Local development
- `project.settings.test` — Testing (used by pytest, configured in `pyproject.toml`). CI uses it too; `ENVIRONMENT=CI` switches the database in `base.py`
- `project.settings.production` — Production deployment

## Key Dependencies

- **Django 4.2** — web framework
- **django-lifecycle** — model hooks (`@hook` decorator) for cache invalidation and notifications
- **martor** — Markdown editor widget (`MartorField`)
- **django-allauth** — authentication + GitHub OAuth
- **djangorestframework** — REST API
- **django-redis** — Redis cache backend
- **celery** — async task queue
- **whitenoise** — static file serving
- **uv** — package/project manager (replaces pip/pipenv)
- **pytest + pytest-django + pytest-xdist** — parallel test runner

## CI/CD

GitHub Actions workflow (`.github/workflows/django.yml`) runs on push/PR to `master`:
1. Starts PostgreSQL and Redis as service containers
2. Installs deps with `uv sync`
3. Runs both `python manage.py test` and `pytest` in parallel

## Architecture Notes

- `AUTH_USER_MODEL = 'users.CustomUser'` — always reference `settings.AUTH_USER_MODEL` in ForeignKey, not the model directly
- `DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'` — integer PKs (not BigAutoField)
- `SITE_ID = 1` — required by `django.contrib.sites` (used for notification email URLs)
- CORS allowed from `localhost:3000` / `127.0.0.1:3000` (for potential frontend clients)
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
