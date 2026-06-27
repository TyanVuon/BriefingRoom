#!/bin/bash
# Source this file to use the isolated RAGFlow Python environment.
#   source scripts/activate-ragflow.sh

RAGFLOW_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_PROJECT_ENVIRONMENT="$RAGFLOW_ROOT/uv-rag-env"
export PYTHONPATH="$RAGFLOW_ROOT"

if [ ! -x "$UV_PROJECT_ENVIRONMENT/bin/python" ]; then
  echo "uv-rag-env not found. Run: UV_PROJECT_ENVIRONMENT=uv-rag-env uv sync --python 3.13"
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1091
source "$UV_PROJECT_ENVIRONMENT/bin/activate"
echo "RAGFlow env: $UV_PROJECT_ENVIRONMENT"
