![django test workflow](https://github.com/joeriksson/django-forums-app/actions/workflows/django.yml/badge.svg)

# Django Forums App

A private discussion forum built with Django. Members read and write in forums, threads and replies; new members join by invitation, or by signing up while signup is open.

## Features

- **Forums and threads**: Markdown replies with an editor and preview, announcements, upvotes, recent activity, full-text search with filters, email notifications for subscribed threads
- **Members**: sign in with email or GitHub, invitations, confirmed email addresses, optional two-factor authentication (required for staff and moderators), profile names shown instead of usernames
- **Moderation**: a Moderators group that can edit and delete others' threads and posts, forums that can be closed so only moderators start threads or post, and a security log
- **Site**: hand-written CSS with light and dark palettes, self-hosted fonts, a strict Content Security Policy, nothing loaded from a CDN, an optional REST API

## Tech stack

Python 3.12 · Django 5.2 · PostgreSQL 16 · Redis 8 · Celery · uv · Docker Compose

## Documentation

<https://docs.brommaplan.nu/forums/>. The source is in [`docs/`](docs/); preview it with `make docs`.

## Quick start

You need Docker with Compose and `make`.

```bash
git clone https://github.com/Joeriksson/django-forums-app.git
cd django-forums-app
cp .env.example .env    # set SECRET_KEY
make dev_build
make dev_web_exec cmd='python manage.py migrate'
make dev_web_exec cmd='python manage.py createsuperuser'
```

Then open http://127.0.0.1:8000. See [Development](docs/development.md) for the rest and [Deploying](docs/deployment-vps.md) for production.

## Licence

MIT, see [LICENSE](LICENSE).
