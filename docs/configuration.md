# Configuration

All settings come from environment variables. Put them in `.env` next to the compose files; `.env.example` lists every one with comments. `DEBUG` is not read from the environment: each settings module sets it. See [Deploying](deployment-vps.md#2-env-checklist) for what a first deploy needs.

Settings that can change without a restart are in the admin: see [Site settings](managing.md#site-settings).

## Core

| Variable | Default | What it does |
|---|---|---|
| `SECRET_KEY` | | Django's secret key. Production refuses to start with fewer than 50 characters, fewer than 5 different ones, or a `django-insecure-` key |
| `DJANGO_MFA_ENCRYPTION_KEY` | derived from `SECRET_KEY` outside production | Encrypts two-factor secrets in the database. Required in production. Changing it makes the stored second factors unreadable |
| `ENVIRONMENT` | | `development`, `production`, `CI` or `test`. The production compose file sets it |
| `DJANGO_SETTINGS_MODULE` | | `project.settings.development` for development. Without it `manage.py` uses `base` and Celery uses `production`. The production compose file sets it |
| `REDIS_URL` | `redis://redis:6379/0` | The database number is replaced: the cache uses `/0`, Celery `/1`. The production compose file sets it |
| `REDIS_LOCALHOST` | | `true` for Redis on localhost, when running without Docker |
| `DATABASE_URL` | | Overrides the database settings, e.g. to run without Docker. The production compose file sets it |
| `WEB_CONCURRENCY` | `2` | Production: gunicorn worker processes, each handling 4 requests at a time |

## The site

| Variable | Default | What it does |
|---|---|---|
| `DJANGO_SITE_URL` | `http://127.0.0.1:8000` | The public address, for links in emails. Required in production: `https`, no path |
| `DJANGO_ALLOWED_HOSTS` | | Production: comma-separated hosts, also used for `CSRF_TRUSTED_ORIGINS`. If empty, every request gets a 400 |
| `ADMIN_URL` | `nimda` | The admin's path |
| `DJANGO_TIME_ZONE` | `UTC` | The zone dates and times are shown in, for every member: a name such as `Europe/Paris`. Logs stay in UTC |
| `DJANGO_LANGUAGE` | `en` | The language of the pages until a visitor picks another, and of the mails: `en` or `sv` |
| `DJANGO_SIGNUP_OPEN` | `false` (development: `true`) | Lets anyone sign up, by email or GitHub. While closed, only an invitation opens signup |
| `DJANGO_API_ENABLED` | `false` (development: `true`) | Mounts the REST API under `/api/`. While off, every `/api/` path is a 404 |

## Security

| Variable | Default | What it does |
|---|---|---|
| `DJANGO_STAFF_REQUIRE_MFA` | `true` (development: `false`) | Anyone with a permission needs an authenticator app to use the site, and their API tokens are refused |
| `DJANGO_CSP_REPORT_ONLY` | `false` | `true` makes the Content Security Policy only report, in the browser console, instead of blocking |
| `DJANGO_SECURE_HSTS_SECONDS` | `3600` | Production: HSTS max-age. See [Raising HSTS](deployment-vps.md#6-raising-hsts) |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `false` | Opt-in HSTS flag |
| `DJANGO_SECURE_HSTS_PRELOAD` | `false` | Opt-in HSTS flag |

## Email

| Variable | Default | What it does |
|---|---|---|
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | | SMTP server and login. Production refuses to start without them, unless `DJANGO_EMAIL_CONSOLE=true` |
| `EMAIL_PORT` | `587` | |
| `EMAIL_USE_TLS` | `true` | STARTTLS |
| `DEFAULT_FROM_EMAIL` | `EMAIL_HOST_USER` | The sender address |
| `DJANGO_EMAIL_CONSOLE` | `false` | Production: print mail to the logs instead, for trying the stack out locally |
| `DJANGO_ADMINS` | | Comma-separated addresses that get the traceback of every server error. Empty means no error mails |

## The production compose file

| Variable | What it does |
|---|---|
| `POSTGRES_PASSWORD` | Required. The Postgres superuser's password, for maintenance; the app doesn't use it |
| `POSTGRES_APP_PASSWORD` | Required. The password of the app's database role, `forum`. URL-safe characters only |
| `REDIS_PASSWORD` | Required. URL-safe characters only |

## On your own machine

| Variable | What it does |
|---|---|
| `DOCS_TARGET` | For `deploy/docs.sh`: where this documentation is copied, `user@host:/path/forums/`. The folder must be the site's own: rsync deletes everything else in it |
