#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Encrypted at-rest storage for mail-intelligence secrets and prompts (zero-trust)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from common.crypto_utils import AES256CBC

LOGGER = logging.getLogger(__name__)

SEALED_DIR = Path(os.environ.get("MAIL_INTEL_SEALED_DIR", "agent/prompts/sealed/mail_intel"))
VAULT_DIR = Path(os.environ.get("MAIL_INTEL_VAULT_DIR", "config/privacy_vault"))


def _derive_key(*parts: str) -> bytes:
    material = "|".join(parts).encode("utf-8")
    return hashlib.sha256(material).digest()


def _user_vault_path(user_id: str) -> Path:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    return VAULT_DIR / f"{digest}.vault"


def seal_blob(*, user_id: str, hardware_token: str, name: str, plaintext: str) -> Path:
    """Encrypt plaintext with a key bound to user + hardware session."""
    key = _derive_key(user_id, hardware_token, "mail-intel-vault")
    crypto = AES256CBC(key=key)
    payload = {
        "name": name,
        "ciphertext": base64.b64encode(crypto.encrypt(plaintext.encode("utf-8"))).decode("ascii"),
    }
    out_dir = SEALED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}.sealed"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out_path


def unseal_blob(*, user_id: str, hardware_token: str, name: str) -> str:
    path = SEALED_DIR / f"{name}.sealed"
    if not path.is_file():
        raise FileNotFoundError(f"Sealed blob not found: {name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = _derive_key(user_id, hardware_token, "mail-intel-vault")
    crypto = AES256CBC(key=key)
    raw = base64.b64decode(payload["ciphertext"])
    return crypto.decrypt(raw).decode("utf-8")


def seal_user_vault(*, user_id: str, hardware_token: str, secrets: dict[str, Any]) -> None:
    key = _derive_key(user_id, hardware_token, "mail-intel-user-vault")
    crypto = AES256CBC(key=key)
    blob = base64.b64encode(crypto.encrypt(json.dumps(secrets).encode("utf-8"))).decode("ascii")
    path = _user_vault_path(user_id)
    path.write_text(json.dumps({"blob": blob}, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def unseal_user_vault(*, user_id: str, hardware_token: str) -> dict[str, Any]:
    path = _user_vault_path(user_id)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    key = _derive_key(user_id, hardware_token, "mail-intel-user-vault")
    crypto = AES256CBC(key=key)
    raw = base64.b64decode(payload["blob"])
    return json.loads(crypto.decrypt(raw).decode("utf-8"))


def load_sealed_prompt(name: str, *, user_id: str, hardware_token: str) -> str | None:
    try:
        return unseal_blob(user_id=user_id, hardware_token=hardware_token, name=name)
    except Exception as exc:
        LOGGER.debug("Sealed prompt %s unavailable: %s", name, exc)
        return None
