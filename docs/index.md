# Wildvasa

A private discussion forum. Members read and write in forums, threads and replies, and new members join by invitation, or by signing up while signup is open.

**Stack:** Python 3.12, Django 5.2, PostgreSQL 16, Redis 8, Celery, managed with [uv](https://docs.astral.sh/uv/). It is self-hosted with Docker behind a reverse proxy.

## Features

- Forums and threads with Markdown text, an editor with a preview, code highlighting, upvotes and announcements kept at the top of a forum.
- Full-text search with `"exact phrases"` and `-excluded` words, filters for forum, author and date, and the matched words marked in the results.
- Direct messages between two members, with blocking and a way to report a message to the moderators.
- A notification center: a bell and an envelope in the header count what's new, and subscribed threads and messages also send an email. Several replies in a row give one mail, and none if the member has already been there.
- Accounts via django-allauth: email and password or GitHub, confirmed addresses, and optional two-factor authentication (required for staff and moderators). Other members see a profile name, never the username or the address.
- Moderation: a Moderators group, forums that can be closed to members' posts, and a security log.
- English and Swedish, chosen in the header. Light and dark palettes.
- Hand-written CSS, self-hosted fonts, a strict Content Security Policy and nothing loaded from a CDN.
- An optional REST API, off by default.

## Where to go next

- [Development](development.md): run the stack locally, tests and translations.
- [Managing the forum](managing.md): forums, members, moderators and site settings.
- [Configuration](configuration.md): every environment variable.
- [Deploying](deployment-vps.md): the production stack on one server, updates, backups and logs.
- [How it works](architecture.md): the code, notifications, search and security.
