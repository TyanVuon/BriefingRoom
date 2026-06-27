#!/usr/bin/env python3
"""Initialize encrypted local vault + TOTP for mail-intelligence (offline setup)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.local_secrets_vault import (  # noqa: E402
    VAULT_DIR,
    init_vault,
    seal_categories,
    totp_provisioning_uri,
    vault_initialized,
)


def _load_prompt_dir(prompt_dir: Path) -> dict[str, str]:
    prompts: dict[str, str] = {}
    if not prompt_dir.is_dir():
        return prompts
    for path in sorted(prompt_dir.glob("*.md")):
        prompts[path.stem] = path.read_text(encoding="utf-8").strip()
    return prompts


def _print_qr(uri: str, out_path: Path | None) -> None:
    try:
        import qrcode
    except ImportError:
        print("\nInstall qrcode for terminal QR: uv add qrcode[pil]")
        print(f"Manual setup URI:\n{uri}\n")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(uri)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    if out_path:
        img = qr.make_image(fill_color="black", back_color="white")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        try:
            out_path.chmod(0o600)
        except OSError:
            pass
        print(f"Saved QR image to {out_path} (outside repo recommended)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize mail-intel local secrets vault + TOTP.")
    parser.add_argument("--user-id", required=True, help="RAGFlow user id")
    parser.add_argument(
        "--prompt-dir",
        default=str(ROOT / "agent" / "prompts" / "local" / "mail_intel"),
        help="Plaintext prompts to seal into vault",
    )
    parser.add_argument(
        "--secrets-file",
        default="",
        help="Optional JSON file with api_keys/connectors categories",
    )
    parser.add_argument(
        "--qr-out",
        default="",
        help="Optional path to save QR PNG (keep outside git)",
    )
    parser.add_argument("--force", action="store_true", help="Re-initialize existing vault")
    args = parser.parse_args()

    if not os.environ.get("MAIL_INTEL_VAULT_MASTER", "").strip():
        print("Set MAIL_INTEL_VAULT_MASTER in your shell (never commit).", file=sys.stderr)
        return 1

    user_id = args.user_id.strip()
    if vault_initialized(user_id) and not args.force:
        print(f"Vault already exists under {VAULT_DIR}. Use --force to recreate.", file=sys.stderr)
        return 1

    categories: dict[str, dict] = {
        "api_keys": {},
        "prompts": _load_prompt_dir(Path(args.prompt_dir)),
        "connectors": {},
        "ragflow_creds": {},
    }
    if args.secrets_file:
        secrets_path = Path(args.secrets_file)
        if secrets_path.is_file():
            extra = json.loads(secrets_path.read_text(encoding="utf-8"))
            if isinstance(extra, dict):
                for key in ("api_keys", "connectors", "ragflow_creds", "prompts"):
                    section = extra.get(key)
                    if isinstance(section, dict):
                        categories[key].update(section)

    secret = init_vault(user_id=user_id, categories=categories)
    if args.force and vault_initialized(user_id):
        # init_vault already sealed categories; skip Redis-dependent re-seal during CLI init
        pass

    uri = totp_provisioning_uri(user_id=user_id, secret=secret)
    print(f"Local vault initialized at {VAULT_DIR}")
    print("Scan this authenticator QR once, then store the secret offline:\n")
    _print_qr(uri, Path(args.qr_out) if args.qr_out else None)
    print("\nNext: unlock via POST /api/v1/privacy/vault/unlock or the explore UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
