![django test workflow](https://github.com/joeriksson/django-forums-app/actions/workflows/django.yml/badge.svg)

# Django Forums

A sample forums app built on the Django framework. I built this app to learn Django more, and I wanted to learn how to do a parent/child database model to also learn that aspect of Django. It can also be seen as an example app to see how the features listed below could be implemented in Django.

Includes:

- forums, threads and posts (reply in threads)
- subscribe to threads and get email notifications
- custom user model (email instead of username)
- optionally login via github account
- user profile in a separate model from user
- e-mail verification
- django debug toolbar (only in development)
- docker files for spinning up containers (python and postgresql)
- basic tests for pages, users and forums
- different settings files for development and production
- basic Bootstrap styling
- api via Django REST Framework
- caching with Redis
- e-mail task queue with Celery

## Tech stack

- **Python** 3.12
- **Django** 4.2 (LTS)
- **PostgreSQL** 16
- **Redis** (caching and Celery broker)
- **Celery** (async task queue)
- **uv** (dependency management)
- **Docker** / **Docker Compose** (containerised development and production)

## Production and development settings

The settings files are split into production and development. The project also has one `docker-compose-dev.yml` for development and one `docker-compose-prod.yml` for production. To make it easier and less to type for each command, there is a Makefile with the most common operations.

## Quick start

1. Clone this repository

```
git clone https://github.com/Joeriksson/django-forums-app.git
```

2. Install [Docker Desktop](https://www.docker.com/products/docker-desktop) to be able to use the docker environment.

3. Create a `.env` file in the root folder with the following parameters:

```
ENVIRONMENT=development
SECRET_KEY=<your secret key>
DEBUG=True
ADMIN1=<Name, email@example.com>
ADMIN2=<Name, email@example.com>
SENDGRID_PASSWORD=<your sendgrid password>
SENDGRID_USERNAME=<your sendgrid username>
SENTRY_KEY=<your sentry key>
SENTRY_PROJECT=<your sentry project id>
```

> **Note:** `SENDGRID_PASSWORD`, `SENDGRID_USERNAME`, `SENTRY_KEY`, and `SENTRY_PROJECT` are optional for development. The development settings send email to the console by default, so you can leave those as empty strings or omit them.

4. In the directory where you cloned the repository, build and start the containers:

```
make dev_build
```

5. The containers should now be up and running. Check in your browser that you see a start page at `http://127.0.0.1:8000`

6. Run the database migrations:

```
make dev_web_exec cmd='python manage.py migrate'
```

7. Create a Django superuser to log in to the admin:

```
make dev_web_exec cmd='python manage.py createsuperuser'
```

8. Go to the admin pages (see `urls.py`) and log in with the superuser account you just created.

To stop the containers:

```
make dev_down
```

## Running tests

Two test suites are available. Run them inside the Docker containers:

```bash
make dev_pytest      # pytest (tests/ directory)
make dev_test        # Django test runner (parallel)
```

## Dependency management

Dependencies are managed with [uv](https://github.com/astral-sh/uv). The `pyproject.toml` file defines all direct dependencies and the `uv.lock` file pins the full dependency tree.

To add or update dependencies, edit `pyproject.toml` and run:

```
uv lock
```
