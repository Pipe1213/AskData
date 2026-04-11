#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DATASET="${1:-pagila}"
SEED_FILE="${REPO_ROOT}/demo_data/seed/${DATASET}.sql"
ACTIVE_DATASET_FILE="${REPO_ROOT}/demo_data/active_dataset.txt"

if [[ ! -f "${SEED_FILE}" ]]; then
  echo "Unknown dataset '${DATASET}'. Expected a seed file at ${SEED_FILE}." >&2
  exit 1
fi

if ! docker compose ps postgres >/dev/null 2>&1; then
  echo "PostgreSQL service is not available. Start it first with 'make docker-up'." >&2
  exit 1
fi

POSTGRES_DB="$(docker compose exec -T postgres printenv POSTGRES_DB | tr -d '\r')"
POSTGRES_USER="$(docker compose exec -T postgres printenv POSTGRES_USER | tr -d '\r')"

if [[ -z "${POSTGRES_DB}" || -z "${POSTGRES_USER}" ]]; then
  echo "Could not resolve PostgreSQL container environment." >&2
  exit 1
fi

echo "Reloading dataset '${DATASET}' into database '${POSTGRES_DB}'..."

docker compose exec -T postgres psql \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
SQL

docker compose exec -T postgres psql \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 < "${SEED_FILE}"

printf "%s\n" "${DATASET}" > "${ACTIVE_DATASET_FILE}"

if command -v curl >/dev/null 2>&1; then
  curl -fsS -X POST http://127.0.0.1:8000/schema/reload >/dev/null 2>&1 || true
fi

echo "Loaded '${DATASET}'."
echo "If the backend was not running, restart it before querying the new schema."
