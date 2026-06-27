#!/usr/bin/env python3
"""Seal mail-intelligence secrets/prompts with hardware-auth-derived encryption."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.privacy_vault import seal_blob  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal local mail-intel files for zero-trust storage.")
    parser.add_argument("--user-id", required=True, help="RAGFlow user id")
    parser.add_argument(
        "--hardware-token",
        default=os.environ.get("HARDWARE_AUTH_TOKEN", ""),
        help="Short-lived token from POST /api/v1/privacy/webauthn/authenticate/verify",
    )
    parser.add_argument(
        "--prompt-dir",
        default=str(ROOT / "agent" / "prompts" / "local" / "mail_intel"),
        help="Directory of plaintext prompt overrides to seal",
    )
    args = parser.parse_args()
    if not args.hardware_token:
        print("Set HARDWARE_AUTH_TOKEN after touching your security key.", file=sys.stderr)
        return 1

    prompt_dir = Path(args.prompt_dir)
    if not prompt_dir.is_dir():
        print(f"Prompt directory not found: {prompt_dir}", file=sys.stderr)
        return 1

    sealed = 0
    for path in sorted(prompt_dir.glob("*.md")):
        seal_blob(
            user_id=args.user_id,
            hardware_token=args.hardware_token,
            name=path.stem,
            plaintext=path.read_text(encoding="utf-8"),
        )
        sealed += 1
        print(f"Sealed {path.name}")

    print(f"Done. Sealed {sealed} prompt(s) under agent/prompts/sealed/mail_intel/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
