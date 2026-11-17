# Managing the forum

Most of this happens in the Django admin, at `/<ADMIN_URL>/` (default `/nimda/`).

## Forums

Add and edit forums on the site, with the `forums.add_forum` and `forums.change_forum` permissions, or in the admin. Each forum says who may post:

| Posting | Who can do what |
|---|---|
| Open | Every member starts threads and replies |
| Moderators start threads | Only moderators start threads; members reply |
| Moderators only | Members only read |

Closing a forum stops new content only: members can still edit and delete their own, upvote and subscribe.

Moderators can mark a thread as an announcement with a checkbox on its form. It then stays at the top of its forum.

## Members and invitations

Signup is closed unless `DJANGO_SIGNUP_OPEN=true`. While it's closed, people join by invitation, sent from the admin: see [Inviting people](deployment-vps.md#7-inviting-people).

## Moderators

Add a member to the *Moderators* group in the admin. They can then edit and delete other members' threads, delete their replies and handle reported messages, but not rewrite a reply: that needs `forums.change_post`, which the group doesn't have.

A moderator needs an authenticator app before getting the rights, and the admin refuses the group without one: see [Two-factor authentication](deployment-vps.md#8-two-factor-authentication-for-staff-and-moderators).

Changes made to someone else's thread or reply are written to the [security log](deployment-vps.md#9-logs-and-the-security-log).

## Reported messages

Direct messages are read only by the two members, and they aren't in the admin. The receiver of a message can report it, which keeps a copy for the moderators. Those with the permission see *Reports* in the user menu, with the number waiting: the copied message, the two members and the reporter's note, and nothing else of the conversation. *Mark as handled* records who and when. Nobody is mailed about a report.

## Site settings

The site's name, the visitors' texts and a few list sizes are set in the Django admin, under *Site settings* (`/<ADMIN_URL>/`, default `/nimda/`). There is one form; *Save* applies it at once, with no restart. A new database starts with the defaults below (created by `migrate`).

| Setting | Default | Used for |
|---|---|---|
| Title | `Django Forums App` | The site's name: the header, the browser tab, the visitors' home page, emails and authenticator apps |
| Tagline | `A private forum. Sign in to read and write.` | Under the name on the visitors' home page |
| Invitation note | `Membership is by invitation. …` | On the visitors' home page while signup is closed |
| Recent threads | 3 (1–10) | Threads under *Recent activity*, above the forum list |
| Latest threads | 15 (5–50) | Threads on the *Latest* page |
| Threads per page | 20 (5–100) | Threads per page of a forum |
| Posts per page | 25 (5–100) | Posts per page of a thread |
| Notification mail delay | 5 minutes (0–30) | How long a reply or direct message waits before its mail; 0 sends it at once |

Good to know:

- The texts are plain text: HTML or Markdown shows as typed.
- Set the name here, not under *Sites*: saving copies it into the *Sites* display name. *Sites* is only for the domain.
- People who set up two-factor authentication before a rename keep the old name in their authenticator app. It still works.
- Changing a page size moves posts and threads to other pages, so older links to `?page=N` (also those to a single post) may open a page without what they pointed to.

Security limits (posting, search, login) and anything needed at start-up are not here: they are in the settings files and `.env`, so changing them takes a deploy.

## GitHub login

Members can sign in with GitHub as well as with email and password. It's optional: until a GitHub app is set up, the login page doesn't show the GitHub button.

You need one GitHub app per address the site runs on, because a GitHub OAuth app has a single callback URL: one for development and one for production.

### 1. Create the app on GitHub

On GitHub: *Settings* → *Developer settings* → *OAuth Apps* → *New OAuth App*. For an organisation, use the organisation's settings instead.

| Field | Development | Production |
|---|---|---|
| Application name | e.g. `My forum (dev)` | e.g. `My forum` (members see it when they approve) |
| Homepage URL | `http://127.0.0.1:8000` | `https://forum.example.com` |
| Authorization callback URL | `http://127.0.0.1:8000/accounts/github/login/callback/` | `https://forum.example.com/accounts/github/login/callback/` |

Leave *Enable Device Flow* off. After *Register application*, generate a client secret and copy it at once: GitHub shows it only once.

### 2. Add it in the admin

In the Django admin (`/<ADMIN_URL>/`, default `/nimda/`): *Social applications* → *Add*.

- **Provider:** GitHub
- **Name:** anything, e.g. `GitHub`
- **Client id:** the app's *Client ID*
- **Secret key:** the client secret
- **Key:** leave empty
- **Sites:** move your site (in production the one you renamed to your domain, see [the deployment guide](deployment-vps.md#3-first-deployment)) to *Chosen sites*

Save. The login and signup pages now show *GitHub*.

The secret is stored in the database, so it is in database backups: treat those as secret anyway. To replace it, generate a new secret on GitHub, paste it here, then delete the old one on GitHub.

### How it behaves

- **Signing up with GitHub** follows the same rules as email: allowed while `DJANGO_SIGNUP_OPEN` is true, otherwise only with an invitation. With an invitation, the invited address must be one of the GitHub account's *verified* email addresses (primary or not); otherwise the site says signup is closed.
- **Existing members** who signed up with email can't start using GitHub from the login page: the site would treat it as a new signup. They connect GitHub first, while signed in, at `/accounts/3rdparty/`; after that the GitHub button signs them in.
- **Two-factor authentication** applies to GitHub logins too: whoever has an authenticator app is asked for a code after GitHub.
- The site asks GitHub only for the account's email addresses (`user:email` scope), not repository access.

### Check that it works

The tests don't log in to GitHub, so try it once on each site after setting it up:

1. Sign out, open the login page and choose *GitHub*. GitHub asks you to authorise the app, then sends you back to the site.
2. If the browser stops on the way, open its console: a Content Security Policy error means the policy blocks the redirect (`form-action` in `_CSP` in `project/settings/base.py` must allow `https://github.com`). A GitHub page about a *redirect_uri* means the callback URL in the app doesn't match the site's address exactly (scheme, host and trailing slash).
3. In production, the security log has a `login` line for the user.
