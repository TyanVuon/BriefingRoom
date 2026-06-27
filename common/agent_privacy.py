#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Helpers for privacy-oriented agent DSL settings."""

from __future__ import annotations

import json
from typing import Any


def _coerce_dsl(dsl: Any) -> dict | None:
    if dsl is None:
        return None
    if isinstance(dsl, dict):
        return dsl
    if isinstance(dsl, str):
        try:
            parsed = json.loads(dsl)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def ephemeral_sessions_enabled(dsl: Any) -> bool:
    """Return True when agent DSL opts into delete-after-run session storage."""
    data = _coerce_dsl(dsl)
    if not data:
        return False
    privacy = (data.get("globals") or {}).get("privacy") or {}
    if isinstance(privacy, dict):
        return bool(privacy.get("ephemeral_sessions"))
    return False


def hardware_auth_required(dsl: Any) -> bool:
    """Return True when agent DSL requires FIDO2/WebAuthn before use."""
    data = _coerce_dsl(dsl)
    if not data:
        return False
    privacy = (data.get("globals") or {}).get("privacy") or {}
    if isinstance(privacy, dict):
        return bool(privacy.get("hardware_auth_required"))
    return False


def zero_trust_enabled(dsl: Any) -> bool:
    data = _coerce_dsl(dsl)
    if not data:
        return False
    privacy = (data.get("globals") or {}).get("privacy") or {}
    if isinstance(privacy, dict):
        return bool(privacy.get("zero_trust"))
    return False


def local_vault_required(dsl: Any) -> bool:
    """Return True when agent DSL requires local vault unlock (zero-trust)."""
    return zero_trust_enabled(dsl)


def obsidian_2fa_required(dsl: Any) -> bool:
    data = _coerce_dsl(dsl)
    if not data:
        return False
    privacy = (data.get("globals") or {}).get("privacy") or {}
    if isinstance(privacy, dict):
        return bool(privacy.get("obsidian_2fa", privacy.get("zero_trust")))
    return False


def privacy_policy(dsl: Any) -> dict[str, bool]:
    data = _coerce_dsl(dsl) or {}
    privacy = (data.get("globals") or {}).get("privacy") or {}
    if not isinstance(privacy, dict):
        privacy = {}
    return {
        "ephemeral_sessions": bool(privacy.get("ephemeral_sessions")),
        "hardware_auth_required": bool(privacy.get("hardware_auth_required")),
        "zero_trust": bool(privacy.get("zero_trust")),
        "local_vault_required": bool(privacy.get("local_vault_required", privacy.get("zero_trust"))),
        "obsidian_2fa": bool(privacy.get("obsidian_2fa", privacy.get("zero_trust"))),
    }
