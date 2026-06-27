#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Encrypted local vault for mail-intelligence secrets (compute–storage separation)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LOGGER = logging.getLogger(__name__)


def _redis_conn():
    """Lazy import avoids circular import when CLI init runs outside the API server."""
    from rag.utils.redis_conn import REDIS_CONN

    return REDIS_CONN

VAULT_DIR = Path(os.environ.get("MAIL_INTEL_LOCAL_VAULT", "config/local_vault"))
MASTER_ENV = "MAIL_INTEL_VAULT_MASTER"
SESSION_TTL = int(os.environ.get("MAIL_INTEL_VAULT_SESSION_TTL_SEC", "3600"))
TOTP_ISSUER = os.environ.get("MAIL_INTEL_TOTP_ISSUER", "RAGFlow Mail Intel")
_VAULT_SALT = "mail-intel-local-vault-v1"
_META_SALT = "mail-intel-local-vault-meta-v1"
_SESSION_PREFIX = "mail-intel:local-vault-session:"
_DATA_PREFIX = "mail-intel:local-vault-data:"

SEALED_CATEGORIES = ("api_keys", "prompts", "connectors", "ragflow_creds")


class VaultError(Exception):
    """User-safe vault operation failure."""


class VaultLockedError(VaultError):
    """Vault or scope is not unlocked for this session."""


def _require_master() -> str:
    master = os.environ.get(MASTER_ENV, "").strip()
    if not master:
        raise VaultError(
            f"{MASTER_ENV} is not configured. Set it in your host environment (never commit)."
        )
    return master


def _user_digest(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]


def _meta_path(user_id: str) -> Path:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    return VAULT_DIR / f"{_user_digest(user_id)}.meta.json"


def _blob_path(user_id: str) -> Path:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    return VAULT_DIR / f"{_user_digest(user_id)}.vault"


def _derive_key(*parts: str) -> bytes:
    material = "|".join(parts).encode("utf-8")
    return hashlib.sha256(material).digest()


def _at_rest_key(user_id: str) -> bytes:
    return _derive_key(_require_master(), user_id, _VAULT_SALT)


def _meta_key(user_id: str) -> bytes:
    return _derive_key(_require_master(), user_id, _META_SALT)


def _encrypt_blob(plaintext: bytes, key: bytes) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_blob(encoded: str, key: bytes) -> bytes:
    raw = base64.b64decode(encoded)
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def vault_initialized(user_id: str) -> bool:
    return _meta_path(user_id).is_file() and _blob_path(user_id).is_file()


def _load_meta(user_id: str) -> dict[str, Any]:
    path = _meta_path(user_id)
    if not path.is_file():
        raise VaultError("Local vault is not initialized. Run scripts/init_mail_intel_vault.py.")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_meta(user_id: str, payload: dict[str, Any]) -> None:
    path = _meta_path(user_id)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_encrypted_blob(user_id: str) -> dict[str, Any]:
    path = _blob_path(user_id)
    if not path.is_file():
        raise VaultError("Local vault blob is missing.")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_encrypted_blob(user_id: str, envelope: dict[str, Any]) -> None:
    path = _blob_path(user_id)
    path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _empty_categories() -> dict[str, Any]:
    return {name: {} for name in SEALED_CATEGORIES}


def _decrypt_categories(user_id: str) -> dict[str, Any]:
    envelope = _load_encrypted_blob(user_id)
    blob = envelope.get("blob")
    if not blob:
        return _empty_categories()
    raw = _decrypt_blob(blob, _at_rest_key(user_id))
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        return _empty_categories()
    out = _empty_categories()
    for key in SEALED_CATEGORIES:
        section = data.get(key)
        if isinstance(section, dict):
            out[key] = section
    return out


