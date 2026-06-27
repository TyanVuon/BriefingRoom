#!/usr/bin/env bash
# Bind-mount entrypoint: live repo at /ragflow, deps in /opt/ragflow-venv (named volume).
set -euo pipefail

export PYTHONPATH=/ragflow
export PATH="/opt/ragflow-venv/bin:${PATH}"
export UV_PROJECT_ENVIRONMENT=/opt/ragflow-venv

bootstrap_venv() {
  if [[ -x /opt/ragflow-venv/bin/python3 ]] && /opt/ragflow-venv/bin/python3 -c "import quart" 2>/dev/null; then
    return 0
  fi
  if [[ ! -f /ragflow/pyproject.toml ]]; then
    echo "ERROR: /ragflow/pyproject.toml missing — repo bind mount failed" >&2
    exit 1
  fi
  echo "Bootstrapping Python venv into /opt/ragflow-venv (first run only; may take 15–30 min)..."
  git config --global http.postBuffer 524288000
  git config --global http.lowSpeedLimit 0
  git config --global http.lowSpeedTime 999999
  local attempt
  for attempt in 1 2 3 4 5; do
    if (cd /ragflow && uv sync --python 3.13 --frozen); then
      echo "Python venv ready."
      return 0
    fi
    echo "uv sync attempt ${attempt}/5 failed — retrying in 20s..." >&2
    sleep 20
  done
  echo "ERROR: Could not bootstrap venv after 5 attempts" >&2
  exit 1
}

bootstrap_venv

if [[ ! -f /ragflow/VERSION ]]; then
  echo "mail-intel-dev" > /ragflow/VERSION
fi

if [[ ! -f /ragflow/web/dist/index.html ]]; then
  echo "WARN: /ragflow/web/dist missing — run: cd web && npm install && npm run build" >&2
fi

# entrypoint.sh expects /ragflow/conf/service_conf.yaml.template (stock image path)
mkdir -p /ragflow/conf
if [[ ! -f /ragflow/conf/service_conf.yaml.template ]]; then
  cp -f /ragflow/docker/service_conf.yaml.template /ragflow/conf/service_conf.yaml.template
fi

# Stage nginx configs where entrypoint.sh expects them (/etc/nginx/conf.d/ragflow.conf.*)
NGINX_SRC=/ragflow/docker/nginx
NGINX_DEST=/etc/nginx/conf.d
mkdir -p "$NGINX_DEST"
if [[ -d "$NGINX_SRC" ]]; then
  for f in ragflow.conf.python ragflow.conf.hybrid ragflow.conf.golang ragflow.https.conf; do
    if [[ -f "$NGINX_SRC/$f" ]]; then
      cp -f "$NGINX_SRC/$f" "$NGINX_DEST/$f"
    fi
  done
fi
if [[ -f "$NGINX_SRC/proxy.conf" ]]; then
  cp -f "$NGINX_SRC/proxy.conf" /etc/nginx/proxy.conf
fi
if [[ -f "$NGINX_SRC/nginx.conf" ]]; then
  cp -f "$NGINX_SRC/nginx.conf" /etc/nginx/nginx.conf
fi

exec /ragflow/docker/entrypoint.sh "$@"
