# Deploying on a VPS with Docker

This guide runs the production stack from `docker-compose-prod.yml` on a VPS, behind a reverse proxy container that terminates HTTPS. The examples use Caddy and `forum.example.com`; replace the domain with your own.

```
Internet ──HTTPS──> Caddy (container, ports 80/443)
                      │
                      │ forum_proxy network, HTTP
                      ▼
                    web (gunicorn, alias forum-web)
                      │ default network
                      ├──> db (Postgres)
                      └──> redis <── celery, celery-beat
```

The stack publishes no ports. The proxy is the only container with public ports, and it reaches `web` over the shared `forum_proxy` network by the name `forum-web`. Only `web` is on that network, so the proxy can't reach Postgres or Redis. The other services talk to each other on the stack's own default network.

## 1. Reverse proxy (Caddy)

`docker-compose-prod.yml` creates the `forum_proxy` network. Caddy runs in its own compose stack, outside this repo. In that stack's compose file, declare `forum_proxy` as external and add it to the Caddy service's networks:

```yaml
# Caddy's own compose file (not docker-compose-prod.yml)
services:
  caddy:
    # ...
    networks:
      - forum_proxy
networks:
  forum_proxy:
    external: true
```

Add a site block to the Caddyfile:

```caddyfile
forum.example.com {
	reverse_proxy forum-web:8000
}
```

Use `forum-web`, not `web`: if the proxy is on other apps' networks as well, `web` may be the name of a service there too.

That is all the app needs:

- **HTTPS and HTTP→HTTPS redirects:** Caddy handles both automatically for the domain.
- **`X-Forwarded-Proto`:** Caddy sends it by default. Django relies on it (`SECURE_PROXY_SSL_HEADER`) to know the request was HTTPS. Without it, `SECURE_SSL_REDIRECT` causes a redirect loop.
- **`Host` header:** Caddy passes the original host through by default. It must match `DJANGO_ALLOWED_HOSTS`.
- **HSTS:** Django sends the `Strict-Transport-Security` header. Don't add one in Caddy as well.
- **Static files:** served by the app through WhiteNoise, so no extra Caddy rules are needed.

To also serve `www.forum.example.com`, add it to the site address (`forum.example.com, www.forum.example.com {`) and to `DJANGO_ALLOWED_HOSTS`.

## 2. `.env` checklist

Copy `.env.example` to `.env` next to `docker-compose-prod.yml` (`cp .env.example .env`), fill in the production values below, and restrict it with `chmod 600 .env`. Leave out the lines the example says to leave out in production. Docker Compose reads it both for the containers and for the `${...}` values in the compose file.

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

**Optional:**

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_ADMINS` | empty | Email addresses, comma-separated, that get the traceback of every server error (500). Set it: without it you only see errors in the logs |
| `DEFAULT_FROM_EMAIL` | `EMAIL_HOST_USER` | Must be an address the SMTP account may send from |
| `EMAIL_PORT` / `EMAIL_USE_TLS` | `587` / `true` | STARTTLS submission |
| `DJANGO_SECURE_HSTS_SECONDS` | `3600` | See [HSTS](#6-raising-hsts) |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | `false` | See [HSTS](#6-raising-hsts) |
| `ADMIN_URL` | `nimda` | Path of the Django admin |
| `DJANGO_SIGNUP_OPEN` | `false` | `true` lets anyone create an account, by email or GitHub. While it's closed, the signup page says so and the navbar hides its link; existing users can still log in. Create accounts in the admin meanwhile |
| `DJANGO_EMAIL_CONSOLE` | `false` | `true` prints mail to the logs instead of using SMTP. Only for trying the stack out |

**Don't set** `DJANGO_SETTINGS_MODULE`, `ENVIRONMENT`, `DATABASE_URL` or `REDIS_URL`: the compose file sets them, and its values take priority.

## 3. First deployment

```bash
git clone <repo-url> forum && cd forum
cp .env.example .env   # then fill it in as above
docker compose -f docker-compose-prod.yml up -d --build
docker compose -f docker-compose-prod.yml exec web python manage.py migrate
docker compose -f docker-compose-prod.yml exec web python manage.py createsuperuser
```

The first `up` creates the `forum_proxy` network. Start (or restart) the Caddy stack only after that, with its own `docker compose up -d`, since Caddy can't join a network that doesn't exist yet.

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

Use `up`, not `down` followed by `up`. `down` tries to remove `forum_proxy`, which fails with "network has active endpoints" while Caddy is attached. If you do need `down`, stop Caddy first.

Migrations don't run automatically. **Back up the database before migrating** (see below); some migrations change data. For example, `forums.0015` deletes duplicate upvotes and subscriptions, and that can't be undone.

Static files are collected into the image when it's built (`collectstatic` in the `Dockerfile`), and WhiteNoise serves them. `--build` in the commands above picks up changes under `static/` and new package versions; there's nothing to run by hand.

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
| **502 Bad Gateway** from Caddy | `web` isn't running, or Caddy isn't on `forum_proxy` (it was started before the network existed: restart the Caddy stack) |
| `network forum_proxy ... has active endpoints` on `down` | Caddy is still attached; see [Updating](#4-updating) |

Logs: `docker compose -f docker-compose-prod.yml logs -f web celery`

## Testing the stack locally

The stack can be started locally to check that it comes up, but not browsed: the production settings redirect HTTP to HTTPS and use secure cookies, and no port is published. In `.env`, set `DJANGO_ALLOWED_HOSTS=localhost` and `DJANGO_EMAIL_CONSOLE=true`, then:

```bash
docker compose -f docker-compose-prod.yml up -d --build
docker compose -f docker-compose-prod.yml ps                  # all five services running
docker compose -f docker-compose-prod.yml exec web python manage.py migrate
docker compose -f docker-compose-prod.yml exec web python manage.py check --deploy
docker compose -f docker-compose-prod.yml exec web python manage.py sendtestemail you@example.com  # mail shows in the logs
docker compose -f docker-compose-prod.yml logs celery celery-beat
```

To fetch a page from inside the container, send the headers the proxy would add:

```bash
docker compose -f docker-compose-prod.yml exec web python -c "import urllib.request as u; r = u.urlopen(u.Request('http://localhost:8000/', headers={'Host': 'localhost', 'X-Forwarded-Proto': 'https'})); print(r.status)"
```

`docker compose -f docker-compose-prod.yml down -v` removes everything again, including the local database volume.
