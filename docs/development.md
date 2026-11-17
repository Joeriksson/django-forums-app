# Development

## With Docker

You need Docker with Compose and `make`. [uv](https://docs.astral.sh/uv/) on the host is optional: `make audit`, the translations and this documentation use it, and so does your editor.

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

3. Open <http://127.0.0.1:8000> and sign in. The first login asks you to confirm your email address: development prints mail to the console, so find the link with `make dev_logs`. The admin is at `/nimda/` by default.

| Command | What it does |
|---|---|
| `make dev_build` / `make dev` | Build and start the containers / start them |
| `make dev_down` | Stop them |
| `make dev_logs` | Show the logs, and the mail sent in development |
| `make dev_web_exec cmd='...'` | Run a command in the web container |
| `make dev_redis_exec cmd='redis-cli'` | Open the Redis CLI |
| `make dev_export_data` | Export the database as a JSON fixture |
| `make dev_pytest` | Run the tests |
| `make audit` | Check the locked dependencies for known vulnerabilities (on the host) |
| `make docs` | Preview this documentation at <http://localhost:8001> (on the host) |

The containers write files such as migrations into the repository as uid 1000. If your user has another uid, add `user:` to the services in `docker-compose-dev.yml`.

## Without Docker

You need PostgreSQL and Redis running yourself. In `.env`, set `DATABASE_URL` and `REDIS_LOCALHOST=true`, then:

```bash
uv sync
uv run python manage.py migrate --settings=project.settings.development
uv run python manage.py createsuperuser --settings=project.settings.development
uv run python manage.py runserver --settings=project.settings.development
```

Set `DJANGO_SETTINGS_MODULE=project.settings.development` in `.env`, or pass `--settings` as above. Without it, `manage.py` uses settings with no email backend, and `createsuperuser` fails when it sends the welcome mail.

## How development differs from production

- Signup is open, staff don't need two-factor authentication, and the API is on. To try the site with signup closed, set `DJANGO_SIGNUP_OPEN=false` in `.env` and restart with `make dev_down` and `make dev`.
- Celery tasks run inside the web process, so mail goes out at once, without its usual delay.
- Mail is printed to the console instead of being sent.

## Tests

`make dev_pytest` runs the suite in parallel with pytest, with the settings in `project.settings.test`. All tests are under `tests/`. CI runs them on every push and pull request, together with the audit and a check of the production image.

The tests don't run a browser. After changing styles or scripts, look at the pages in light and dark, at phone width, and check the browser console for Content Security Policy violations.

## Translations

Every text a member sees goes through gettext, and the Swedish catalog is committed in `locale/sv/LC_MESSAGES/`, both `django.po` and the compiled `django.mo`. After adding or changing a text:

```bash
make messages           # collect the texts into django.po
# write the Swedish
make compile_messages   # compile django.mo; commit both files
```

Both run on the host and need gettext there. A test fails when a text is missing from the catalog or the compiled file is out of date.

## Dependencies

`pyproject.toml` lists the dependencies and `uv.lock` pins the full tree.

```bash
uv add <package>        # add a runtime dependency
uv add --dev <package>  # add a development dependency
uv remove <package>     # remove a dependency
uv sync                 # install everything from uv.lock
```

Some front-end files are copies from other projects and not covered by `make audit`. `CLAUDE.md` lists them with their versions.

## Publishing this documentation

The source is in `docs/`. `deploy/docs.sh` builds it and copies it to `DOCS_TARGET`, set in `.env`, with rsync. Everything in `docs/` gets published, so the script refuses to run while a file there isn't in `nav` in `zensical.toml`. Keep private notes out of `docs/`.