def _encrypt_categories(user_id: str, categories: dict[str, Any]) -> None:
    payload = {name: categories.get(name, {}) for name in SEALED_CATEGORIES}
    blob = _encrypt_blob(json.dumps(payload, separators=(",", ":")).encode("utf-8"), _at_rest_key(user_id))
    _save_encrypted_blob(user_id, {"v": 1, "cipher": "aes-256-gcm", "blob": blob})


def _session_key(user_id: str) -> str:
    return f"{_SESSION_PREFIX}{user_id}"


def _data_key(user_id: str) -> str:
    return f"{_DATA_PREFIX}{user_id}"


def _session_payload(user_id: str) -> dict[str, Any] | None:
    try:
        raw = _redis_conn().get(_session_key(user_id))
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _store_session(user_id: str, *, vault: bool, obsidian: bool) -> None:
    payload = {
        "vault": vault,
        "obsidian": obsidian,
        "unlocked_at": int(time.time()),
    }
    try:
        _redis_conn().set(_session_key(user_id), json.dumps(payload), SESSION_TTL)
    except Exception as exc:
        raise VaultError("Vault session store unavailable.") from exc


def _store_decrypted_cache(user_id: str, categories: dict[str, Any]) -> None:
    try:
        _redis_conn().set(_data_key(user_id), json.dumps(categories), SESSION_TTL)
    except Exception as exc:
        raise VaultError("Vault session store unavailable.") from exc


def _clear_session(user_id: str) -> None:
    try:
        _redis_conn().delete(_session_key(user_id))
        _redis_conn().delete(_data_key(user_id))
    except Exception:
        pass


def _cached_categories(user_id: str) -> dict[str, Any] | None:
    try:
        raw = _redis_conn().get(_data_key(user_id))
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def generate_totp_secret() -> str:
    try:
        import pyotp
    except ImportError as exc:  # pragma: no cover
        raise VaultError("pyotp is required. Run: uv add pyotp") from exc
    return pyotp.random_base32()


def totp_provisioning_uri(*, user_id: str, secret: str) -> str:
    try:
        import pyotp
    except ImportError as exc:  # pragma: no cover
        raise VaultError("pyotp is required. Run: uv add pyotp") from exc
    return pyotp.TOTP(secret).provisioning_uri(name=user_id, issuer_name=TOTP_ISSUER)


def totp_qr_data_url(provisioning_uri: str) -> str | None:
    """Return a PNG data URL for authenticator enrollment, or None if qrcode is unavailable."""
    try:
        import io

        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(border=1)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def begin_totp_setup(*, user_id: str) -> dict[str, Any]:
    """First-time TOTP enrollment: create vault and return one-time QR provisioning data."""
    if vault_initialized(user_id):
        raise VaultError("Local vault is already initialized. Enter your authenticator code to unlock.")
    secret = init_vault(user_id=user_id)
    uri = totp_provisioning_uri(user_id=user_id, secret=secret)
    return {
        "initialized": True,
        "provisioning_uri": uri,
        "qr_data_url": totp_qr_data_url(uri),
        "issuer": TOTP_ISSUER,
    }


def verify_totp(user_id: str, code: str) -> bool:
    meta = _load_meta(user_id)
    enc_secret = meta.get("totp_secret_enc")
    if not enc_secret:
        raise VaultError("TOTP is not configured for this vault.")
    try:
        import pyotp
    except ImportError as exc:  # pragma: no cover
        raise VaultError("pyotp is required. Run: uv add pyotp") from exc
    secret = _decrypt_blob(enc_secret, _meta_key(user_id)).decode("utf-8")
    totp = pyotp.TOTP(secret)
    normalized = "".join(ch for ch in str(code or "").strip() if ch.isdigit())
    return bool(normalized) and totp.verify(normalized, valid_window=1)


