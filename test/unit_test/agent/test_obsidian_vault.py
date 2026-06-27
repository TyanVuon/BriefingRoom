#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.obsidian_vault_store import (
    has_saved_notes,
    load_context_if_relevant,
    load_recent,
    save_briefing,
    search_notes,
)


@pytest.fixture
def vault_tmp(tmp_path: Path) -> Path:
    intel = tmp_path / "Mail Intel"
    intel.mkdir()
    return tmp_path


def test_save_and_load_briefing(vault_tmp: Path):
    rel = save_briefing(
        vault_path=str(vault_tmp),
        subfolder="Mail Intel",
        content="## Threat board\nT3 test",
        user_query="comprehensive advice",
    )
    assert rel.startswith("Mail Intel/")
    assert (vault_tmp / rel).is_file()
    assert has_saved_notes(str(vault_tmp), "Mail Intel")
    ctx = load_recent(vault_path=str(vault_tmp), subfolder="Mail Intel", max_notes=3)
    assert "Threat board" in ctx


def test_save_includes_user_query(vault_tmp: Path):
    rel = save_briefing(
        vault_path=str(vault_tmp),
        subfolder="Mail Intel",
        content="## Threat board\nT3 test",
        user_query="search deeper with tavily on life sector",
    )
    text = (vault_tmp / rel).read_text(encoding="utf-8")
    assert "## User request" in text
    assert "search deeper with tavily on life sector" in text


def test_load_empty_when_no_saves(vault_tmp: Path):
    assert not has_saved_notes(str(vault_tmp), "Mail Intel")
    assert load_recent(vault_path=str(vault_tmp), subfolder="Mail Intel") == ""
    assert load_context_if_relevant(
        vault_path=str(vault_tmp),
        subfolder="Mail Intel",
        user_query="comprehensive advice",
    ) == ""


def test_search_notes(vault_tmp: Path):
    save_briefing(
        vault_path=str(vault_tmp),
        subfolder="Mail Intel",
        content="Example Corp fintech role Tokyo",
        user_query="jobs",
    )
    hits = search_notes(
        vault_path=str(vault_tmp),
        subfolder="Mail Intel",
        query="Example Corp",
        max_notes=3,
    )
    assert "Example Corp" in hits


def test_obsidian_component_registered():
    from agent.component import component_class

    assert component_class("ObsidianVaultParam")
    assert component_class("ObsidianVault")
