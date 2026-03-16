# CLAUDE.md

## Project Overview

Django-based discussion forum platform with forums, threads, posts, user authentication, REST API, and email notifications.

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
2. Install dependencies: `pip install -r requirements.txt`
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

Tests use `project.settings.test` settings. Coverage is configured in `.coveragerc`.

## Key Commands (Makefile)

```bash
make dev_web_exec cmd='python manage.py migrate'        # Run management commands
make dev_web_exec cmd='python manage.py createsuperuser'
make dev_web_exec cmd='python manage.py collectstatic --noinput'
```

## Project Structure

```
project/        # Django project settings (base, development, production, test, ci)
forums/         # Core forums app (Forum, Thread, Post, Notification, UpVote models)
users/          # Custom user model (email-based auth) + UserProfile
pages/          # Static pages
api/            # Django REST Framework API
tests/          # pytest test suite
templates/      # HTML templates
```

## Environment Variables

Required in a `.env` file:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `ENVIRONMENT` | `development`, `production`, `CI`, or `test` |
| `DEBUG` | `True` for development |
| `SENDGRID_USERNAME` | Email sending (optional, defaults to console backend) |
| `SENDGRID_PASSWORD` | Email sending (optional) |
| `SENTRY_KEY` | Error tracking (optional) |
| `SENTRY_PROJECT` | Error tracking (optional) |
| `ADMIN1` | Admin contact, format: `Name, email@example.com` |
| `ADMIN2` | Admin contact, format: `Name, email@example.com` |
| `REDIS_URL` | Redis URL (default: `redis://redis:6379/0`) |
| `REDIS_LOCALHOST` | Set to `true` when using local Redis |

## Services

- **PostgreSQL**: Database (host: `db` in Docker, `localhost` locally; credentials: `postgres/postgres`)
- **Redis**: Caching and Celery message broker
- **Celery**: Async task queue for email notifications

## Settings Modules

- `project.settings.base` — Shared configuration
- `project.settings.development` — Local development
- `project.settings.test` — Testing (used by pytest)
- `project.settings.ci` — CI/CD pipelines
- `project.settings.production` — Production deployment

## Architecture Notes

- Custom user model uses email instead of username (`users.CustomUser`)
- Thread and Post models use `django-lifecycle` hooks for notifications
- Markdown editing via `martor`
- GitHub OAuth login via `django-allauth`
- API built with Django REST Framework
