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
                      └──> redis <── celery
```

The stack publishes no ports. The proxy is the only container with public ports, and it reaches `web` over the shared `forum_proxy` network by the name `forum-web`. Only `web` is on that network, so the proxy can't reach Postgres or Redis. The other services talk to each other on the stack's own default network.

No container runs its service as root: `web` and `celery` run as an unprivileged user that can't change the code or the installed packages, and Redis and Postgres run as their own users. There is no `celery-beat` container, since nothing is scheduled; add one back to `docker-compose-prod.yml` with the first scheduled task, with its schedule file outside `/code` (`-s /tmp/celerybeat-schedule`).

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
- **`X-Forwarded-For`:** Caddy sends the visitor's address in it by default, and drops any value the visitor sent. The login rate limits (failed logins, signups, password resets) count per address from its last entry (`ALLAUTH_TRUSTED_PROXY_COUNT = 1` in `production.py`). This assumes exactly one proxy in front of the app: with a second one before Caddy (a CDN, say), raise the count to 2, or the limits count every visitor as that proxy.
- **`Host` header:** Caddy passes the original host through by default. It must match `DJANGO_ALLOWED_HOSTS`.
- **HSTS:** Django sends the `Strict-Transport-Security` header. Don't add one in Caddy as well.
- **Static files:** served by the app through WhiteNoise, so no extra Caddy rules are needed.

To also serve `www.forum.example.com`, add it to the site address (`forum.example.com, www.forum.example.com {`) and to `DJANGO_ALLOWED_HOSTS`.

## 2. `.env` checklist

Copy `.env.example` to `.env` next to `docker-compose-prod.yml` (`cp .env.example .env`), fill in the production values below, and restrict it with `chmod 600 .env`. Leave out the lines the example says to leave out in production. Docker Compose reads it both for the containers and for the `${...}` values in the compose file.

**Required:**

| Variable | Value |
|---|---|
| `SECRET_KEY` | A long random string, e.g. from `python -c "import secrets; print(secrets.token_urlsafe(50))"`. At least 50 characters, or the containers refuse to start. Changing it later logs everyone out |
| `DJANGO_MFA_ENCRYPTION_KEY` | The key that encrypts two-factor secrets in the database, from `python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`. The containers refuse to start without a valid one. **Keep a copy outside the server and never change it**, see [Two-factor authentication](#8-two-factor-authentication-for-staff-and-moderators) |
| `DJANGO_ALLOWED_HOSTS` | Your domain(s), comma-separated: `forum.example.com` |
| `DJANGO_SITE_URL` | The site's public address, with `https` and without a path: `https://forum.example.com`. Notification and invitation emails build their links from it. The app won't start without it |
| `POSTGRES_PASSWORD` | Password of the database superuser `postgres`, used for maintenance on the server only. The app doesn't use it |
| `POSTGRES_APP_PASSWORD` | Password of the app's own database role, `forum`; use a different one. URL-safe characters (letters, digits, `-`, `_`), because it is put into `DATABASE_URL` as is |
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
| `WEB_CONCURRENCY` | `2` | Number of gunicorn worker processes; each handles 4 requests at a time (`gunicorn.conf.py`). Raise it on a server with more CPU cores and memory: each worker is a copy of the app in memory |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` | `false` | See [HSTS](#6-raising-hsts) |
| `ADMIN_URL` | `nimda` | Path of the Django admin |
| `DJANGO_SIGNUP_OPEN` | `false` | `true` lets anyone create an account, by email or GitHub. While it's closed, the signup page says so and the navbar hides its link; existing users can still log in. Create accounts in the admin meanwhile |
| `DJANGO_STAFF_REQUIRE_MFA` | `true` | Staff and moderators need two-factor authentication to use the site. Leave it on; see [Two-factor authentication for staff and moderators](#8-two-factor-authentication-for-staff-and-moderators) |
| `DJANGO_API_ENABLED` | `false` | `true` switches the REST API under `/api/` on. The website doesn't use it; leave it off unless something of yours calls the API. While it's off, every `/api/` path answers 404 |
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

1. **Check email:** `docker compose -f docker-compose-prod.yml exec web python manage.py sendtestemail you@example.com`
2. **Confirm the superuser's address.** Nobody logs in before confirming their email address, and `createsuperuser` doesn't confirm it. Log in at `https://forum.example.com/accounts/login/`: instead of logging you in, the site mails a confirmation link. Open it, confirm, and log in again. This is why email has to work first; see [Troubleshooting](#troubleshooting) if the mail doesn't arrive. Then set up two-factor authentication, see [section 8](#8-two-factor-authentication-for-staff-and-moderators).
3. **Set the site name.** Log in to `https://forum.example.com/<ADMIN_URL>/`, open *Sites*, and change `example.com` to `forum.example.com`. The login emails (password reset, address confirmation) use the site's name. Links in notification and invitation emails use `DJANGO_SITE_URL` instead.
4. **Optional, GitHub login:** add a *Social application* for GitHub in the admin. Without one, the login page simply doesn't show the GitHub button.

## 4. Updating

```bash
git pull
docker compose -f docker-compose-prod.yml up -d --build --remove-orphans
docker compose -f docker-compose-prod.yml exec web python manage.py migrate
```

`--remove-orphans` removes the container of a service that is no longer in the compose file. Use `up`, not `down` followed by `up`. `down` tries to remove `forum_proxy`, which fails with "network has active endpoints" while Caddy is attached. If you do need `down`, stop Caddy first.

Migrations don't run automatically. **Back up the database before migrating** (see below); some migrations change data. For example, `forums.0015` deletes duplicate upvotes and subscriptions, and that can't be undone.

Static files are collected into the image when it's built (`collectstatic` in the `Dockerfile`), and WhiteNoise serves them. `--build` in the commands above picks up changes under `static/` and new package versions; there's nothing to run by hand.

## 5. Backups

A database dump holds every member's email address and password hash, the invitation keys and any API tokens. Encrypt it as it is made, so it never exists as a readable file, and keep it somewhere other than the server.

The commands below use [`age`](https://age-encryption.org), a small file encryption tool, with a key pair: the server only has the public key, so backups can be made there (also from a scheduled job) but not read there.

**Once, on your own computer** (not on the server):

```bash
# On your own computer, not on the server
age-keygen -o forum-backup-key.txt     # prints the public key: age1...
```

`age` is in the usual package managers (`apt install age`, `brew install age`). `forum-backup-key.txt` is the private key: it never goes to the server or into this repository. Keep a second copy of it somewhere safe (a password manager, say). Without it the backups can't be read by anyone, you included. The public key, the line starting with `age1`, is not secret.

**Back up**, on the server (install `age` there too), with your public key in place of `age1...`:

```bash
docker compose -f docker-compose-prod.yml exec -T db pg_dump -U forum forum \
  | age -r age1... > backup-$(date +%F).sql.age
```

Then copy the file off the server; a backup that only exists on the server is lost with it.

**Restore** into an empty database. Decrypt on your own computer, where the private key is, and send the result straight to the server, so the readable dump is never stored:

```bash
# On your own computer
age -d -i forum-backup-key.txt backup-YYYY-MM-DD.sql.age \
  | ssh user@server 'cd forum && docker compose -f docker-compose-prod.yml exec -T db psql -U forum forum'
```

**What else to keep with the backups:** a copy of the server's `.env`, stored as carefully as the private key. A restored database needs the same `DJANGO_MFA_ENCRYPTION_KEY`, or no stored second factor works (see [section 8](#8-two-factor-authentication-for-staff-and-moderators)); the same `SECRET_KEY` keeps sessions and pending password reset links valid.

Try a restore once before you depend on the backups, for example into the stack [started locally](#testing-the-stack-locally).

The forum's data is in the database `forum`, owned by the role `forum`, which is all the app can touch: it is not a superuser and can't create roles or databases. `docker/postgres/create-app-role.sh` creates both when the `postgres_data` volume is first created. The superuser `postgres` is for maintenance: `docker compose -f docker-compose-prod.yml exec db psql -U postgres`.

Both passwords are only applied when the volume is first created. Changing one later requires changing it inside Postgres as well (`ALTER ROLE forum PASSWORD '...'` as `postgres`).

## 6. Raising HSTS

HSTS starts at one hour, so a mistake only locks browsers into HTTPS briefly. Once the site has run on HTTPS without problems:

1. Set `DJANGO_SECURE_HSTS_SECONDS=31536000` (one year).
2. Only if **every** subdomain of the domain is served over HTTPS: set `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true`.
3. Only if you want to submit the domain to browsers' preload list (hard to undo): also set `DJANGO_SECURE_HSTS_PRELOAD=true`, then submit at hstspreload.org.

Restart with `docker compose -f docker-compose-prod.yml up -d` after changing `.env`.

## 7. Inviting people

Signup is closed unless `DJANGO_SIGNUP_OPEN=true`. While it's closed, people join by invitation:

1. Check `DJANGO_SITE_URL` in `.env`; the link in the email is built from it.
2. In the admin, open *Invitations → Add*, enter the person's email address and save. The app emails them a link. Addresses that already have an account or a pending invitation are refused.
3. The person opens the link and signs up, with that address and a password, or with a GitHub account that has that address verified. The link works once and for 7 days.

The list shows each invitation as *Pending*, *Used* or *Expired*, and when its email was sent. To send a new link (expired, lost, or never arrived), select the invitation and run *Resend invitation*: the old link stops working and the 7 days start again. The link is also on the invitation's own page, if you'd rather send it yourself.

Inviting needs the `users.add_invitation` permission. Superusers have it.

## 8. Two-factor authentication for staff and moderators

Everyone who can do more than a member needs an authenticator app, such as any TOTP app on a phone: staff, superusers, members of the Moderators group, and anyone given a permission in the admin. Without one they are sent to the setup page from every other page, so they can't moderate or reach the admin until it's done. Other users can turn two-factor authentication on if they like.

**First login.** After `createsuperuser`, log in on the site (the admin uses the site's login page) and confirm the email address with the link the site mails you. At the next login you are sent to *Two-factor authentication* straight away: activate the authenticator app by scanning the QR code and entering a code. Then store the recovery codes somewhere safe, away from the phone. From then on every login, with a password or GitHub, asks for a code.

**New staff members and moderators** set up the authenticator app first, as an ordinary member (*Two-factor authentication* in the user menu), and get their rights after that. The admin refuses to give staff status, a group or a permission to an account without one: otherwise anyone with that account's password could set up their own app and use the rights. The *Two-factor* column in the admin's user list shows who has one. Every account has confirmed its email address by then, since nobody logs in without it, so two-factor setup is never refused for that reason.

The first superuser is the exception, since `createsuperuser` doesn't go through the admin: set its authenticator app up right after creating it.

**What staff and moderators can't do:** use API tokens. A token would skip the code, so the API refuses tokens of these accounts. They use the API in the browser, logged in on the site. This only matters with `DJANGO_API_ENABLED=true`: by default there is no API.

**API tokens are passwords.** A token gives its user's access to the API for as long as it exists: it never expires, and it is stored readable in the database. Create one (in the admin, under *Auth Token → Tokens*) only for something that needs it, and delete it there when it is no longer used or may have been seen by someone else. While the API is off, tokens can't be used at all.

**The encryption key.** The authenticator apps' secrets and the recovery codes are stored encrypted with `DJANGO_MFA_ENCRYPTION_KEY`, so a copy of the database alone doesn't give anyone a second factor. The other side of that: with a different key, or without it, nobody's code or recovery code is accepted, and logins of users with two-factor authentication fail with an error. Keep a copy of the key where you keep your backups' key, not only in `.env` on the server. A restored database backup needs the key it was made with. If the key is lost for good, generate a new one and run `remove_mfa` (below) for each account that had two-factor authentication.

**Lost phone.** Use a recovery code instead of the app's code at login; each works once. Without recovery codes, remove the account's two-factor authentication on the server:

```bash
docker compose -f docker-compose-prod.yml exec web python manage.py remove_mfa you@example.com
```

The account then logs in with the password alone and has to set two-factor authentication up again before using the site. Setting `DJANGO_STAFF_REQUIRE_MFA=false` does not help here: the login still asks for the code of an account that has an authenticator app.

## 9. Logs and the security log

The containers log to the host's systemd journal (`logging` in `docker-compose-prod.yml`), so the logs survive updates, which recreate the containers. Each container's lines are tagged with its name, e.g. `forum-web-1` if the repo was cloned into `forum`; `docker ps --format '{{.Names}}'` lists the names.

```bash
docker compose -f docker-compose-prod.yml logs -f web celery      # as before
journalctl -t forum-web-1 --since "2 days ago"              # one container, by time
journalctl -t forum-web-1 --since today | grep ' security ' # the security log
```

Lines from the `security` logger record who did what, and from which address:

| Line starts with | Meaning |
|---|---|
| `login`, `logout`, `signup` | A user logged in (after the two-factor code, if any), logged out, or signed up |
| `login_failed` | Wrong address or password, with the address that was typed |
| `mfa_failed` | Wrong two-factor code |
| `password_set`, `password_changed`, `password_reset`, `email_changed` | Account changes |
| `mfa_added`, `mfa_removed`, `mfa_reset`, `mfa_removed_by_command` | Two-factor changes (`mfa_reset`: new recovery codes) |
| `moderation` | A thread or post was edited or deleted by someone other than its author (`owner`) |
| `denied` | A request was refused (`status=401` or `403`) or rate limited (`429`) |
| `invitation_created`, `invitation_resent`, `invitation_used`, `invitation_refused` | Invitations; `refused` is an unknown, expired or used link |

`user`, `owner` and `invitation` are ids: look them up in the admin. Changes made in the admin itself are in its own *History*, not here.

**Set how long the journal is kept.** It holds the logs of the whole server, and the lines contain IP addresses, so decide on a period. Once, on the server:

```ini
# /etc/systemd/journald.conf on the server (not a file in this repo)
[Journal]
SystemMaxUse=1G
MaxRetentionSec=3month
```

```bash
sudo systemctl restart systemd-journald
```

After the first deployment with this setup, check that lines arrive: `journalctl -t forum-web-1 -n 20`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Containers exit with `ImproperlyConfigured: Set SECRET_KEY` | `SECRET_KEY` is missing, shorter than 50 characters or not random enough |
| Containers exit with `ImproperlyConfigured: Set DJANGO_MFA_ENCRYPTION_KEY` | The key is missing or isn't 32 bytes in base64; generate one with the command in the [`.env` checklist](#2-env-checklist) |
| Login fails with a 500 right after the two-factor code, `InvalidToken` in `logs web` | `DJANGO_MFA_ENCRYPTION_KEY` is not the key the secrets were encrypted with. Put the original key back |
| Containers exit with `ImproperlyConfigured: Missing SMTP settings` | One of `EMAIL_HOST`, `EMAIL_HOST_USER` or `EMAIL_HOST_PASSWORD` is missing |
| `docker compose` says `required variable ... is missing a value` | `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD` or `REDIS_PASSWORD` isn't set in `.env` |
| `web` logs `password authentication failed for user "forum"` or `role "forum" does not exist` | The `postgres_data` volume was created before the role existed, or with another password: the init script only runs on an empty volume. Create the role and database by hand as `postgres` (the statements are in `docker/postgres/create-app-role.sh`), or, with no data to keep, remove the volume and start again |
| Every page returns **400 Bad Request** | The domain isn't in `DJANGO_ALLOWED_HOSTS` |
| Forms fail with **CSRF verification failed** | Same: `CSRF_TRUSTED_ORIGINS` is built from `DJANGO_ALLOWED_HOSTS` |
| Endless redirect loop | The proxy doesn't send `X-Forwarded-Proto: https` |
| Login answers that a confirmation email was sent, but none arrives | The account's address isn't confirmed yet and the mail failed: check `logs web` and the SMTP settings, then log in again for a new mail. As a last resort set `DJANGO_EMAIL_CONSOLE=true`, restart, log in and take the link from `logs web`; then set it back |
| A user created in the admin can't log in | Same: their first login mails them a confirmation link. Invited users don't need one |
| Invitation has no *Sent* time | The email failed (it's retried 3 times): check `logs celery` and the SMTP settings, then use *Resend invitation* |
| Links in notification emails point to the wrong address | `DJANGO_SITE_URL` in `.env` is wrong; fix it and restart |
| Invitation links point to the wrong address | `DJANGO_SITE_URL` is wrong; fix it, restart, and use *Resend invitation* |
| Containers exit with `ImproperlyConfigured: Set DJANGO_SITE_URL` | It's missing, or isn't an `https` address without a path |
| **502 Bad Gateway** from Caddy | `web` isn't running, or Caddy isn't on `forum_proxy` (it was started before the network existed: restart the Caddy stack) |
| Containers fail to start with `failed to initialize logging driver` | The host has no systemd journal: remove the `logging` lines from `docker-compose-prod.yml` |
| `network forum_proxy ... has active endpoints` on `down` | Caddy is still attached; see [Updating](#4-updating) |

Logs: `docker compose -f docker-compose-prod.yml logs -f web celery` (see [Logs and the security log](#9-logs-and-the-security-log))

## Testing the stack locally

The stack can be started locally to check that it comes up, but not browsed: the production settings redirect HTTP to HTTPS and use secure cookies, and no port is published. In `.env`, set `DJANGO_ALLOWED_HOSTS=localhost`, `DJANGO_SITE_URL=https://localhost` and `DJANGO_EMAIL_CONSOLE=true`, then:

```bash
docker compose -f docker-compose-prod.yml up -d --build
docker compose -f docker-compose-prod.yml ps                  # all four services running
docker compose -f docker-compose-prod.yml exec web python manage.py migrate
docker compose -f docker-compose-prod.yml exec web python manage.py check --deploy
docker compose -f docker-compose-prod.yml exec web python manage.py sendtestemail you@example.com  # mail shows in the logs
docker compose -f docker-compose-prod.yml logs celery
```

To fetch a page from inside the container, send the headers the proxy would add:

```bash
docker compose -f docker-compose-prod.yml exec web python -c "import urllib.request as u; r = u.urlopen(u.Request('http://localhost:8000/', headers={'Host': 'localhost', 'X-Forwarded-Proto': 'https'})); print(r.status)"
```

`docker compose -f docker-compose-prod.yml down -v` removes everything again, including the local database volume.
