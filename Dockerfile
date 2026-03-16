# Pull base image
FROM python:3.12-slim

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set env vars
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working dir
WORKDIR /code

# Install dependencies (all groups, including dev/test tools)
COPY pyproject.toml uv.lock /code/
RUN uv sync --frozen

# Copy project
COPY . /code/

# Command for container to not shut down
CMD tail -f /dev/null
