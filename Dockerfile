# Pull base image
FROM python:3.10.5-slim

# Set env vars
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working dir
WORKDIR /code

# Install dependencies
# COPY Pipfile Pipfile.lock /code/
RUN python -m pip install --upgrade pip

# RUN pip install pipenv && pipenv install --system
COPY requirements.txt /code/
RUN python -m pip install -r requirements.txt

# Copy project
COPY . /code/


# Command for container to not shut down in GitHub Action
CMD tail -f /dev/null

