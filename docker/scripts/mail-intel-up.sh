#!/usr/bin/env bash
# Start Mail Intel stack with offline vault master (never put in .env files).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MASTER_FILE="${MAIL_INTEL_VAULT_MASTER_FILE:-$HOME/.ragflow-mail-intel/vault-master.txt}"

if [[ -z "${MAIL_INTEL_VAULT_MASTER:-}" ]]; then
  if [[ ! -f "$MASTER_FILE" ]]; then
    echo "ERROR: Set MAIL_INTEL_VAULT_MASTER or create $MASTER_FILE" >&2
    exit 1
  fi
  export MAIL_INTEL_VAULT_MASTER="$(tr -d '[:space:]' < "$MASTER_FILE")"
fi

cd "$ROOT/docker"
docker compose -f docker-compose-mail-intel.yml \
  --env-file .env --env-file .env.mail-intel \
  up -d "$@"
