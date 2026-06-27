#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Strip leaked chain-of-thought from user-facing LLM output."""

from __future__ import annotations

import re

_THINKING_BLOCK = re.compile(
    r"<think>.*?</think>",
    re.DOTALL | re.IGNORECASE,
)
_THINKING_OPEN = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)
_GENERIC_THINK = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)

_META_LINE = re.compile(
    r"^(?:"
    r"We need to\b.*|"
    r"Return format with\b.*|"
    r"Let's craft\.?\s*$|"
    r"We'll maybe\b.*|"
    r"We should\b.*|"
    r"I'll (?:craft|produce|summarize)\b.*|"
    r"Provide (?:concise|sources)\b.*"
    r")",
    re.IGNORECASE,
)

_OUTPUT_START = re.compile(
    r"(?:"
    r"^\s*#{1,3}\s+\S"  # markdown heading
    r"|^\s*\*\*Answer\*\*"
    r"|^\s*Answer\s*$"
    r"|Let's craft\.\s*(?=#{1,3}\s|\*\*Answer\*\*|Answer\s*$)"
    r")",
    re.MULTILINE | re.IGNORECASE,
)


def sanitize_user_facing_llm_output(text: str) -> str:
    """Remove thinking blocks and planning preamble; keep the formatted answer."""
    if not text or not text.strip():
        return text or ""

    out = text.strip()
    out = _THINKING_BLOCK.sub("", out)
    out = _GENERIC_THINK.sub("", out)
    out = _THINKING_OPEN.sub("", out)

    # gpt-oss often emits "Let's craft.Answer" with no newline before Answer.
    out = re.sub(r"Let's craft\.\s*(?=Answer\b)", "", out, flags=re.IGNORECASE)

    match = _OUTPUT_START.search(out)
    if match:
        out = out[match.start() :]
        if out.lower().startswith("answer"):
            out = re.sub(r"^Answer\s*\n?", "", out, count=1, flags=re.IGNORECASE)

    lines = out.splitlines()
    cleaned: list[str] = []
    started = False
    for line in lines:
        if not started:
            if _META_LINE.match(line.strip()):
                continue
            if line.strip().startswith("## ") or line.strip().startswith("# "):
                started = True
            elif line.strip().lower() in {"answer", "sources", "next steps"}:
                started = True
            elif line.strip() and not _META_LINE.match(line.strip()):
                started = True
            else:
                continue
        cleaned.append(line)

    out = "\n".join(cleaned).strip() if cleaned else out.strip()
    return out.strip()
