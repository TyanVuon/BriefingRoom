#!/usr/bin/env python3
"""Copy mail-intel prompt templates into gitignored local/ for customization."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "agent" / "prompts" / "mail_intel"
LOCAL = ROOT / "agent" / "prompts" / "local" / "mail_intel"


def main() -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in PUBLIC.glob("*.md"):
        dest = LOCAL / src.name
        if dest.exists():
            continue
        shutil.copy2(src, dest)
        copied += 1
        print(f"Created {dest.relative_to(ROOT)}")
    if copied == 0:
        print(f"Local prompts already present under {LOCAL.relative_to(ROOT)}")
    else:
        print(f"Copied {copied} prompt file(s). Edit files under agent/prompts/local/mail_intel/")


if __name__ == "__main__":
    main()
