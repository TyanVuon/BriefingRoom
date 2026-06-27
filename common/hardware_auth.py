#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""WebAuthn / FIDO2 hardware authentication for zero-trust mail intelligence."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt

from common import settings
from common.crypto_utils import AES256CBC
from rag.utils.redis_conn import REDIS_CONN

LOGGER = logging.getLogger(__name__)

try:
    from webauthn import (
        generate_authentication_options,
        generate_registration_options,
        verify_authentication_response,
        verify_registration_response,
    )
    from webauthn.helpers.cose import COSEAlgorithmIdentifier
    from webauthn.helpers.options_to_json import options_to_json
    from webauthn.helpers.structs import (
        AuthenticatorAttachment,
        AuthenticatorSelectionCriteria,
        AuthenticatorTransport,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    _WEBAUTHN_AVAILABLE = True
except ImportError:  # pragma: no cover - optional at import time
    options_to_json = None  # type: ignore[assignment,misc]
    AuthenticatorAttachment = None  # type: ignore[assignment,misc]
    AuthenticatorTransport = None  # type: ignore[assignment,misc]
    _WEBAUTHN_AVAILABLE = False

RP_ID = os.environ.get("MAIL_INTEL_RP_ID", "localhost").strip() or "localhost"
RP_NAME = os.environ.get("MAIL_INTEL_RP_NAME", "RAGFlow Mail Intel").strip() or "RAGFlow Mail Intel"
RP_ORIGIN = os.environ.get("MAIL_INTEL_RP_ORIGIN", "http://localhost:9222").strip() or "http://localhost:9222"
HARDWARE_TOKEN_TTL = int(
    os.environ.get(
        "MAIL_INTEL_HARDWARE_TOKEN_TTL_SEC",
        os.environ.get("MAIL_INTEL_HARDWARE_TOKEN_TTL", "86400"),
    )
)
STORE_DIR = Path(os.environ.get("MAIL_INTEL_HARDWARE_STORE", "config/hardware_auth"))
STORE_KEY_ENV = "MAIL_INTEL_HARDWARE_STORE_KEY"
CHALLENGE_TTL = 300
_STORE_CIPHER_SALT = b"mail-intel-hardware-auth-store-v1"


@dataclass
class HardwareCredential:
    credential_id: str
    public_key: str
    sign_count: int
    transports: list[str]


def _require_webauthn() -> None:
    if not _WEBAUTHN_AVAILABLE:
        raise RuntimeError(
            "WebAuthn support is not installed. Run: uv add webauthn"
        )


def _options_to_dict(options: Any) -> dict[str, Any]:
    """Serialize py_webauthn options for @simplewebauthn/browser."""
    _require_webauthn()
    return json.loads(options_to_json(options))


def _cross_platform_transports() -> list[Any]:
    return [AuthenticatorTransport.USB, AuthenticatorTransport.NFC]


def _transport_enums(transports: list[Any] | None) -> list[Any]:
    """Coerce persisted JSON transport strings to py_webauthn enum values."""
    if not transports:
        return _cross_platform_transports()
    out: list[Any] = []
    for item in transports:
        if isinstance(item, AuthenticatorTransport):
            out.append(item)
            continue
        if isinstance(item, str):
            normalized = item.strip().lower()
            if not normalized:
                continue
            try:
                out.append(AuthenticatorTransport(normalized))
            except ValueError:
                LOGGER.debug("Ignoring unknown authenticator transport: %s", item)
    return out or _cross_platform_transports()


def _transport_value_list(transports: list[Any] | None) -> list[str]:
    """Normalize transports for JSON persistence."""
    if not transports:
        return [t.value for t in _cross_platform_transports()]
    out: list[str] = []
    for item in transports:
        if isinstance(item, AuthenticatorTransport):
            out.append(item.value)
        elif isinstance(item, str) and item.strip():
            out.append(item.strip().lower())
    return out or [t.value for t in _cross_platform_transports()]


def _store_path(user_id: str) -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]
    return STORE_DIR / f"{digest}.json"


def _store_cipher_key() -> bytes:
    raw = os.environ.get(STORE_KEY_ENV, "").strip()
    if not raw:
        raw = settings.get_secret_key()
        LOGGER.warning(
            "%s not set; deriving store key from service secret (set in production)",
            STORE_KEY_ENV,
        )
    return hashlib.sha256(_STORE_CIPHER_SALT + raw.encode("utf-8")).digest()


def _encrypt_store_payload(payload: dict[str, Any]) -> dict[str, Any]:
    crypto = AES256CBC(key=_store_cipher_key())
    blob = base64.b64encode(
        crypto.encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    ).decode("ascii")
    return {"v": 1, "encrypted": True, "blob": blob}


def _decrypt_store_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    blob = envelope.get("blob")
    if not blob:
        raise ValueError("Encrypted hardware auth store is missing ciphertext.")
    crypto = AES256CBC(key=_store_cipher_key())
    raw = crypto.decrypt(base64.b64decode(blob))
    return json.loads(raw.decode("utf-8"))


def _load_store(user_id: str) -> dict[str, Any]:
    path = _store_path(user_id)
    if not path.is_file():
        return {"credentials": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"credentials": [], "_store_corrupted": True}
    if raw.get("encrypted") and raw.get("blob"):
        try:
            return _decrypt_store_payload(raw)
        except Exception as exc:
            LOGGER.error("Failed to decrypt hardware auth store for user: %s", exc)
            return {"credentials": [], "_store_corrupted": True}
    if isinstance(raw.get("credentials"), list):
        return raw
    return {"credentials": [], "_store_corrupted": True}


