# Migration Plan: Python 3.12 + Django 4.2 + uv

**Created:** 2026-03-16
**Context:** Project was last updated ~4 years ago, ran on Python 3.10. venv is now Python 3.12, and several dependencies fail to install. Target: Django 4.2 LTS, Python 3.12, switch from pip-compile to Astral uv.

---

## Phase 1 — Switch to `uv`

Replace `requirements.in` / `requirements.txt` (pip-compile workflow) with a `pyproject.toml` + `uv.lock` workflow.

**Steps:**
1. Create `pyproject.toml` with `[project]` and `[project.optional-dependencies]` sections listing direct dependencies (replacing `requirements.in`)
2. Run `uv lock` to generate `uv.lock` (replaces compiled `requirements.txt`)
3. Run `uv sync` to install from the lockfile
4. Update `Makefile` — replace `pip install -r requirements.txt` with `uv sync`
5. Update `Dockerfile` — use `uv` to install deps (Astral provides a Docker helper image, or `COPY --from=ghcr.io/astral-sh/uv uv /bin/uv`)
6. Keep `requirements.txt` only if needed for CI backwards compat, otherwise drop it

---

## Phase 2 — Update Django (4.0.8 → 4.2.x)

Django 4.2 is an LTS release. Key things to check after upgrade:

- `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"` — set explicitly to silence warnings
- `USE_L10N` is now `True` by default (was `False` in older defaults); verify locale formatting in templates
- The `CSRF_TRUSTED_ORIGINS` format changed in 4.0 (needs scheme now) — probably already set correctly if the app ran on 4.0
- Run `python manage.py check` after the switch

---

## Phase 3 — Dependency Updates

| Package | Old | New target | Breaking changes to handle |
|---|---|---|---|
| `Django` | 4.0.8 | `>=4.2,<4.3` | See Phase 2 |
| `celery` | 5.2.7 | `>=5.5` | Python 3.12 support added in 5.5.0; not present in 5.2/5.3 |
| `django-allauth` | 0.47.0 | `>=0.61,<0.64` | Settings restructured; `SOCIALACCOUNT_PROVIDERS` config may need updating; cap at 0.63 to stay before Django 4.0 drop |
| `django-crispy-forms` | 1.13.0 | `>=2.1` | **Breaking:** template packs now separate packages — add `crispy-bootstrap4` (or `crispy-bootstrap5`) to deps and `INSTALLED_APPS`; add `CRISPY_TEMPLATE_PACK` setting |
| `django-debug-toolbar` | 3.2.4 | `>=4.2` | Min version for Django 4.2 is 4.2; settings restructured in 4.x (`SHOW_TOOLBAR_CALLBACK` path changed) |
| `django-lifecycle` | 0.9.3 | `>=1.0` | Confirm hook order behavior unchanged; project is low-maintenance but 1.0 is 3.12/4.2 compatible |
| `django-permissions-auditor` | 1.0.4 | `>=1.2.0` | 1.2.0 added Python 3.12 to test matrix |
| `django-redis` | 5.1.0 | `>=5.4` | Requires `redis-py` 4.x+ in newer versions |
| `djangorestframework` | 3.13.1 | `>=3.14` | 3.14 adds Django 4.2 support |
| `dj-database-url` | 0.5.0 | `>=2.1,<3` | **Breaking:** `config()` signature changed; stop at <3 to avoid 3.0 breaking changes |
| `redis` | 3.5.3 | `>=4.6` | **Breaking:** 4.x changed connection pool API; `from_url()` behavior changed; django-redis 5.4+ handles this |
| `psycopg2-binary` | 2.9.2 | `>=2.9.10` | Python 3.12 wheels available from 2.9.9+ |
| `gunicorn` | 20.1.0 | `>=23` | No breaking changes for this app |
| `martor` | 1.6.13 | `>=1.6.40,<1.7` | Cap at 1.6.x series; compatible with Python 3.12 |
| `sentry-sdk` | 1.5.1 | `>=1.40` | Minimal API changes for basic usage |
| `pytest` | 6.2.5 | `>=7.4` | Python 3.12 support from 7.3; removes `py` as runtime dep |
| `pytest-cov` | 3.0.0 | `>=5.0` | Compatible with pytest 7+ |
| `pytest-django` | 4.5.2 | `>=4.8` | Compatible with pytest 7+ and Django 4.2 |
| `pytest-xdist` | 2.5.0 | `>=3.5` | Absorbs `pytest-forked`; drop `pytest-forked` |
| `requests` | 2.28.0 | `>=2.31` | No breaking changes |
| `pyjwt` | 2.4.0 | `>=2.8` | No breaking changes |
| `cryptography` | 38.0.3 | `>=42` | Pre-built wheels available for Python 3.12 |

