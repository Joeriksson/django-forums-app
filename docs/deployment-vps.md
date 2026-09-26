# Deploying on a VPS with Docker

This guide runs the production stack from `docker-compose-prod.yml` on a VPS, behind a reverse proxy on the host that terminates HTTPS. The examples use Caddy and `forum.example.com`; replace the domain with your own.

```
Internet ──HTTPS──> Caddy (host) ──HTTP──> 127.0.0.1:8000 ──> web (gunicorn)
                                                                │
                              db (Postgres) <──┬────────────────┤
                              redis <──────────┴── celery, celery-beat
```

Only `web` is published, and only on `127.0.0.1`, so it can't be reached from outside except through the proxy. Postgres and Redis aren't published at all.

## 1. Reverse proxy (Caddy)

Add a site block to the Caddyfile on the host:

```caddyfile
forum.example.com {
	reverse_proxy 127.0.0.1:8000
}
```

That is all the app needs:

- **HTTPS and HTTP→HTTPS redirects:** Caddy handles both automatically for the domain.
- **`X-Forwarded-Proto`:** Caddy sends it by default. Django relies on it (`SECURE_PROXY_SSL_HEADER`) to know the request was HTTPS. Without it, `SECURE_SSL_REDIRECT` causes a redirect loop.
- **`Host` header:** Caddy passes the original host through by default. It must match `DJANGO_ALLOWED_HOSTS`.
- **HSTS:** Django sends the `Strict-Transport-Security` header. Don't add one in Caddy as well.
- **Static files:** served by the app through WhiteNoise, so no extra Caddy rules are needed.

To also serve `www.forum.example.com`, add it to the site address (`forum.example.com, www.forum.example.com {`) and to `DJANGO_ALLOWED_HOSTS`.

## 2. `.env` checklist

Create `.env` next to `docker-compose-prod.yml` and restrict it with `chmod 600 .env`. Docker Compose reads it both for the containers and for the `${...}` values in the compose file.

**Required:**

| Variable | Value |
|---|---|
| `SECRET_KEY` | A long random string, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | Your domain(s), comma-separated: `forum.example.com` |
| `POSTGRES_PASSWORD` | Database password. Use URL-safe characters (letters, digits, `-`, `_`), because it is put into `DATABASE_URL` as is |
| `REDIS_PASSWORD` | Redis password. Also URL-safe, for the same reason |
| `EMAIL_HOST` | Your SMTP server |
| `EMAIL_HOST_USER` | SMTP login (usually the sending address) |
| `EMAIL_HOST_PASSWORD` | SMTP password or token |
| `ADMIN1`, `ADMIN2` | Admin contacts for error emails, format `Name,email@example.com`. The app won't start without them |

**Optional:**

| Variable | Default | Notes |
|---|---|---|
| `DEFAULT_FROM_EMAIL` | `EMAIL_HOST_USER` | Must be an address the SMTP account may send from |
| `EMAIL_PORT` / `EMAIL_USE_TLS` | `587` / `true` | STARTTLS submission |
| `DJANGO_SECURE_HSTS_SECONDS` | `3600` | See [HSTS](#6-raising-hsts) |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | `false` | See [HSTS](#6-raising-hsts) |
| `ADMIN_URL` | `nimda` | Path of the Django admin |
| `DJANGO_EMAIL_CONSOLE` | `false` | `true` prints mail to the logs instead of using SMTP. Only for trying the stack out |

**Don't set** `DJANGO_SETTINGS_MODULE`, `ENVIRONMENT`, `DATABASE_URL` or `REDIS_URL`: the compose file sets them, and its values take priority.

## 3. First deployment

```bash
git clone <repo-url> forum && cd forum
# create .env as above
docker compose -f docker-compose-prod.yml up -d --build
docker compose -f docker-compose-prod.yml exec web python manage.py migrate
docker compose -f docker-compose-prod.yml exec web python manage.py createsuperuser
```

Then:

1. **Set the site domain.** Log in to `https://forum.example.com/<ADMIN_URL>/`, open *Sites*, and change `example.com` to `forum.example.com`. Notification emails build their thread links from this domain.
2. **Check email:** `docker compose -f docker-compose-prod.yml exec web python manage.py sendtestemail you@example.com`
3. **Optional, GitHub login:** add a *Social application* for GitHub in the admin. Without one, the login page simply doesn't show the GitHub button.

## 4. Updating

```bash
git pull
docker compose -f docker-compose-prod.yml up -d --build
docker compose -f docker-compose-prod.yml exec web python manage.py migrate
```

Migrations don't run automatically. **Back up the database before migrating** (see below); some migrations change data. For example, `forums.0015` deletes duplicate upvotes and subscriptions, and that can't be undone.

Static files come from the `staticfiles/` directory in the repository. After changing anything under `static/`, run `collectstatic` locally and commit the result.

## 5. Backups

```bash
docker compose -f docker-compose-prod.yml exec -T db pg_dump -U postgres postgres > backup-$(date +%F).sql
```

Restore into an empty database with `psql`:

```bash
docker compose -f docker-compose-prod.yml exec -T db psql -U postgres postgres < backup-YYYY-MM-DD.sql
```

`POSTGRES_PASSWORD` is only applied when the `postgres_data` volume is first created. Changing it later requires changing the password inside Postgres as well.

## 6. Raising HSTS

HSTS starts at one hour, so a mistake only locks browsers into HTTPS briefly. Once the site has run on HTTPS without problems:

1. Set `DJANGO_SECURE_HSTS_SECONDS=31536000` (one year).
2. Only if **every** subdomain of the domain is served over HTTPS: set `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true`.
3. Only if you want to submit the domain to browsers' preload list (hard to undo): also set `DJANGO_SECURE_HSTS_PRELOAD=true`, then submit at hstspreload.org.

Restart with `docker compose -f docker-compose-prod.yml up -d` after changing `.env`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Containers exit with `ImproperlyConfigured: Missing SMTP settings` | One of `EMAIL_HOST`, `EMAIL_HOST_USER` or `EMAIL_HOST_PASSWORD` is missing |
| `docker compose` says `required variable ... is missing a value` | `POSTGRES_PASSWORD` or `REDIS_PASSWORD` isn't set in `.env` |
| Every page returns **400 Bad Request** | The domain isn't in `DJANGO_ALLOWED_HOSTS` |
| Forms fail with **CSRF verification failed** | Same: `CSRF_TRUSTED_ORIGINS` is built from `DJANGO_ALLOWED_HOSTS` |
| Endless redirect loop | The proxy doesn't send `X-Forwarded-Proto: https` |
| Links in notification emails point to `example.com` | The *Sites* domain hasn't been set (step 3.1) |

Logs: `docker compose -f docker-compose-prod.yml logs -f web celery`
