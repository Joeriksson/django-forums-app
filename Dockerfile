# Pull base image
FROM python:3.12-slim

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

# Set env vars
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Place the project venv at /opt/venv (outside /code, so it survives the dev volume mount)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working dir
WORKDIR /code

# Install dependencies into /opt/venv. The default leaves out the dev group (pytest etc.)
# for production; docker-compose-dev.yml passes an empty value to install it.
ARG UV_SYNC_FLAGS=--no-dev
COPY pyproject.toml uv.lock /code/
RUN uv sync --frozen $UV_SYNC_FLAGS

# Copy project
COPY . /code/

# Collect static files into /code/staticfiles, served by WhiteNoise. Settings need a
# SECRET_KEY at import time; the throwaway value exists only for this step.
RUN SECRET_KEY=collectstatic python manage.py collectstatic --noinput --settings=project.settings.base

# Run as an unprivileged user. The code and the venv stay owned by root, so the app
# can't change them. In development the mounted repo usually belongs to uid 1000 on the
# host, so files the containers write there (migrations) get the right owner.
RUN useradd --uid 1000 --create-home app
USER app

# Command for container to not shut down
CMD tail -f /dev/null
