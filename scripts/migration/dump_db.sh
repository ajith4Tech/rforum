#!/usr/bin/env bash
# Dump the rforum Postgres database to a custom-format archive.
# Never prints or embeds the password. Does not drop or modify the source DB.
#
# Connection (libpq names, with this repo's docker-compose.yml defaults):
#   PGHOST       default localhost
#   PGPORT       default 5433   (.env.example DATABASE_URL / compose host port)
#   PGUSER       default rforum
#   PGDATABASE   default rforum
#   PGPASSWORD   or PG_PASSWORD, or PGPASSFILE (~/.pgpass style)
#
# Output:
#   BACKUP_DIR   default ./db-backups
#
# Example:
#   PGPASSWORD='...' BACKUP_DIR=/home/falcon/Projects/rforum-migration/db-backups \
#     ./scripts/migration/dump_db.sh
set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-rforum}"
PGDATABASE="${PGDATABASE:-rforum}"
BACKUP_DIR="${BACKUP_DIR:-./db-backups}"

if [[ -z "${PGPASSWORD:-}" && -n "${PG_PASSWORD:-}" ]]; then
  export PGPASSWORD="${PG_PASSWORD}"
fi
if [[ -n "${PGPASSFILE:-}" ]]; then
  export PGPASSFILE
fi

if [[ -z "${PGPASSWORD:-}" && -z "${PGPASSFILE:-}" ]]; then
  echo "error: set PGPASSWORD (or PG_PASSWORD) or PGPASSFILE — password is not read from this script." >&2
  exit 1
fi

for bin in pg_dump pg_restore; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "error: $bin not found in PATH. Install postgresql-client (matching server major 16) or run from a postgres:16-alpine container." >&2
    exit 1
  fi
done

mkdir -p "${BACKUP_DIR}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/rforum-${PGDATABASE}-${STAMP}.dump"

echo "Dumping ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE} -> ${OUT}"

pg_dump \
  -h "${PGHOST}" \
  -p "${PGPORT}" \
  -U "${PGUSER}" \
  -d "${PGDATABASE}" \
  -F custom \
  --no-owner \
  --no-acl \
  -f "${OUT}"

SIZE="$(wc -c < "${OUT}" | tr -d ' ')"
if [[ "${SIZE}" -lt 1 ]]; then
  echo "error: dump file is empty (${OUT})." >&2
  exit 1
fi

# Human-readable size (1024-based); fall back to bytes if numfmt is missing.
if command -v numfmt >/dev/null 2>&1; then
  SIZE_H="$(numfmt --to=iec --suffix=B "${SIZE}")"
else
  SIZE_H="${SIZE} bytes"
fi

LIST_FILE="$(mktemp)"
trap 'rm -f "${LIST_FILE}"' EXIT
pg_restore --list "${OUT}" > "${LIST_FILE}"

# pg_restore --list TOC lines look like:
#   "264; 1259 16386 TABLE public users ..."
#   "3412; 0 16386 TABLE DATA public users ..."
TABLE_DATA_COUNT="$(grep -c ' TABLE DATA ' "${LIST_FILE}" || true)"
TABLE_COUNT="$(grep ' TABLE ' "${LIST_FILE}" | grep -v ' TABLE DATA ' | wc -l | tr -d ' ')"

echo "Dump OK"
echo "  file:        ${OUT}"
echo "  size:        ${SIZE_H} (${SIZE} bytes)"
echo "  TOC TABLE:      ${TABLE_COUNT}  (schema objects named TABLE; visual check — not a live row count)"
echo "  TOC TABLE DATA: ${TABLE_DATA_COUNT}  (one per dumped table's data section; 0 means truncated/empty schema dump)"
echo
echo "TOC excerpt (first 20 non-comment lines):"
grep -v '^;' "${LIST_FILE}" | head -n 20 || true

if [[ "${TABLE_DATA_COUNT}" -lt 1 ]]; then
  echo "warning: no TABLE DATA entries in the archive list — dump may be schema-only or truncated." >&2
fi

# --- SSH tunnel (when Postgres is only reachable from the current VM/VPC) ---
# Leave this commented; run the tunnel in another terminal, then point PGHOST
# at the local listen port.
#
#   ssh -N -L 15432:127.0.0.1:5433 USER@CURRENT_EC2_HOST
#   PGHOST=127.0.0.1 PGPORT=15432 PGPASSWORD='...' ./scripts/migration/dump_db.sh
#
# If Postgres is inside k3s on the current host (docs/k3s-deploy.md, namespace
# rforum) instead of docker-compose.yml's published 5433, port-forward first:
#
#   kubectl -n rforum port-forward svc/<postgres-service> 15432:5432
#   PGHOST=127.0.0.1 PGPORT=15432 ... ./scripts/migration/dump_db.sh
# TODO: confirm the live Postgres Service name on the current host — it is
# not hardcoded in this repo's running-cluster state (Helm names it from the
# release; see deploy/helm/rforum/templates/postgresql-service.yaml).
