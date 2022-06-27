[![CircleCI](https://circleci.com/gh/Joeriksson/django-forums-app/tree/master.svg?style=svg)](https://circleci.com/gh/Joeriksson/django-forums-app/tree/master)
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

## Production and development settings
 
The setting file are split up in production and a development settings files. Also the project have one docker-compose.yml for production and one for development. Within the docker-compose files you can find the parameter for which settings file to use on the runserver command. To make it easier and less to type for each command, there is a Makefile with different common operations.

## Quick start

> Note: I haven't tested setting this up this project as below on Windows or Linux. Only on MacOS.

1. Clone this repository

`https://github.com/Joeriksson/django-forums-app.git`

2. Install [Docker Desktop](https://www.docker.com/products/docker-desktop) to be able to use the docker environment.

3. Create an .env file in the root folder with the the following parameters:

```ENVIRONMENT='development'
SENDGRID_PASSWORD=<you sendgrid password>
SENDGRID_USERNAME=<your sendgrid username>
SECRET_KEY=<your secret key>
DEBUG=True
SENTRY_KEY=<your sentry key>
SENTRY_PROJECT=<your sentry project id>
```
> *Note: you don't need a Sendgrid account when using the development settings. It sends mail to the console by default. You can just put in some random values for those. 
> Also you don't need to use sentry for logging. Just comment out the sentry settings in /settings/base.py.*

3. In the directory where you cloned the repository, run the following command:

`make dev_build`

4. The container should now be up and running. Check in you browser that you see a start web page at `http://127.0.0.1:8080`

5. Run a migration to build the databases

`make dev_web_exec cmd='python manage.py migrate'`

6. Create a Django super user to log in to the admin

`make dev_web_exec cmd='python manage.py createsuperuser'`

7. Goto the admin pages (see urls.py) and login with the super user account you just created.

If you want to stop the container run:

`make dev_down`


