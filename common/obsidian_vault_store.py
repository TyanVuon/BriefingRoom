#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Local Obsidian vault read/write for mail-intelligence briefings (no API)."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)

DEFAULT_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", "")
DEFAULT_SUBFOLDER = os.environ.get("OBSIDIAN_MAIL_INTEL_FOLDER", "Mail Intel")
INDEX_NAME = "_ragflow_index.json"

RECALL_HINTS = re.compile(
    r"previous|last time|recall|continue|earlier|before|again|前回|以前|続き",
    re.IGNORECASE,
)


def _resolve_vault_path(vault_path: str) -> Path:
    resolved = (vault_path or DEFAULT_VAULT or "").strip()
    if not resolved:
        raise FileNotFoundError(
            "Obsidian vault not configured. Set OBSIDIAN_VAULT_PATH in your environment."
        )
    return Path(os.path.expanduser(resolved))


def _vault_root(vault_path: str) -> Path:
    root = _resolve_vault_path(vault_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Obsidian vault not found: {root}")
    return root


def _intel_dir(vault_path: str, subfolder: str, *, create: bool = False) -> Path:
    root = _resolve_vault_path(vault_path)
    d = root / subfolder
    if create:
        d.mkdir(parents=True, exist_ok=True)
        return d
    if not root.is_dir():
        raise FileNotFoundError(f"Obsidian vault not found: {root}")
    return d


def _slug(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s.strip())
    return (s[:limit] or "briefing").lower()


def _load_index(intel_dir: Path) -> dict:
    path = intel_dir / INDEX_NAME
    if not path.is_file():
        return {"entries": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"entries": []}


def _save_index(intel_dir: Path, index: dict) -> None:
    path = intel_dir / INDEX_NAME
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def has_saved_notes(vault_path: str, subfolder: str) -> bool:
    try:
        intel_dir = _intel_dir(vault_path, subfolder)
    except FileNotFoundError:
        return False
    if _load_index(intel_dir).get("entries"):
        return True
    return any(intel_dir.glob("*.md"))


def save_briefing(
    *,
    vault_path: str,
    subfolder: str,
    content: str,
    user_query: str = "",
    title_prefix: str = "inbox-briefing",
) -> str:
    if not content or not content.strip():
        raise ValueError("Nothing to save — briefing content is empty.")

    intel_dir = _intel_dir(vault_path, subfolder, create=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d")
    slug = _slug(user_query or title_prefix)
    filename = f"{stamp}-{slug}.md"
    out_path = intel_dir / filename
    if out_path.exists():
        filename = f"{stamp}-{slug}-{now.strftime('%H%M%S')}.md"
        out_path = intel_dir / filename

    frontmatter = (
        "---\n"
        f"date: {now.isoformat()}\n"
        f"query: {json.dumps(user_query or '', ensure_ascii=False)}\n"
        "agent: mail-intelligence-router\n"
        "tags:\n  - mail-intel\n  - briefing\n"
        "---\n\n"
    )
    body = content.strip()
    if user_query and user_query.strip():
        body = f"## User request\n\n{user_query.strip()}\n\n---\n\n{body}"
    out_path.write_text(frontmatter + body + "\n", encoding="utf-8")

    index = _load_index(intel_dir)
    rel = f"{subfolder}/{filename}"
    index["entries"] = [
        {
            "path": rel,
            "date": now.isoformat(),
            "query": user_query or "",
            "filename": filename,
        },
        *index.get("entries", []),
    ][:200]
    _save_index(intel_dir, index)

    LOGGER.info("ObsidianVault saved note %s", rel)
    return rel


def load_recent(
    *,
    vault_path: str,
    subfolder: str,
    max_notes: int = 1,
) -> str:
    try:
        intel_dir = _intel_dir(vault_path, subfolder)
    except FileNotFoundError:
        return ""

    index = _load_index(intel_dir)
    entries = index.get("entries", [])[:max_notes]
    if not entries:
        md_files = sorted(intel_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        entries = [{"path": f"{subfolder}/{p.name}", "filename": p.name} for p in md_files[:max_notes]]

    if not entries:
        return ""

    root = _vault_root(vault_path)
    blocks: list[str] = []
    for entry in entries:
        rel = entry.get("path") or ""
        path = root / rel if rel else intel_dir / entry.get("filename", "")
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        blocks.append(f"### {path.name}\n{text[:4000]}")

    if not blocks:
        return ""

    header = f"=== PRIOR BRIEFINGS ({subfolder}, {len(blocks)} note(s)) ==="
    return header + "\n\n---\n\n".join(blocks)


def search_notes(
    *,
    vault_path: str,
    subfolder: str,
    query: str,
    max_notes: int = 3,
) -> str:
    try:
        intel_dir = _intel_dir(vault_path, subfolder)
    except FileNotFoundError:
        return ""

    terms = [t.lower() for t in re.split(r"\s+", query.strip()) if len(t) > 2]
    if not terms:
        return load_recent(vault_path=vault_path, subfolder=subfolder, max_notes=max_notes)

    hits: list[tuple[float, Path]] = []
    for path in intel_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        score = sum(text.count(t) for t in terms)
        if score > 0:
            hits.append((score, path))

    hits.sort(key=lambda x: x[0], reverse=True)
    if not hits:
        return ""

    blocks = []
    for _, path in hits[:max_notes]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        blocks.append(f"### {path.name}\n{text[:3500]}")
    return f"=== PRIOR BRIEFINGS (search: {query[:80]}) ===\n\n" + "\n\n---\n\n".join(blocks)


def load_context_if_relevant(
    *,
    vault_path: str,
    subfolder: str,
    user_query: str,
    max_notes: int = 1,
) -> str:
    """Return prior note text only when vault has saves; prefer search on recall-style queries."""
    if not has_saved_notes(vault_path, subfolder):
        return ""
    if RECALL_HINTS.search(user_query or ""):
        ctx = search_notes(
            vault_path=vault_path,
            subfolder=subfolder,
            query=user_query,
            max_notes=max_notes,
        )
        if ctx:
            return ctx
    return load_recent(vault_path=vault_path, subfolder=subfolder, max_notes=max_notes)
