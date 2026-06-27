#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Tests for Mail Intelligence Router — v2 gate + desk pipeline DSL."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from api.apps.services.canvas_replica_service import CanvasReplicaService

ROOT = Path(__file__).resolve().parents[3]
IMPORT_PATH = ROOT / "agent" / "import" / "mail_intelligence_router.json"
BUILD_SCRIPT = ROOT / "scripts" / "build_mail_intelligence_router.py"
TENANT_ID = os.environ.get("RAGFLOW_TENANT_ID", "")
DEFAULT_LLM = os.environ.get(
    "MAIL_INTEL_LLM_ID",
    "openai/gpt-oss-120b@openai/gpt-oss-120b@OpenAI-API-Compatible",
)

TRUNK = [
    "begin",
    "ImapInbox:Preload30d",
    "Agent:InboxIndexer",
    "Agent:CyberSecGate",
    "Categorize:SectorRouter",
]

BRIEFING_TAIL = [
    "Agent:CareerMinerBrief",
    "Agent:AuctionMinerBrief",
    "Agent:SubscriptionMinerBrief",
    "Agent:NotificationDigestBrief",
    "Agent:FinanceMiner",
    "ObsidianVault:LoadRecent",
    "Agent:BriefingSynth",
    "ObsidianVault:Archive",
    "Message:ChatReply",
]


def _load_build_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_mail_router", BUILD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dsl():
    mod = _load_build_module()
    data = mod.build_dsl()
    errors = mod.validate_dsl(data)
    assert not errors, errors
    return data


class TestMailRouterDslStructure:
    def test_no_retrieval_nodes(self, dsl):
        assert not any(k.startswith("Retrieval:") for k in dsl["components"])

    def test_trunk_chain(self, dsl):
        comps = dsl["components"]
        for i in range(len(TRUNK) - 1):
            assert comps[TRUNK[i]]["downstream"] == [TRUNK[i + 1]]

    def test_categorize_has_five_sectors(self, dsl):
        cat = dsl["components"]["Categorize:SectorRouter"]["obj"]["params"]["category_description"]
        assert set(cat) == {"security", "career", "commerce", "platform", "briefing"}

    def test_only_gpt_oss_llm(self, dsl):
        for nid, comp in dsl["components"].items():
            params = comp["obj"]["params"]
            if comp["obj"]["component_name"] in ("Agent", "Categorize"):
                assert params["llm_id"] == DEFAULT_LLM

    def test_indexer_references_inbox(self, dsl):
        content = dsl["components"]["Agent:InboxIndexer"]["obj"]["params"]["prompts"][0]["content"]
        assert "{ImapInbox:Preload30d@inbox_context}" in content

    def test_gate_references_manifest(self, dsl):
        content = dsl["components"]["Agent:CyberSecGate"]["obj"]["params"]["prompts"][0]["content"]
        assert "{Agent:InboxIndexer@content}" in content

    def test_categorize_has_items_and_edges(self, dsl):
        cat = dsl["components"]["Categorize:SectorRouter"]["obj"]["params"]
        assert len(cat.get("items", [])) == 5
        assert all(i.get("uuid") for i in cat["items"])
        edges = dsl["graph"]["edges"]
        cat_out = [e for e in edges if e["source"] == "Categorize:SectorRouter"]
        assert len(cat_out) == 5

    def test_career_verifier_tavily_tool(self, dsl):
        tool_edges = [e for e in dsl["graph"]["edges"] if e.get("sourceHandle") == "tool"]
        assert len(tool_edges) == 1
        verifier = dsl["components"]["Agent:CareerVerifier"]["obj"]["params"]["tools"][0]
        assert verifier["component_name"] == "TavilySearch"
        assert verifier["id"] == "Tool:CareerVerifierTavily"

    def test_briefing_synth_merges_desks(self, dsl):
        content = dsl["components"]["Agent:BriefingSynth"]["obj"]["params"]["prompts"][0]["content"]
        assert "{Agent:CyberSecGate@content}" in content
        assert "{ObsidianVault:LoadRecent@vault_context}" in content
        assert "{Agent:CareerMinerBrief@content}" in content
        assert "{Agent:AuctionMinerBrief@content}" in content

    def test_obsidian_on_pipeline(self, dsl):
        assert "ObsidianVault:LoadRecent" in dsl["components"]
        assert "ObsidianVault:Archive" in dsl["components"]
        for save_id in (
            "ObsidianVault:SaveSecurity",
            "ObsidianVault:SaveCareer",
            "ObsidianVault:SaveCommerce",
            "ObsidianVault:SavePlatform",
        ):
            assert save_id in dsl["components"]
        comps = dsl["components"]
        for i in range(len(BRIEFING_TAIL) - 1):
            assert BRIEFING_TAIL[i + 1] in comps[BRIEFING_TAIL[i]]["downstream"]

    def test_branch_obsidian_saves(self, dsl):
        comps = dsl["components"]
        assert comps["Agent:CyberSecFocus"]["downstream"] == ["ObsidianVault:SaveSecurity"]
        assert comps["Agent:CareerVerifier"]["downstream"] == ["ObsidianVault:SaveCareer"]
        assert comps["Agent:CommerceMerge"]["downstream"] == ["ObsidianVault:SaveCommerce"]
        assert comps["Agent:NotificationDigest"]["downstream"] == ["ObsidianVault:SavePlatform"]

    def test_career_and_briefing_miners_separate(self, dsl):
        comps = dsl["components"]
        assert comps["Agent:CareerMiner"]["downstream"] == ["Agent:CareerVerifier"]
        assert comps["Agent:CareerMinerBrief"]["downstream"] == ["Agent:AuctionMinerBrief"]

    def test_ephemeral_sessions_enabled(self, dsl):
        privacy = dsl["globals"]["privacy"]
        assert privacy["ephemeral_sessions"] is True
        assert privacy["hardware_auth_required"] is True
        assert privacy["zero_trust"] is True
        assert privacy["local_vault_required"] is True
        assert privacy["obsidian_2fa"] is True

    def test_messages_do_not_stream(self, dsl):
        for msg_id in (
            "Message:ChatReply",
            "Message:SecurityReply",
            "Message:CareerReply",
            "Message:CommerceReply",
            "Message:PlatformReply",
        ):
            assert dsl["components"][msg_id]["obj"]["params"]["stream"] is False

    def test_message_outputs(self, dsl):
        content = dsl["components"]["Message:ChatReply"]["obj"]["params"]["content"]
        assert "{Agent:BriefingSynth@content}" in content
        assert "{ObsidianVault:Archive@saved_path}" in content[1]

    def test_inbox_fetch_cap(self, dsl):
        params = dsl["components"]["ImapInbox:Preload30d"]["obj"]["params"]
        assert params["max_messages"] >= 200

    def test_runtime_fields_and_normalize(self, dsl):
        for key in ("path", "history", "retrieval", "variables"):
            assert key in dsl
        assert CanvasReplicaService.normalize_dsl(dsl)

    def test_default_build_uses_vault_stubs(self, dsl):
        sys_prompt = dsl["components"]["Agent:InboxIndexer"]["obj"]["params"]["sys_prompt"]
        assert sys_prompt.startswith("[PROMPT:inbox_indexer")
        prologue = dsl["components"]["begin"]["obj"]["params"]["prologue"]
        assert "skeleton" in prologue.lower() or prologue.startswith("[PROMPT:")