def init_vault(*, user_id: str, totp_secret: str | None = None, categories: dict[str, Any] | None = None) -> str:
    """Create meta + encrypted blob. Returns base32 TOTP secret (store offline)."""
    _require_master()
    secret = totp_secret or generate_totp_secret()
    enc_secret = _encrypt_blob(secret.encode("utf-8"), _meta_key(user_id))
    _save_meta(user_id, {"v": 1, "totp_secret_enc": enc_secret})
    merged = _empty_categories()
    if categories:
        for key in SEALED_CATEGORIES:
            section = categories.get(key)
            if isinstance(section, dict):
                merged[key] = section
    _encrypt_categories(user_id, merged)
    return secret


def seal_categories(*, user_id: str, categories: dict[str, Any]) -> None:
    """Replace vault categories at rest (vault must exist)."""
    if not vault_initialized(user_id):
        init_vault(user_id=user_id, categories=categories)
        return
    current = _decrypt_categories(user_id)
    for key in SEALED_CATEGORIES:
        section = categories.get(key)
        if isinstance(section, dict):
            current[key] = section
    _encrypt_categories(user_id, current)
    if is_unlocked(user_id):
        _store_decrypted_cache(user_id, current)


def unlock_vault(
    *,
    user_id: str,
    totp_code: str,
    hardware_token: str = "",
    unlock_vault: bool = True,
    unlock_obsidian: bool = True,
) -> dict[str, Any]:
    if not vault_initialized(user_id):
        raise VaultError("Local vault is not initialized.")
    if not verify_totp(user_id, totp_code):
        raise VaultError("Invalid verification code.")
    session = _session_payload(user_id) or {"vault": False, "obsidian": False}
    if unlock_vault:
        session["vault"] = True
    if unlock_obsidian:
        session["obsidian"] = True
    _store_session(user_id, vault=session["vault"], obsidian=session["obsidian"])
    if session["vault"]:
        _store_decrypted_cache(user_id, _decrypt_categories(user_id))
    return {
        "unlocked": True,
        "vault": session["vault"],
        "obsidian": session["obsidian"],
        "expires_in": SESSION_TTL,
        "hardware_bound": bool(hardware_token),
    }


def lock_vault(*, user_id: str) -> None:
    _clear_session(user_id)


def vault_status(user_id: str) -> dict[str, Any]:
    initialized = vault_initialized(user_id)
    session = _session_payload(user_id) or {}
    master_configured = bool(os.environ.get(MASTER_ENV, "").strip())
    return {
        "initialized": initialized,
        "needs_totp_setup": not initialized,
        "vault_unlocked": bool(session.get("vault")),
        "obsidian_unlocked": bool(session.get("obsidian")),
        "master_configured": master_configured,
        "session_ttl_sec": SESSION_TTL,
        "categories": list(SEALED_CATEGORIES),
    }


def is_unlocked(user_id: str) -> bool:
    session = _session_payload(user_id)
    return bool(session and session.get("vault"))


def is_obsidian_unlocked(user_id: str) -> bool:
    session = _session_payload(user_id)
    return bool(session and session.get("obsidian"))


def require_vault_unlocked(user_id: str) -> None:
    if not is_unlocked(user_id):
        raise VaultLockedError("Local vault is locked. Enter your verification code to unlock.")


def require_obsidian_unlocked(user_id: str) -> None:
    if not is_obsidian_unlocked(user_id):
        raise VaultLockedError(
            "Offline vault access is locked. Verify with your authenticator app to continue."
        )


def get_category(user_id: str, category: str) -> dict[str, Any]:
    if category not in SEALED_CATEGORIES:
        return {}
    if not is_unlocked(user_id):
        return {}
    cached = _cached_categories(user_id)
    if cached and isinstance(cached.get(category), dict):
        return cached[category]
    data = _decrypt_categories(user_id)
    section = data.get(category, {})
    return section if isinstance(section, dict) else {}


def get_prompt(user_id: str, name: str) -> str | None:
    prompts = get_category(user_id, "prompts")
    value = prompts.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def get_api_key(user_id: str, name: str) -> str | None:
    keys = get_category(user_id, "api_keys")
    value = keys.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
