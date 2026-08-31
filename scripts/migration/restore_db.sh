#!/usr/bin/env bash
# Restore a custom-format dump produced by scripts/migration/dump_db.sh.
# Target must already exist (the migration Compose db service creates
# POSTGRES_DB on first boot). Does not drop the database itself.
#
# Compose (docker-compose.migration.yml):
#   DUMP_FILE=/path/to/rforum_backup.dump \
#   PGHOST=127.0.0.1 PGPORT=5432 PGUSER=rforum PGDATABASE=rforum \
#   PGPASSWORD='...' ./scripts/migration/restore_db.sh
#
# k3s: copy the dump into the Postgres pod and run pg_restore there — see
# docs/k3s-deploy.md § "Restore production data". The clustered Postgres
# password is the one in Secret `rforum` (key postgres-password), which
# does not have to match the VM that produced the dump.
#
# Defaults match docker-compose.migration.yml's published loopback port (5432),
# not docker-compose.yml's dev port (5433).
set -euo pipefail

DUMP_FILE="${DUMP_FILE:-${1:-}}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-rforum}"
PGDATABASE="${PGDATABASE:-rforum}"

if [[ -z "${DUMP_FILE}" ]]; then
  echo "usage: DUMP_FILE=/path/to/file.dump $0" >&2
  echo "   or: $0 /path/to/file.dump" >&2
  exit 1
fi
if [[ ! -f "${DUMP_FILE}" ]]; then
  echo "error: dump file not found: ${DUMP_FILE}" >&2
  exit 1
fi

if [[ -z "${PGPASSWORD:-}" && -n "${PG_PASSWORD:-}" ]]; then
  export PGPASSWORD="${PG_PASSWORD}"
fi
if [[ -n "${PGPASSFILE:-}" ]]; then
  export PGPASSFILE
fi
if [[ -z "${PGPASSWORD:-}" && -z "${PGPASSFILE:-}" ]]; then
  echo "error: set PGPASSWORD (or PG_PASSWORD) or PGPASSFILE." >&2
  exit 1
fi

for bin in pg_restore psql; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: $bin not found in PATH. Install postgresql-client (major 16)." >&2
    exit 1
  fi
done

echo "Restoring ${DUMP_FILE} -> ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --exit-on-error \
  -h "${PGHOST}" \
  -p "${PGPORT}" \
  -U "${PGUSER}" \
  -d "${PGDATABASE}" \
  "${DUMP_FILE}"

echo "Restore finished. Row counts on key tables (app/models.py):"

psql \
  -h "${PGHOST}" \
  -p "${PGPORT}" \
  -U "${PGUSER}" \
  -d "${PGDATABASE}" \
  -v ON_ERROR_STOP=1 \
  -c "SELECT 'users' AS table, COUNT(*) AS rows FROM users
      UNION ALL
      SELECT 'presentations', COUNT(*) FROM presentations
      UNION ALL
      SELECT 'sessions', COUNT(*) FROM sessions
      ORDER BY 1;"
