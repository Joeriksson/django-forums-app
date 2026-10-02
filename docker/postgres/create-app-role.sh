#!/bin/sh
# Run by the postgres image when the data volume is first created (mounted into
# /docker-entrypoint-initdb.d by docker-compose-prod.yml), never again after that.
#
# The image's own user, postgres, is a superuser. The app gets a role of its own that
# owns the forum database and nothing else: it can't create roles or databases, read
# files on the server or run programs there.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -v app_password="${POSTGRES_APP_PASSWORD:?Set POSTGRES_APP_PASSWORD in .env}" <<'EOSQL'
CREATE ROLE forum LOGIN PASSWORD :'app_password';
CREATE DATABASE forum OWNER forum;
-- The superuser's database is not for the app
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
EOSQL
