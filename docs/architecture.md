# How it works

## The code

| Package | What's in it |
|---|---|
| `project/` | Settings, the Celery app, URLs, the Content Security Policy and language middleware |
| `forums/` | Forums, threads, replies, upvotes and subscriptions; search (`search.py`), activity lists (`activity.py`), rate limits (`throttling.py`) |
| `conversations/` | Direct messages, blocking and reports |
| `notifications/` | The notification center: one table for every kind of news, the page and the bell |
| `users/` | The custom user model with email login, invitations, the security log, encryption of two-factor secrets |
| `pages/` | The home page and the site settings |
| `api/` | The optional REST API |
| `templates/`, `static/`, `locale/` | Templates, hand-written CSS and scripts, the Swedish catalog |

## The services

gunicorn serves the site, with static files from WhiteNoise. PostgreSQL holds the data. Redis is the cache behind the rate limits and the broker for Celery, whose worker sends the mail. If Redis can't be reached when a mail is queued, the error is logged and the post is still saved, without that mail.

## Notifications and mail

A reply or a direct message first updates the notification center. Each member has one row per thread or conversation, and it is reused: it counts up while unread and starts over at the next news once read, so the table doesn't grow with the posts.

Mail waits a few minutes (`notification_mail_delay`, 5 by default, in [Site settings](managing.md#site-settings)). When the task runs, it mails only those whose unread row starts at this reply or message. So a member who has been there during the wait gets no mail, and one who hasn't gets one mail until they have been there. Mails about messages name the sender and never quote the text.

## Search

Search uses PostgreSQL full-text search with English word forms and GIN indexes, and one query combines threads and replies, sorted and paged. Excerpts mark the matched words after the Markdown is rendered and escaped, so a member's text can't add HTML.

## Security

- **Login:** reading anything needs an account. Email addresses must be confirmed. Staff and moderators must use an authenticator app, and its secrets are encrypted in the database.
- **Rate limits:** posting, messages, search, previews, logins and the API each have limits, per member where they can be.
- **Markdown:** raw HTML in a text shows as text, and a sanitiser keeps only listed tags and URL schemes. Images load only over `https`.
- **Browser:** a Content Security Policy allows scripts, styles and fonts from the site itself only, with no inline code in the templates.
- **Containers:** nothing runs as root, the app can't change its own code, and only `web` is on the reverse proxy's network. The app's database role has no special rights.
- **Security log:** logins, two-factor changes, refused requests, moderation, blocks and reports, with user ids and addresses but never passwords, codes or message texts. See [Logs and the security log](deployment-vps.md#9-logs-and-the-security-log).

## Caching

The forum and thread pages aren't cached: each loads one page in a single query. The cache holds rate-limit counters and stores JSON, not pickle, so write access to Redis doesn't mean running code in the web process.
