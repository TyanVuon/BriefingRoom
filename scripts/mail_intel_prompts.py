#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Load Mail Intelligence Router prompts from local (gitignored) or vault paths only."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "agent" / "prompts" / "mail_intel"
LOCAL_DIR = ROOT / "agent" / "prompts" / "local" / "mail_intel"
SEALED_DIR = ROOT / "agent" / "prompts" / "sealed" / "mail_intel"


def load_prompt(name: str) -> str:
    """Load `{name}.md`; unlocked vault > sealed > local > public example."""
    user_id = os.environ.get("RAGFLOW_USER_ID", "").strip()
    if user_id:
        try:
            from common.local_secrets_vault import get_prompt, is_unlocked

            if is_unlocked(user_id):
                vaulted = get_prompt(user_id, name)
                if vaulted:
                    return vaulted.strip()
        except Exception:
            pass
    hardware_token = os.environ.get("HARDWARE_AUTH_TOKEN", "").strip()
    if hardware_token and user_id:
        try:
            from common.privacy_vault import load_sealed_prompt

            sealed = load_sealed_prompt(name, user_id=user_id, hardware_token=hardware_token)
            if sealed:
                return sealed.strip()
        except Exception:
            pass
    for base in (LOCAL_DIR,):
        path = base / f"{name}.md"
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(
        f"Missing prompt '{name}'. "
        f"Add agent/prompts/local/mail_intel/{name}.md or seal into vault "
        f"(see agent/prompts/mail_intel/README.md)."
    )


def load_optional_prompt(name: str, fallback: str = "") -> str:
    try:
        return load_prompt(name)
    except FileNotFoundError:
        return fallback.strip()
