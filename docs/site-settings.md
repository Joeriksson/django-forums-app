# Site settings

The site's name, the visitors' texts and a few list sizes are set in the Django admin, under *Site settings* (`/<ADMIN_URL>/`, default `/nimda/`). There is one form; *Save* applies it at once, with no restart. A new database starts with the defaults below (created by `migrate`).

| Setting | Default | Used for |
|---|---|---|
| Title | `Wildvasa` | The site's name: the header, the browser tab, the visitors' home page, emails and authenticator apps |
| Tagline | `A private forum. Sign in to read and write.` | Under the name on the visitors' home page |
| Invitation note | `Membership is by invitation. …` | On the visitors' home page while signup is closed |
| Recent threads | 3 (1–10) | Threads under *Recent activity*, above the forum list |
| Latest threads | 15 (5–50) | Threads on the *Latest* page |
| Threads per page | 20 (5–100) | Threads per page of a forum |
| Posts per page | 25 (5–100) | Posts per page of a thread |

Good to know:

- The texts are plain text: HTML or Markdown shows as typed.
- Set the name here, not under *Sites*: saving copies it into the *Sites* display name. *Sites* is only for the domain.
- People who set up two-factor authentication before a rename keep the old name in their authenticator app. It still works.
- Changing a page size moves posts and threads to other pages, so older links to `?page=N` (also those to a single post) may open a page without what they pointed to.

Security limits (posting, search, login) and anything needed at start-up are not here: they are in the settings files and `.env`, so changing them takes a deploy.
