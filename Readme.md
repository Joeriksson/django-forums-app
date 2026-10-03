![django test workflow](https://github.com/joeriksson/django-forums-app/actions/workflows/django.yml/badge.svg)

# Wildvasa Forums App

A private discussion forum built with Django. Members read and write in forums, threads and replies; new members join by invitation, or by signing up while signup is open.

## Features

- **Forums and threads**: Markdown replies with an editor and preview, announcements, upvotes, recent activity, full-text search with filters, email notifications for subscribed threads
- **Members**: sign in with email or GitHub, invitations, confirmed email addresses, optional two-factor authentication (required for staff and moderators), profile names shown instead of usernames
- **Moderation**: a Moderators group that can edit and delete others' threads and posts, and a security log
- **Site**: hand-written CSS with light and dark palettes, self-hosted fonts, a strict Content Security Policy, nothing loaded from a CDN, an optional REST API

## Tech stack

Python 3.12 · Django 5.2 · PostgreSQL 16 · Redis 8 · Celery · uv · Docker Compose

## Development setup

You need Docker with Compose and `make`. [uv](https://github.com/astral-sh/uv) on the host is optional: `make audit` and your editor use it.

1. Clone the repository and create your `.env` (its comments explain every variable; set `SECRET_KEY`):

   ```bash
   git clone https://github.com/Joeriksson/django-forums-app.git
   cd django-forums-app
   cp .env.example .env
   ```

2. Build and start the containers, then set up the database and an admin account:

   ```bash
   make dev_build
   make dev_web_exec cmd='python manage.py migrate'
   make dev_web_exec cmd='python manage.py createsuperuser'
   ```

3. Open http://127.0.0.1:8000 and sign in. The first login asks you to confirm your email address: development prints mail to the console, so find the link with `make dev_logs`. The admin is at `/nimda/` by default; pick your own path with `ADMIN_URL` in `.env` (recommended, at least in production).

Development differs from production: signup is open, staff don't need two-factor authentication, and the API is on. To try the site with signup closed, set `DJANGO_SIGNUP_OPEN=false` in `.env` and restart with `make dev_down` and `make dev`.

GitHub login is optional: add a *Social application* for GitHub in the admin.

The containers write files (such as migrations) into the repository as uid 1000. If your user has another uid, add `user:` to the services in `docker-compose-dev.yml`.

## Everyday commands

| Command | What it does |
|---|---|
| `make dev` / `make dev_down` | Start / stop the containers |
| `make dev_logs` | Show the logs (and mail sent in development) |
| `make dev_web_exec cmd='...'` | Run a command in the web container |
| `make dev_pytest` | Run the tests |
| `make audit` | Check the locked dependencies for known vulnerabilities |

## Tests

`make dev_pytest` runs the suite in parallel with pytest. CI runs it on every push and pull request, together with the audit and a check of the production image.

## Dependencies

Dependencies are managed with uv: `pyproject.toml` lists them and `uv.lock` pins the full tree.

```bash
uv add <package>        # Add a runtime dependency
uv add --dev <package>  # Add a development dependency
uv remove <package>     # Remove a dependency
uv sync                 # Install everything from uv.lock
```

Some front-end files are copies from other projects and not covered by `make audit`; `CLAUDE.md` lists them with their versions.

## Deployment

Production runs `docker-compose-prod.yml` on a VPS behind a reverse proxy (Caddy) that handles HTTPS. See [docs/deployment-vps.md](docs/deployment-vps.md) for the proxy, the `.env` checklist, the first deploy, updates, backups and troubleshooting.

## Licence

MIT, see [LICENSE](LICENSE).