**Packages to drop:**
- `py` — no longer needed by modern pytest
- `pytest-forked` — deprecated, functionality merged into `pytest-xdist`
- `coreapi` / `coreschema` / `itypes` / `uritemplate` — for DRF's old CoreAPI schema support removed in DRF 3.14; switch to OpenAPI
- `more-itertools` — remove from direct deps (not actually used directly)
- `six` — Python 2 compat shim, no longer needed

---

## Phase 4 — Code Changes Required by Breaking Dependencies

These require actual code edits, not just version bumps:

1. **`dj-database-url` 2.x**: Review `DATABASE_URL` parsing call in settings — verify `ssl_require` param rename if used
2. **`django-crispy-forms` 2.x**: Add `crispy-bootstrap4` (or `crispy-bootstrap5`) dep + update `INSTALLED_APPS` + add `CRISPY_TEMPLATE_PACK = "bootstrap4"` (or `bootstrap5`) to settings
3. **`django-allauth` 0.61+**: Check `SOCIALACCOUNT_PROVIDERS` GitHub config format — structure changed in 0.50+; review settings prefix (`ACCOUNT_EMAIL_REQUIRED` etc.)
4. **`django-debug-toolbar` 4.x**: Verify `INTERNAL_IPS` setting; check middleware order
5. **`coreapi` removal**: Remove any `coreapi` schema views from `api/` and `urls.py`; switch to DRF's built-in OpenAPI (`rest_framework.schemas.openapi`) if API docs are needed

---

## Phase 5 — Update Tooling Files

- **`Dockerfile`**: Change base image to `python:3.12-slim`; install `uv`; replace `pip install` with `uv sync --no-dev` for production
- **`docker-compose-dev.yml`**: No changes needed (PostgreSQL 11 upgrade is a separate concern)
- **`.github/workflows/django.yml`**: Update Python versions to `["3.12"]`; install `uv` in CI; replace `pip install` step with `uv sync`
- **`Makefile`**: Update any `pip install` or `pip-compile` references to `uv` equivalents

---

## Suggested Execution Order

```
1. Create pyproject.toml (direct deps with updated version ranges)
2. uv lock  →  resolve and verify no conflicts
3. uv sync  →  install
4. python manage.py check  →  catch Django-level issues
5. Fix crispy-forms INSTALLED_APPS + setting
6. Fix dj-database-url settings call
7. Fix django-allauth settings
8. Remove coreapi from urls/views
9. Run tests:  pytest tests/ -v
10. Fix remaining test failures iteratively
11. Update Dockerfile + CI workflow
```

---

## Biggest Risks

- **`django-allauth`** — most likely to require settings/template changes; large version gap (0.47 → 0.61+)
- **`celery` 5.5** — required for Python 3.12; verify broker URL format unchanged
- **`redis` 3→4** — connection pool internals changed but `django-redis` 5.4+ abstracts this away

## Status

- [x] Phase 1: Switch to uv — completed 2026-03-16
  - Created `pyproject.toml` (replaces `requirements.in` + `requirements.txt`)
  - Generated `uv.lock`; 63 packages resolved (down from 80+)
  - Removed `pytest.ini` and `.coveragerc` (config merged into `pyproject.toml`)
  - Updated `Dockerfile` to Python 3.12-slim + uv
  - Updated CI workflow to use `astral-sh/setup-uv` + Python 3.12
  - Added `.python-version` (3.12), removed it from `.gitignore`
  - Fixed `allauth.account.middleware.AccountMiddleware` missing from `MIDDLEWARE` (allauth 0.56+ requirement)
  - Replaced coreapi docs in `api/urls.py` with DRF OpenAPI schema (coreapi removed in DRF 3.14)
  - Added `crispy_bootstrap4` to `INSTALLED_APPS` (crispy-forms 2.x requirement)
  - Set `DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'` to silence W042 warnings
  - Added `LocMemCache` override to test settings (avoids Redis connection during tests)
  - Django check passes: 0 issues
- [x] Phase 2: Django 4.0.8 → 4.2 — Django 4.2.29 installed; DEFAULT_AUTO_FIELD set; USE_L10N already True; manage.py check: 0 issues
- [x] Phase 3: Dependency version updates — all deps updated via uv; breaking changes audited: dj-database-url API unchanged, debug-toolbar JQUERY_URL silently ignored, allauth flat ACCOUNT_* settings still work in 0.63
- [x] Phase 4: Code changes for breaking deps — all 30 tests pass; development settings check: 0 issues
- [x] Phase 5: Tooling files — Dockerfile (python:3.12-slim + uv + /opt/venv), CI (setup-uv + Python 3.12), Makefile (docker compose), docker-compose-dev.yml (postgres:16, POSTGRES_PASSWORD), docker-compose-prod.yml (postgres:16, POSTGRES_PASSWORD)

## Follow-up tasks (post-merge)
- Remove deprecated `JQUERY_URL` from `DEBUG_TOOLBAR_CONFIG` in `development.py` (removed in debug-toolbar 4.x)
- Migrate flat `ACCOUNT_*` allauth settings in `base.py` to the new dict-based format (deprecated in allauth 0.50+)
