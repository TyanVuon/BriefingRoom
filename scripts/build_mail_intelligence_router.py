#!/usr/bin/env python3
"""Build, validate, and deploy Mail Intelligence Router (zero-trust multi-sector pipeline)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_PATH = ROOT / "agent" / "import" / "mail_intelligence_router.json"
# Resolved at runtime by ObsidianVault / obsidian_vault_store from OBSIDIAN_VAULT_PATH
DEFAULT_VAULT = ""
OBSIDIAN_INTEL_FOLDER = os.environ.get("OBSIDIAN_MAIL_INTEL_FOLDER", "Mail Intel")
DEFAULT_AGENT_ID = os.environ.get("MAIL_INTEL_AGENT_ID", "")
DEFAULT_LLM_ID = os.environ.get(
    "MAIL_INTEL_LLM_ID",
    "openai/gpt-oss-120b@openai/gpt-oss-120b@OpenAI-API-Compatible",
)

LLM_BASE = {
    "frequencyPenaltyEnabled": False,
    "frequency_penalty": 0.7,
    "maxTokensEnabled": False,
    "presencePenaltyEnabled": False,
    "presence_penalty": 0.4,
    "temperatureEnabled": False,
    "topPEnabled": False,
    "top_p": 0.3,
    "llm_id": DEFAULT_LLM_ID,
}

INBOX_REF = "{ImapInbox:Preload30d@inbox_context}"
MANIFEST_REF = "{Agent:InboxIndexer@content}"
GATE_REF = "{Agent:CyberSecGate@content}"


def _load_prompt_module():
    import importlib.util

    path = ROOT / "scripts" / "mail_intel_prompts.py"
    spec = importlib.util.spec_from_file_location("mail_intel_prompts", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_PROMPTS = _load_prompt_module()
FULL_PROMPTS = "--full-prompts" in sys.argv
INJECT_FROM_VAULT = "--inject-from-vault" in sys.argv
# Git-safe default: stub prompts unless operator opts into local files or vault inject.
SKELETON_MODE = "--skeleton" in sys.argv or (not FULL_PROMPTS and not INJECT_FROM_VAULT)


def _prompt(name: str) -> str:
    if INJECT_FROM_VAULT:
        user_id = os.environ.get("RAGFLOW_USER_ID", "").strip()
        if user_id:
            try:
                from common.local_secrets_vault import get_prompt, is_unlocked

                if is_unlocked(user_id):
                    vaulted = get_prompt(user_id, name)
                    if vaulted:
                        no_think = get_prompt(user_id, "no_thinking") or _PROMPTS.load_optional_prompt(
                            "no_thinking", ""
                        )
                        return vaulted.replace("{{NO_THINKING}}", no_think)
            except Exception as exc:
                print(f"Vault inject warning for {name}: {exc}", file=sys.stderr)
    if SKELETON_MODE:
        from common.vault_runtime import stub_prompt

        return stub_prompt(name)
    text = _PROMPTS.load_prompt(name)
    no_think = _PROMPTS.load_prompt("no_thinking")
    return text.replace("{{NO_THINKING}}", no_think)


def _begin_prologue() -> str:
    if INJECT_FROM_VAULT:
        user_id = os.environ.get("RAGFLOW_USER_ID", "").strip()
        if user_id:
            try:
                from common.local_secrets_vault import get_prompt, is_unlocked

                if is_unlocked(user_id):
                    vaulted = get_prompt(user_id, "begin_prologue")
                    if vaulted:
                        return vaulted
            except Exception:
                pass
    if SKELETON_MODE:
        return (
            "Mail Intelligence concierge (skeleton). "
            "Unlock local vault and deploy with --inject-from-vault for full prompts."
        )
    return _PROMPTS.load_prompt("begin_prologue")


BEGIN_PROLOGUE = _begin_prologue()
INDEXER_SYS = _prompt("inbox_indexer")
CYBER_SEC_GATE_SYS = _prompt("cyber_sec_gate")
CYBER_SEC_FOCUS_SYS = _prompt("cyber_sec_focus")
CAREER_MINER_SYS = _prompt("career_miner")
CAREER_VERIFIER_SYS = _prompt("career_verifier")
AUCTION_MINER_SYS = _prompt("auction_miner")
SUBSCRIPTION_MINER_SYS = _prompt("subscription_miner")
NOTIFICATION_DIGEST_SYS = _prompt("notification_digest")
FINANCE_MINER_SYS = _prompt("finance_miner")
COMMERCE_MERGE_SYS = _prompt("commerce_merge")
BRIEFING_SYNTH_SYS = _prompt("reception_synth")

# Categorize branch UUIDs (must match graph edge sourceHandle + items[].uuid)
CAT_BRIEFING = "a1000001-0000-4000-8000-000000000001"
CAT_SECURITY = "a1000002-0000-4000-8000-000000000002"
CAT_CAREER = "a1000003-0000-4000-8000-000000000003"
CAT_COMMERCE = "a1000004-0000-4000-8000-000000000004"
CAT_PLATFORM = "a1000005-0000-4000-8000-000000000005"

TOOL_CAREER_VERIFIER = "Tool:CareerVerifierTavily"

_CAT_SPECS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "security",
        CAT_SECURITY,
        "Agent:CyberSecFocus",
        "Security, phishing, threats, account breach, login alerts, privacy exposure, suspicious mail.",
        ["threat check", "is this phishing", "security alerts", "account breach"],
    ),
    (
        "career",
        CAT_CAREER,
        "Agent:CareerMiner",
        "Jobs, recruiters, hiring, career events, job boards, verify postings.",
        ["job listings", "career desk", "verify this job posting", "recruiter emails"],
    ),
    (
        "commerce",
        CAT_COMMERCE,
        "Agent:AuctionMiner",
        "Auctions, shopping alerts, bids, orders, Yahoo/commerce notifications, subscriptions billing.",
        [
            "auction alerts",
            "yahoo alerts",
            "my subscriptions",
            "shopping orders",
            "commerce desk",
        ],
    ),
    (
        "platform",
        CAT_PLATFORM,
        "Agent:NotificationDigest",
        "Platform noreply, newsletters, GitHub/dev notifications, marketing digests.",
        ["newsletters", "github notifications", "platform digest", "noreply mail"],
    ),
    (
        "briefing",
        CAT_BRIEFING,
        "Agent:CareerMinerBrief",
        "General inbox briefing, summary, comprehensive advice, overview, or user did not specify a single sector.",
        [
            "gimme a briefing",
            "comprehensive advice",
            "what's up in the inbox",
            "summarize my mail",
            "what's new on my inbox",
            "whats new on my inbox",
        ],
    ),
]


def _tavily_tool(tool_node_id: str) -> dict:
    """Agent.tools entry — runtime uses this; Tool node is canvas UI only (RAGFlow convention)."""
    return {
        "id": tool_node_id,
        "component_name": "TavilySearch",
        "name": "TavilySearch",
        "params": {
            "api_key": os.environ.get("TAVILY_API_KEY", ""),
            "days": 7,
            "exclude_domains": [],
            "include_answer": False,
            "include_domains": [],
            "include_image_descriptions": False,
            "include_images": False,
            "include_raw_content": True,
            "max_results": 5,
            "outputs": {
                "formalized_content": {"type": "string", "value": ""},
                "json": {"type": "Array<Object>", "value": []},
            },
            "query": "sys.query",
            "search_depth": "basic",
            "topic": "general",
        },
    }


def _tavily_tools(tool_node_id: str) -> list[dict]:
    return [_tavily_tool(tool_node_id)]


def _node(node_id: str, label: str, name: str, form: dict, x: float, y: float, ntype: str, height: int = 86) -> dict:
    return {
        "id": node_id,
        "type": ntype,
        "position": {"x": x, "y": y},
        "sourcePosition": "right",
        "targetPosition": "left",
        "data": {"label": label, "name": name, "form": form},
        "measured": {"width": 200, "height": height},
    }


def _agent_params(
    *,
    sys_prompt: str,
    user_content: str,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    tools: list | None = None,
    max_rounds: int = 1,
) -> dict:
    return {
        **LLM_BASE,
        "cite": False,
        "delay_after_error": 1,
        "description": "",
        "exception_default_value": "",
        "exception_goto": [],
        "exception_method": "",
        "max_retries": 3,
        "max_rounds": max_rounds,
        "max_tokens": max_tokens,
        "mcp": [],
        "message_history_window_size": 8,
        "outputs": {"content": {"type": "string", "value": ""}},
        "prompts": [{"role": "user", "content": user_content}],
        "sys_prompt": sys_prompt,
        "temperature": temperature,
        "tools": tools or [],
        "user_prompt": "",
        "visual_files_var": "",
    }


def _tool_node(node_id: str, name: str, x: float, y: float) -> dict:
    """Canvas Tool node — visual anchor for agent.tools (see web/src/pages/agent/canvas/node/tool-node.tsx)."""
    return _node(
        node_id,
        "Tool",
        name,
        {"description": "Tavily search — job / company verification", "user_prompt": ""},
        x,
        y,
        "toolNode",
        48,
    )


def _message_params(*parts: str) -> dict:
    return {"content": list(parts), "stream": False}


def _obsidian_save_form(*, content_ref: str, title_prefix: str) -> dict:
    return {
        "vault_path": "",
        "subfolder": OBSIDIAN_INTEL_FOLDER,
        "mode": "save",
        "max_notes": 5,
        "query": "{sys.query}",
        "content": content_ref,
        "title_prefix": title_prefix,
        "outputs": {
            "vault_context": {"type": "string", "value": ""},
            "saved_path": {"type": "string", "value": ""},
            "status": {"type": "string", "value": ""},
        },
    }


def _categorize_params() -> dict:
    items: list[dict] = []
    category_description: dict = {}
    for name, uuid, target, desc, examples in _CAT_SPECS:
        items.append(
            {
                "name": name,
                "description": desc,
                "examples": [{"value": ex} for ex in examples],
                "uuid": uuid,
            }
        )
        category_description[name] = {
            "description": desc,
            "examples": examples,
            "to": [target],
        }
    return {
        **LLM_BASE,
        "query": "sys.query",
        "message_history_window_size": 4,
        "max_tokens": 256,
        "temperature": 0.1,
        "items": items,
        "category_description": category_description,
        "outputs": {"category_name": {"type": "string"}},
    }


def build_dsl() -> dict:
    indexer_user = f"User: {{sys.query}}\n\nInbox:\n{INBOX_REF}"
    gate_user = f"User: {{sys.query}}\n\nInbox manifest:\n{MANIFEST_REF}"

    def _miner_user() -> str:
        return f"User: {{sys.query}}\n\nManifest:\n{MANIFEST_REF}\n\nCyberSec gate:\n{GATE_REF}"

    nodes = [
        _node(
            "begin",
            "Begin",
            "Chat entry",
            {
                "enablePrologue": True,
                "mode": "conversational",
                "prologue": BEGIN_PROLOGUE,
                "inputs": {},
                "outputs": {},
            },
            0,
            320,
            "beginNode",
            82,
        ),
        _node(
            "ImapInbox:Preload30d",
            "ImapInbox",
            "Fetch inbox 30d",
            {
                "connector_id": "",
                "days": 30,
                "max_messages": 200,
                "query": "{sys.query}",
                "outputs": {"inbox_context": {"type": "string", "value": ""}},
            },
            220,
            320,
            "ragNode",
            120,
        ),
        _node(
            "Agent:InboxIndexer",
            "Agent",
            "Inbox indexer",
            _agent_params(
                sys_prompt=INDEXER_SYS,
                user_content=indexer_user,
                max_tokens=4096,
                temperature=0.05,
            ),
            460,
            320,
            "agentNode",
            120,
        ),
        _node(
            "Agent:CyberSecGate",
            "Agent",
            "CyberSec gate",
            _agent_params(
                sys_prompt=CYBER_SEC_GATE_SYS,
                user_content=gate_user,
                max_tokens=3072,
                temperature=0.1,
            ),
            700,
            320,
            "agentNode",
            120,
        ),
        _node(
            "Categorize:SectorRouter",
            "Categorize",
            "Route sector",
            _categorize_params(),
            940,
            320,
            "categorizeNode",
            220,
        ),
        # Security branch
        _node(
            "Agent:CyberSecFocus",
            "Agent",
            "Threat analyst",
            _agent_params(
                sys_prompt=CYBER_SEC_FOCUS_SYS,
                user_content=(
                    f"User: {{sys.query}}\n\nManifest:\n{MANIFEST_REF}\n\n"
                    f"CyberSec gate:\n{GATE_REF}"
                ),
                max_tokens=2560,
                temperature=0.15,
            ),
            1200,
            40,
            "agentNode",
            120,
        ),
        _node(
            "ObsidianVault:SaveSecurity",
            "ObsidianVault",
            "Save security reply",
            _obsidian_save_form(
                content_ref="{Agent:CyberSecFocus@content}",
                title_prefix="security-reply",
            ),
            1320,
            40,
            "ragNode",
            100,
        ),
        _node(
            "Message:SecurityReply",
            "Message",
            "Security reply",
            _message_params(
                "{Agent:CyberSecFocus@content}",
                "\n\n---\n_Offline copy: {ObsidianVault:SaveSecurity@saved_path}_",
            ),
            1560,
            40,
            "messageNode",
        ),
        # Career branch
        _node(
            "Agent:CareerMiner",
            "Agent",
            "Career miner",
            _agent_params(
                sys_prompt=CAREER_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=2560,
                temperature=0.15,
            ),
            1200,
            140,
            "agentNode",
            120,
        ),
        _node(
            "Agent:CareerVerifier",
            "Agent",
            "Career verifier",
            _agent_params(
                sys_prompt=CAREER_VERIFIER_SYS,
                user_content=(
                    "User: {sys.query}\n\n"
                    "Career extraction:\n{Agent:CareerMiner@content}\n\n"
                    f"CyberSec gate:\n{GATE_REF}"
                ),
                max_tokens=3072,
                temperature=0.2,
                tools=_tavily_tools(TOOL_CAREER_VERIFIER),
                max_rounds=5,
            ),
            1440,
            140,
            "agentNode",
            120,
        ),
        _tool_node(TOOL_CAREER_VERIFIER, "Tavily search", 1440, 270),
        _node(
            "ObsidianVault:SaveCareer",
            "ObsidianVault",
            "Save career reply",
            _obsidian_save_form(
                content_ref="{Agent:CareerVerifier@content}",
                title_prefix="career-reply",
            ),
            1560,
            140,
            "ragNode",
            100,
        ),
        _node(
            "Message:CareerReply",
            "Message",
            "Career reply",
            _message_params(
                "{Agent:CareerVerifier@content}",
                "\n\n---\n_Offline copy: {ObsidianVault:SaveCareer@saved_path}_",
            ),
            1800,
            140,
            "messageNode",
        ),
        # Commerce branch
        _node(
            "Agent:AuctionMiner",
            "Agent",
            "Auction miner",
            _agent_params(
                sys_prompt=AUCTION_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=2048,
                temperature=0.15,
            ),
            1200,
            260,
            "agentNode",
            120,
        ),
        _node(
            "Agent:SubscriptionMiner",
            "Agent",
            "Subscription miner",
            _agent_params(
                sys_prompt=SUBSCRIPTION_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=2048,
                temperature=0.15,
            ),
            1440,
            260,
            "agentNode",
            120,
        ),
        _node(
            "Agent:CommerceMerge",
            "Agent",
            "Commerce merge",
            _agent_params(
                sys_prompt=COMMERCE_MERGE_SYS,
                user_content=(
                    "User: {sys.query}\n\n"
                    "Auction extraction:\n{Agent:AuctionMiner@content}\n\n"
                    "Subscription extraction:\n{Agent:SubscriptionMiner@content}\n\n"
                    f"CyberSec gate:\n{GATE_REF}"
                ),
                max_tokens=2560,
                temperature=0.2,
            ),
            1680,
            260,
            "agentNode",
            120,
        ),
        _node(
            "ObsidianVault:SaveCommerce",
            "ObsidianVault",
            "Save commerce reply",
            _obsidian_save_form(
                content_ref="{Agent:CommerceMerge@content}",
                title_prefix="commerce-reply",
            ),
            1800,
            260,
            "ragNode",
            100,
        ),
        _node(
            "Message:CommerceReply",
            "Message",
            "Commerce reply",
            _message_params(
                "{Agent:CommerceMerge@content}",
                "\n\n---\n_Offline copy: {ObsidianVault:SaveCommerce@saved_path}_",
            ),
            2040,
            260,
            "messageNode",
        ),
        # Platform branch
        _node(
            "Agent:NotificationDigest",
            "Agent",
            "Notification digest",
            _agent_params(
                sys_prompt=NOTIFICATION_DIGEST_SYS,
                user_content=_miner_user(),
                max_tokens=2048,
                temperature=0.15,
            ),
            1200,
            380,
            "agentNode",
            120,
        ),
        _node(
            "ObsidianVault:SavePlatform",
            "ObsidianVault",
            "Save platform reply",
            _obsidian_save_form(
                content_ref="{Agent:NotificationDigest@content}",
                title_prefix="platform-reply",
            ),
            1320,
            380,
            "ragNode",
            100,
        ),
        _node(
            "Message:PlatformReply",
            "Message",
            "Platform reply",
            _message_params(
                "{Agent:NotificationDigest@content}",
                "\n\n---\n_Offline copy: {ObsidianVault:SavePlatform@saved_path}_",
            ),
            1560,
            380,
            "messageNode",
        ),
        # Briefing branch — sequential miners (parallel canvas batch deferred)
        _node(
            "Agent:CareerMinerBrief",
            "Agent",
            "Career miner (briefing)",
            _agent_params(
                sys_prompt=CAREER_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=2560,
                temperature=0.15,
            ),
            1200,
            500,
            "agentNode",
            120,
        ),
        _node(
            "Agent:AuctionMinerBrief",
            "Agent",
            "Auction miner (briefing)",
            _agent_params(
                sys_prompt=AUCTION_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=2048,
                temperature=0.15,
            ),
            1440,
            500,
            "agentNode",
            120,
        ),
        _node(
            "Agent:SubscriptionMinerBrief",
            "Agent",
            "Subscription miner (briefing)",
            _agent_params(
                sys_prompt=SUBSCRIPTION_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=2048,
                temperature=0.15,
            ),
            1680,
            500,
            "agentNode",
            120,
        ),
        _node(
            "Agent:NotificationDigestBrief",
            "Agent",
            "Notification digest (briefing)",
            _agent_params(
                sys_prompt=NOTIFICATION_DIGEST_SYS,
                user_content=_miner_user(),
                max_tokens=2048,
                temperature=0.15,
            ),
            1920,
            500,
            "agentNode",
            120,
        ),
        _node(
            "Agent:FinanceMiner",
            "Agent",
            "Finance miner",
            _agent_params(
                sys_prompt=FINANCE_MINER_SYS,
                user_content=_miner_user(),
                max_tokens=1536,
                temperature=0.15,
            ),
            1680,
            500,
            "agentNode",
            120,
        ),
        _node(
            "ObsidianVault:LoadRecent",
            "ObsidianVault",
            "Load prior briefings",
            {
                "vault_path": "",
                "subfolder": OBSIDIAN_INTEL_FOLDER,
                "mode": "load_relevant",
                "max_notes": 1,
                "query": "{sys.query}",
                "content": "",
                "title_prefix": "inbox-briefing",
                "outputs": {
                    "vault_context": {"type": "string", "value": ""},
                    "saved_path": {"type": "string", "value": ""},
                    "status": {"type": "string", "value": ""},
                },
            },
            1920,
            500,
            "ragNode",
            100,
        ),
        _node(
            "Agent:BriefingSynth",
            "Agent",
            "Briefing synth",
            _agent_params(
                sys_prompt=BRIEFING_SYNTH_SYS,
                user_content=(
                    "User: {sys.query}\n\n"
                    "Prior vault notes:\n{ObsidianVault:LoadRecent@vault_context}\n\n"
                    f"CyberSec gate:\n{GATE_REF}\n\n"
                    "Career:\n{Agent:CareerMinerBrief@content}\n\n"
                    "Auction:\n{Agent:AuctionMinerBrief@content}\n\n"
                    "Subscriptions:\n{Agent:SubscriptionMinerBrief@content}\n\n"
                    "Platform:\n{Agent:NotificationDigestBrief@content}\n\n"
                    "Finance:\n{Agent:FinanceMiner@content}"
                ),
                max_tokens=3072,
                temperature=0.25,
            ),
            2160,
            500,
            "agentNode",
            120,
        ),
        _node(
            "ObsidianVault:Archive",
            "ObsidianVault",
            "Save briefing",
            _obsidian_save_form(
                content_ref="{Agent:BriefingSynth@content}",
                title_prefix="inbox-briefing",
            ),
            2400,
            500,
            "ragNode",
            100,
        ),
        _node(
            "Message:ChatReply",
            "Message",
            "Chat reply",
            _message_params(
                "{Agent:BriefingSynth@content}",
                "\n\n---\n_Offline copy: {ObsidianVault:Archive@saved_path}_",
            ),
            2640,
            500,
            "messageNode",
        ),
    ]

    trunk = [
        "begin",
        "ImapInbox:Preload30d",
        "Agent:InboxIndexer",
        "Agent:CyberSecGate",
        "Categorize:SectorRouter",
    ]

    branches = {
        "security": ["Agent:CyberSecFocus", "ObsidianVault:SaveSecurity", "Message:SecurityReply"],
        "career": [
            "Agent:CareerMiner",
            "Agent:CareerVerifier",
            "ObsidianVault:SaveCareer",
            "Message:CareerReply",
        ],
        "commerce": [
            "Agent:AuctionMiner",
            "Agent:SubscriptionMiner",
            "Agent:CommerceMerge",
            "ObsidianVault:SaveCommerce",
            "Message:CommerceReply",
        ],
        "platform": [
            "Agent:NotificationDigest",
            "ObsidianVault:SavePlatform",
            "Message:PlatformReply",
        ],
        "briefing": [
            "Agent:CareerMinerBrief",
            "Agent:AuctionMinerBrief",
            "Agent:SubscriptionMinerBrief",
            "Agent:NotificationDigestBrief",
            "Agent:FinanceMiner",
            "ObsidianVault:LoadRecent",
            "Agent:BriefingSynth",
            "ObsidianVault:Archive",
            "Message:ChatReply",
        ],
    }

    downstream: dict[str, list[str]] = {}
    upstream: dict[str, list[str]] = {}

    def _link(src: str, tgt: str) -> None:
        downstream.setdefault(src, []).append(tgt)
        upstream.setdefault(tgt, []).append(src)

    for i in range(len(trunk) - 1):
        _link(trunk[i], trunk[i + 1])

    # Categorize uses dynamic _next; downstream empty in components
    downstream["Categorize:SectorRouter"] = []

    for chain in branches.values():
        prev = "Categorize:SectorRouter"
        for nid in chain:
            _link(prev, nid)
            prev = nid

    edges = [
        {"id": f"e-{trunk[i]}-{trunk[i+1]}", "source": trunk[i], "sourceHandle": "start", "target": trunk[i + 1], "targetHandle": "end"}
        for i in range(len(trunk) - 1)
    ]

    cat_edges = [
        (CAT_SECURITY, "Agent:CyberSecFocus"),
        (CAT_CAREER, "Agent:CareerMiner"),
        (CAT_COMMERCE, "Agent:AuctionMiner"),
        (CAT_PLATFORM, "Agent:NotificationDigest"),
        (CAT_BRIEFING, "Agent:CareerMinerBrief"),
    ]
    for handle, target in cat_edges:
        edges.append(
            {
                "id": f"e-Categorize-{target}",
                "source": "Categorize:SectorRouter",
                "sourceHandle": handle,
                "target": target,
                "targetHandle": "end",
            }
        )

    tool_edges = [
        ("Agent:CareerVerifier", TOOL_CAREER_VERIFIER),
    ]
    for agent_id, tool_id in tool_edges:
        edges.append(
            {
                "id": f"e-{agent_id}-tool-{tool_id}",
                "source": agent_id,
                "sourceHandle": "tool",
                "target": tool_id,
                "targetHandle": "end",
            }
        )

    for chain in branches.values():
        for i in range(len(chain) - 1):
            src, tgt = chain[i], chain[i + 1]
            edges.append(
                {
                    "id": f"e-{src}-{tgt}",
                    "source": src,
                    "sourceHandle": "start",
                    "target": tgt,
                    "targetHandle": "end",
                }
            )

    all_ids = {n["id"] for n in nodes}
    components: dict = {}
    for n in nodes:
        nid = n["id"]
        label = n["data"]["label"]
        if label == "Tool":
            continue  # canvas-only; runtime uses agent.tools (RAGFlow convention)
        form = n["data"]["form"]
        comp_name = label if label != "Begin" else "Begin"
        components[nid] = {
            "obj": {"component_name": comp_name, "params": form},
            "downstream": downstream.get(nid, []),
            "upstream": upstream.get(nid, []),
        }

    return {
        "components": components,
        "globals": {
            "sys.conversation_turns": 0,
            "sys.date": "",
            "sys.files": [],
            "sys.history": [],
            "sys.query": "",
            "sys.user_id": "",
            "privacy": {
                "ephemeral_sessions": True,
                "hardware_auth_required": True,
                "zero_trust": True,
                "local_vault_required": True,
                "obsidian_2fa": True,
            },
        },
        "graph": {"nodes": nodes, "edges": edges},
        "history": [],
        "messages": [],
        "path": [],
        "retrieval": [],
        "variables": {},
    }


def validate_dsl(dsl: dict) -> list[str]:
    errors: list[str] = []
    for key in ("path", "history", "retrieval", "variables", "components", "graph", "globals"):
        if key not in dsl:
            errors.append(f"missing top-level key: {key}")

    components = dsl.get("components", {})
    node_ids = {n["id"] for n in dsl.get("graph", {}).get("nodes", [])}

    if any(k.startswith("Retrieval:") for k in components):
        errors.append("Retrieval nodes must not be present (embedding unavailable)")

    trunk = [
        "begin",
        "ImapInbox:Preload30d",
        "Agent:InboxIndexer",
        "Agent:CyberSecGate",
        "Categorize:SectorRouter",
    ]
    for i in range(len(trunk) - 1):
        src, tgt = trunk[i], trunk[i + 1]
        if tgt not in components.get(src, {}).get("downstream", []):
            errors.append(f"broken trunk link: {src} -> {tgt}")

    required_agents = (
        "Agent:InboxIndexer",
        "Agent:CyberSecGate",
        "Agent:CyberSecFocus",
        "Agent:CareerMiner",
        "Agent:CareerMinerBrief",
        "Agent:CareerVerifier",
        "Agent:AuctionMiner",
        "Agent:AuctionMinerBrief",
        "Agent:SubscriptionMiner",
        "Agent:SubscriptionMinerBrief",
        "Agent:CommerceMerge",
        "Agent:NotificationDigest",
        "Agent:NotificationDigestBrief",
        "Agent:FinanceMiner",
        "Agent:BriefingSynth",
    )
    for agent_id in required_agents:
        if agent_id not in node_ids:
            errors.append(f"missing node {agent_id}")
        agent = components.get(agent_id, {}).get("obj", {}).get("params", {})
        if agent.get("llm_id") != DEFAULT_LLM_ID:
            errors.append(f"{agent_id} llm_id must be {DEFAULT_LLM_ID}")

    if INBOX_REF not in (
        components.get("Agent:InboxIndexer", {}).get("obj", {}).get("params", {}).get("prompts", [{}])[0].get("content", "")
    ):
        errors.append("InboxIndexer must reference inbox context")

    if MANIFEST_REF not in (
        components.get("Agent:CyberSecGate", {}).get("obj", {}).get("params", {}).get("prompts", [{}])[0].get("content", "")
    ):
        errors.append("CyberSecGate must reference inbox manifest")

    career = components.get("Agent:CareerVerifier", {}).get("obj", {}).get("params", {})
    tools = career.get("tools") or []
    if not any(t.get("component_name") == "TavilySearch" for t in tools):
        errors.append("CareerVerifier must include TavilySearch tool")

    cat = components.get("Categorize:SectorRouter", {}).get("obj", {}).get("params", {})
    cats = cat.get("category_description") or {}
    for name in ("security", "career", "commerce", "platform", "briefing"):
        if name not in cats:
            errors.append(f"Categorize missing category: {name}")
    items = cat.get("items") or []
    if len(items) != 5:
        errors.append("Categorize must have 5 items with uuid for canvas handles")
    uuids = {i.get("uuid") for i in items}
    if uuids != {CAT_SECURITY, CAT_CAREER, CAT_COMMERCE, CAT_PLATFORM, CAT_BRIEFING}:
        errors.append("Categorize item uuids must match edge sourceHandles")

    graph_edges = dsl.get("graph", {}).get("edges", [])
    cat_out = [e for e in graph_edges if e.get("source") == "Categorize:SectorRouter"]
    if len(cat_out) != 5:
        errors.append(f"Categorize needs 5 outgoing edges, found {len(cat_out)}")
    tool_out = [e for e in graph_edges if e.get("sourceHandle") == "tool"]
    if len(tool_out) != 1:
        errors.append(f"CareerVerifier needs 1 Tavily tool edge, found {len(tool_out)}")

    for msg_id in (
        "Message:ChatReply",
        "Message:SecurityReply",
        "Message:CareerReply",
        "Message:CommerceReply",
        "Message:PlatformReply",
    ):
        if components.get(msg_id, {}).get("obj", {}).get("params", {}).get("stream") is not False:
            errors.append(f"{msg_id} must set stream=false to avoid reasoning leaks")

    for save_id in (
        "ObsidianVault:Archive",
        "ObsidianVault:SaveSecurity",
        "ObsidianVault:SaveCareer",
        "ObsidianVault:SaveCommerce",
        "ObsidianVault:SavePlatform",
    ):
        if save_id not in components:
            errors.append(f"missing {save_id}")

    if components.get("Message:ChatReply", {}).get("obj", {}).get("params", {}).get("content") != [
        "{Agent:BriefingSynth@content}",
        "\n\n---\n_Offline copy: {ObsidianVault:Archive@saved_path}_",
    ]:
        errors.append("Message:ChatReply must output BriefingSynth + Obsidian path")

    if "ObsidianVault:LoadRecent" not in components:
        errors.append("missing ObsidianVault:LoadRecent on briefing path")

    privacy = (dsl.get("globals") or {}).get("privacy") or {}
    if not privacy.get("ephemeral_sessions"):
        errors.append("globals.privacy.ephemeral_sessions must be true")
    if not privacy.get("hardware_auth_required"):
        errors.append("globals.privacy.hardware_auth_required must be true")
    if not privacy.get("zero_trust"):
        errors.append("globals.privacy.zero_trust must be true")
    if not privacy.get("local_vault_required"):
        errors.append("globals.privacy.local_vault_required must be true")
    if not privacy.get("obsidian_2fa"):
        errors.append("globals.privacy.obsidian_2fa must be true")

    return errors


def _auth_headers() -> dict:
    import httpx

    sys.path.insert(0, str(ROOT))
    from api.utils.crypt import crypt

    email = os.environ.get("RAGFLOW_API_EMAIL", "").strip()
    password = os.environ.get("RAGFLOW_API_PASSWORD", "").strip()
    if not email or not password:
        raise RuntimeError(
            "Set RAGFLOW_API_EMAIL and RAGFLOW_API_PASSWORD in the environment for --update"
        )

    password_enc = crypt(password)
    with httpx.Client(base_url=os.environ.get("RAGFLOW_API_BASE", "http://localhost:9380"), timeout=60) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password_enc},
        )
        login.raise_for_status()
        body = login.json()
        if body.get("code") != 0:
            raise RuntimeError(f"Login failed: {body}")
        auth = login.headers.get("authorization") or login.headers.get("Authorization")
        if not auth:
            raise RuntimeError("Login succeeded but no Authorization header returned")
        return {"Authorization": auth}


def update_via_api(agent_id: str, dsl: dict) -> None:
    import httpx

    headers = _auth_headers()
    with httpx.Client(base_url=os.environ.get("RAGFLOW_API_BASE", "http://localhost:9380"), timeout=60) as client:
        resp = client.put(f"/api/v1/agents/{agent_id}", headers=headers, json={"dsl": dsl})
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(f"Update agent failed: {result}")


def main() -> None:
    dsl = build_dsl()
    errors = validate_dsl(dsl)
    if errors:
        print("DSL validation FAILED:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print("DSL validation: OK")

    IMPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    IMPORT_PATH.write_text(json.dumps(dsl, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {IMPORT_PATH}")

    if "--update" in sys.argv:
        agent_id = os.environ.get("MAIL_INTEL_AGENT_ID", DEFAULT_AGENT_ID).strip()
        for i, arg in enumerate(sys.argv):
            if arg == "--agent-id" and i + 1 < len(sys.argv):
                agent_id = sys.argv[i + 1]
        if not agent_id:
            print("Set MAIL_INTEL_AGENT_ID (or pass --agent-id) for --update")
            sys.exit(1)
        update_via_api(agent_id, dsl)
        print(f"Updated agent id={agent_id}")


if __name__ == "__main__":
    main()
