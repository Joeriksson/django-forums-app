# GitHub login

Members can sign in with GitHub as well as with email and password. It's optional: until a GitHub app is set up, the login page doesn't show the GitHub button.

You need one GitHub app per address the site runs on, because a GitHub OAuth app has a single callback URL: one for development and one for production.

## 1. Create the app on GitHub

On GitHub: *Settings* → *Developer settings* → *OAuth Apps* → *New OAuth App*. For an organisation, use the organisation's settings instead.

| Field | Development | Production |
|---|---|---|
| Application name | e.g. `Wildvasa (dev)` | e.g. `Wildvasa` (members see it when they approve) |
| Homepage URL | `http://127.0.0.1:8000` | `https://forum.example.com` |
| Authorization callback URL | `http://127.0.0.1:8000/accounts/github/login/callback/` | `https://forum.example.com/accounts/github/login/callback/` |

Leave *Enable Device Flow* off. After *Register application*, generate a client secret and copy it at once: GitHub shows it only once.

## 2. Add it in the admin

In the Django admin (`/<ADMIN_URL>/`, default `/nimda/`): *Social applications* → *Add*.

- **Provider:** GitHub
- **Name:** anything, e.g. `GitHub`
- **Client id:** the app's *Client ID*
- **Secret key:** the client secret
- **Key:** leave empty
- **Sites:** move your site (in production the one you renamed to your domain, see [the deployment guide](deployment-vps.md#3-first-deployment)) to *Chosen sites*

Save. The login and signup pages now show *GitHub*.

The secret is stored in the database, so it is in database backups: treat those as secret anyway. To replace it, generate a new secret on GitHub, paste it here, then delete the old one on GitHub.

## How it behaves

- **Signing up with GitHub** follows the same rules as email: allowed while `DJANGO_SIGNUP_OPEN` is true, otherwise only with an invitation. With an invitation, the invited address must be one of the GitHub account's *verified* email addresses (primary or not); otherwise the site says signup is closed.
- **Existing members** who signed up with email can't start using GitHub from the login page: the site would treat it as a new signup. They connect GitHub first, while signed in, at `/accounts/3rdparty/`; after that the GitHub button signs them in.
- **Two-factor authentication** applies to GitHub logins too: whoever has an authenticator app is asked for a code after GitHub.
- The site asks GitHub only for the account's email addresses (`user:email` scope), not repository access.

## Check that it works

The tests don't log in to GitHub, so try it once on each site after setting it up:

1. Sign out, open the login page and choose *GitHub*. GitHub asks you to authorise the app, then sends you back to the site.
2. If the browser stops on the way, open its console: a Content Security Policy error means the policy blocks the redirect (`form-action` in `_CSP` in `project/settings/base.py` must allow `https://github.com`). A GitHub page about a *redirect_uri* means the callback URL in the app doesn't match the site's address exactly (scheme, host and trailing slash).
3. In production, the security log has a `login` line for the user.
