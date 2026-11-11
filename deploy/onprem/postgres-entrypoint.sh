#!/bin/sh
set -eu
# Official PostgreSQL entrypoint subsequently drops privileges to postgres.
# File-backed Compose secrets retain host modes: copy the TLS key to a private
# container directory rather than weakening PostgreSQL key checks.
mkdir -p /tmp/integrity-tls
cp /run/secrets/db_cert /tmp/integrity-tls/server.crt
cp /run/secrets/db_key /tmp/integrity-tls/server.key
chmod 700 /tmp/integrity-tls
chmod 600 /tmp/integrity-tls/server.key
chown -R postgres:postgres /tmp/integrity-tls
exec /usr/local/bin/docker-entrypoint.sh "$@"