def store_corrupted(user_id: str) -> bool:
    """True when an on-disk enrollment exists but cannot be read (e.g. key rotation)."""
    return bool(_load_store(user_id).get("_store_corrupted"))


def _save_store(user_id: str, payload: dict[str, Any]) -> None:
    path = _store_path(user_id)
    envelope = _encrypt_store_payload(payload)
    path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _challenge_key(user_id: str, purpose: str) -> str:
    return f"mail-intel:webauthn:{purpose}:{user_id}"


def _store_challenge(user_id: str, purpose: str, challenge: str) -> None:
    REDIS_CONN.set(_challenge_key(user_id, purpose), challenge, CHALLENGE_TTL)


def _pop_challenge(user_id: str, purpose: str) -> str | None:
    key = _challenge_key(user_id, purpose)
    challenge = REDIS_CONN.get(key)
    if challenge:
        REDIS_CONN.delete(key)
    return challenge


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def clear_store(user_id: str) -> None:
    """Remove persisted enrollment (e.g. after store-key rotation)."""
    path = _store_path(user_id)
    if path.is_file():
        path.unlink()


def list_credentials(user_id: str) -> list[HardwareCredential]:
    store = _load_store(user_id)
    out: list[HardwareCredential] = []
    for item in store.get("credentials", []):
        out.append(
            HardwareCredential(
                credential_id=item["credential_id"],
                public_key=item["public_key"],
                sign_count=int(item.get("sign_count", 0)),
                transports=list(item.get("transports") or []),
            )
        )
    return out


def has_registered_credentials(user_id: str) -> bool:
    return bool(list_credentials(user_id))


def registration_options(user_id: str, *, username: str) -> dict[str, Any]:
    _require_webauthn()
    existing = list_credentials(user_id)
    exclude = [
        PublicKeyCredentialDescriptor(id=_b64decode(c.credential_id))
        for c in existing
    ]
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=user_id.encode("utf-8"),
        user_name=username or user_id,
        user_display_name=username or user_id,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )
    _store_challenge(user_id, "register", _b64(options.challenge))
    return _options_to_dict(options)


def verify_registration(user_id: str, credential: dict[str, Any]) -> None:
    _require_webauthn()
    expected = _pop_challenge(user_id, "register")
    if not expected:
        raise ValueError(
            "Module enrollment session expired. Reconnect your hardware module and try again."
        )
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=_b64decode(expected),
        expected_rp_id=RP_ID,
        expected_origin=RP_ORIGIN,
        require_user_verification=True,
    )
    store = _load_store(user_id)
    creds = store.setdefault("credentials", [])
    cred_id = _b64(verification.credential_id)
    creds = [c for c in creds if c.get("credential_id") != cred_id]
    creds.append(
        {
            "credential_id": cred_id,
            "public_key": _b64(verification.credential_public_key),
            "sign_count": verification.sign_count,
            "transports": _transport_value_list(credential.get("transports")),
        }
    )
    store["credentials"] = creds
    _save_store(user_id, store)


def authentication_options(user_id: str) -> dict[str, Any]:
    _require_webauthn()
    creds = list_credentials(user_id)
    if not creds:
        raise ValueError("No hardware module enrolled. Complete initial provisioning first.")
    allow = [
        PublicKeyCredentialDescriptor(
            id=_b64decode(c.credential_id),
            transports=_transport_enums(c.transports),
        )
        for c in creds
    ]
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _store_challenge(user_id, "authenticate", _b64(options.challenge))
    return _options_to_dict(options)


def issue_hardware_token(user_id: str, credential: dict[str, Any]) -> str:
    _require_webauthn()
    expected = _pop_challenge(user_id, "authenticate")
    if not expected:
        raise ValueError(
            "Module verification session expired. Reconnect your hardware module and try again."
        )
    creds = list_credentials(user_id)
    by_id = {c.credential_id: c for c in creds}
    raw_id = credential.get("rawId") or credential.get("id")
    if not raw_id:
        raise ValueError("Module verification payload is incomplete.")
    if isinstance(raw_id, str):
        cred_id = raw_id
        credential_id_bytes = _b64decode(raw_id)
    else:
        credential_id_bytes = bytes(raw_id)
        cred_id = _b64(credential_id_bytes)
    stored = by_id.get(cred_id)
    if not stored:
        raise ValueError("Unknown hardware module. Complete enrollment first.")
    verification = verify_authentication_response(
        credential=credential,
        expected_challenge=_b64decode(expected),
        expected_rp_id=RP_ID,
        expected_origin=RP_ORIGIN,
        credential_public_key=_b64decode(stored.public_key),
        credential_current_sign_count=stored.sign_count,
        require_user_verification=True,
    )
    store = _load_store(user_id)
    for item in store.get("credentials", []):
        if item.get("credential_id") == cred_id:
            item["sign_count"] = verification.new_sign_count
    _save_store(user_id, store)

    now = int(time.time())
    payload = {
        "sub": user_id,
        "hw": True,
        "iat": now,
        "exp": now + HARDWARE_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.get_secret_key(), algorithm="HS256")


def verify_hardware_token(token: str | None, user_id: str) -> bool:
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.get_secret_key(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return False
    return payload.get("sub") == user_id and payload.get("hw") is True