class TestMailRouterCanvasLoad:
    @pytest.mark.skipif(not TENANT_ID, reason="Set RAGFLOW_TENANT_ID for canvas load test")
    def test_canvas_loads(self, dsl):
        from agent.canvas import Canvas

        canvas = Canvas(json.dumps(dsl), tenant_id=TENANT_ID)
        for nid in TRUNK:
            assert nid in canvas.components
        assert canvas.get_prologue()


class TestImapInboxFetch:
    """Live fetch — requires RAGFLOW_TENANT_ID in environment."""

    @pytest.mark.skipif(not TENANT_ID, reason="Set RAGFLOW_TENANT_ID for live IMAP tests")
    def test_fetch_inbox_returns_mail_text(self):
        from common import settings

        settings.init_settings()
        from agent.tools.imap_inbox import fetch_imap_inbox

        text = fetch_imap_inbox(TENANT_ID, days=30, max_messages=5)
        assert isinstance(text, str)
        assert len(text) > 100
        assert "Subject:" in text or "Subject" in text
        assert "Embedding request failed" not in text

    @pytest.mark.skipif(not TENANT_ID, reason="Set RAGFLOW_TENANT_ID for live IMAP tests")
    def test_imap_component_invoke(self, dsl):
        from common import settings

        settings.init_settings()
        from agent.canvas import Canvas

        canvas = Canvas(json.dumps(dsl), tenant_id=TENANT_ID)
        canvas.reset()
        canvas.globals["sys.query"] = "what is new in my inbox"
        canvas.path = ["begin", "ImapInbox:Preload30d"]
        obj = canvas.get_component_obj("ImapInbox:Preload30d")
        obj.invoke()
        assert not obj.error(), obj.error()
        ctx = obj.output("inbox_context")
        assert ctx and ("Subject:" in ctx or "INBOX" in ctx)
