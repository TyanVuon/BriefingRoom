#!/usr/bin/env bash
# Wait for ragflow API then deploy Mail Intelligence Router DSL.
set -euo pipefail

RAGFLOW_HOST="${RAGFLOW_API_BASE:-http://ragflow-mail-intel:9380}"
MAX_WAIT="${MAIL_INTEL_DEPLOY_WAIT:-120}"

echo "Waiting for API at ${RAGFLOW_HOST} (max ${MAX_WAIT}s)..."
deadline=$((SECONDS + MAX_WAIT))
until curl -sf "${RAGFLOW_HOST}/api/v1/system/ping" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "ERROR: API not ready after ${MAX_WAIT}s" >&2
    exit 1
  fi
  sleep 2
done
echo "API ready."

export PYTHONPATH=/ragflow
export RAGFLOW_API_BASE="${RAGFLOW_HOST}"

if [[ -z "${MAIL_INTEL_AGENT_ID:-}" ]]; then
  echo "ERROR: MAIL_INTEL_AGENT_ID is required (set in .env.mail-intel or export)" >&2
  exit 1
fi

if [[ -z "${RAGFLOW_API_EMAIL:-}" || -z "${RAGFLOW_API_PASSWORD:-}" ]]; then
  echo "ERROR: Export RAGFLOW_API_EMAIL and RAGFLOW_API_PASSWORD in your shell before deploy." >&2
  echo "       Do not store passwords in .env files — see docker/README-mail-intel.md" >&2
  exit 1
fi

PY="/opt/ragflow-venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="/opt/ragflow-venv/bin/python3"
fi
if [[ ! -x "$PY" ]]; then
  echo "ERROR: Python not found in /opt/ragflow-venv — bootstrap venv first" >&2
  exit 1
fi

DEPLOY_ARGS=(--skeleton)
if [[ "${MAIL_INTEL_INJECT_VAULT:-}" == "1" ]]; then
  DEPLOY_ARGS=(--inject-from-vault)
fi
"$PY" scripts/build_mail_intelligence_router.py "${DEPLOY_ARGS[@]}" --update --agent-id "${MAIL_INTEL_AGENT_ID}"
echo "Mail Intelligence Router deployed to agent ${MAIL_INTEL_AGENT_ID}"
