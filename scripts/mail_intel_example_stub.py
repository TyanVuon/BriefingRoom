#!/usr/bin/env python3
"""Generate git-safe shape stubs for agent/prompts/mail_intel/*.example.md."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / "agent" / "prompts" / "mail_intel"


def shape_stub(name: str) -> str:
    return (
        f"# Prompt shape: {name} (local-only)\n\n"
        "Structural reference only — no operational content.\n\n"
        f"Copy to `agent/prompts/local/mail_intel/{name}.md` and seal into vault.\n\n"
        "Expected sections: Role | Hard rules | Input | Output\n\n"
        f"Runtime: [PROMPT:{name} — inject from local vault at deploy]\n"
    )


def write_all_stubs() -> None:
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(EXAMPLE_DIR.glob("*.example.md")):
        stem = path.name.removesuffix(".example.md")
        if stem == "no_thinking":
            path.write_text(
                "# no_thinking (local-only)\n\n"
                "Optional suffix appended to agent system prompts. Seal into vault.\n",
                encoding="utf-8",
            )
        elif stem == "begin_prologue":
            path.write_text(
                "# Begin prologue (local-only)\n\n"
                "User-facing greeting and menu options for the mail concierge.\n"
                "Seal into vault as `begin_prologue`.\n",
                encoding="utf-8",
            )
        else:
            path.write_text(shape_stub(stem), encoding="utf-8")


if __name__ == "__main__":
    write_all_stubs()
    print(f"Wrote shape stubs under {EXAMPLE_DIR}")
