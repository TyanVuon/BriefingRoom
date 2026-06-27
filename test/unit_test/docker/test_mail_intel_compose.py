#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Validate Mail Intelligence Docker compose configuration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOCKER_DIR = ROOT / "docker"
COMPOSE_FILE = DOCKER_DIR / "docker-compose-mail-intel.yml"
ENV_EXAMPLE = DOCKER_DIR / ".env.mail-intel.example"
DEPLOY_SCRIPT = DOCKER_DIR / "scripts" / "mail-intel-deploy.sh"
COMPOSE_TEXT = COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rendered_compose() -> dict | None:
    if shutil.which("docker") is None:
        return None
    env_mail = DOCKER_DIR / ".env.mail-intel"
    if not env_mail.is_file():
        env_mail.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(COMPOSE_FILE),
                "--env-file",
                str(DOCKER_DIR / ".env"),
                "--env-file",
                str(env_mail),
                "config",
                "--format",
                "json",
            ],
            cwd=DOCKER_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return json.loads(proc.stdout)


def test_compose_file_exists():
    assert COMPOSE_FILE.is_file()


def test_uses_infinity_not_elasticsearch():
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "DOC_ENGINE=infinity" in env_example
    assert "COMPOSE_PROFILES=infinity" in env_example
    assert "DOC_ENGINE: infinity" in COMPOSE_TEXT
    assert "infinity:" in COMPOSE_TEXT


def test_segmented_networks():
    assert "edge:" in COMPOSE_TEXT
    assert "app:" in COMPOSE_TEXT
    assert "data:" in COMPOSE_TEXT
    assert "internal: true" in COMPOSE_TEXT


def test_ragflow_mail_intel_service():
    assert "ragflow-mail-intel:" in COMPOSE_TEXT
    assert "OBSIDIAN_VAULT_PATH: /vault" in COMPOSE_TEXT
    assert "MAIL_INTEL_RP_ORIGIN:" in COMPOSE_TEXT
    assert "http://localhost" in COMPOSE_TEXT
    assert 'MAIL_INTEL_HARDWARE_STORE: /ragflow/config/hardware_auth' in COMPOSE_TEXT


def test_data_tier_internal_only():
    for svc in ("mysql:", "redis:", "minio:", "infinity:"):
        assert svc in COMPOSE_TEXT
    assert "ports: !reset []" in COMPOSE_TEXT


def test_stock_ragflow_image_disabled():
    assert 'profiles: ["never"]' in COMPOSE_TEXT


def test_deploy_init_job():
    assert "mail-intel-deploy:" in COMPOSE_TEXT
    assert 'profiles: ["init"]' in COMPOSE_TEXT
    assert "mail-intel-deploy.sh" in COMPOSE_TEXT


def test_deploy_script_exists():
    assert DEPLOY_SCRIPT.is_file()
    text = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "build_mail_intelligence_router.py" in text
    assert "system/ping" in text


def test_dockerfile_copies_scripts():
    dockerfile = (ROOT / "docker" / "Dockerfile.mail-intel-runtime").read_text(encoding="utf-8")
    assert "mail-intel-entrypoint.sh" in dockerfile
    assert "/opt/ragflow-venv" in dockerfile
    entrypoint = (DOCKER_DIR / "scripts" / "mail-intel-entrypoint.sh").read_text(encoding="utf-8")
    assert "bootstrap_venv" in entrypoint
    assert "uv sync" in entrypoint
    compose_text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "..:/ragflow:rw" in compose_text
    assert "mail_intel_venv:/opt/ragflow-venv" in compose_text
    assert "Dockerfile.mail-intel-runtime" in compose_text


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_docker_compose_config_renders(rendered_compose):
    assert rendered_compose is not None
    services = rendered_compose["services"]
    assert "ragflow-mail-intel" in services
    assert "infinity" in services
    assert "es01" not in services
    rf = services["ragflow-mail-intel"]
    assert any("80" in str(p) for p in rf.get("ports", []))
    for name in ("mysql", "redis", "minio", "infinity"):
        assert services[name].get("ports") in (None, [])


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_obsidian_blueprint_saved():
    blueprint_path = os.environ.get("OBSIDIAN_BLUEPRINT_PATH", "").strip()
    if not blueprint_path:
        pytest.skip("Set OBSIDIAN_BLUEPRINT_PATH to a local blueprint markdown file")
    blueprint = Path(blueprint_path)
    assert blueprint.is_file()
    text = blueprint.read_text(encoding="utf-8")
    assert "Infinity" in text
    assert "docker-compose-mail-intel.yml" in text
