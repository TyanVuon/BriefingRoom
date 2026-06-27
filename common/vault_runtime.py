#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Runtime injection of local vault secrets into agent DSL and components."""

from __future__ import annotations

import copy
import logging
import os
from typing import Any

from common.agent_privacy import zero_trust_enabled
from common.local_secrets_vault import (
    VaultLockedError,
    get_api_key,
    get_category,
    get_prompt,
    is_obsidian_unlocked,
    is_unlocked,
    require_obsidian_unlocked,
)

LOGGER = logging.getLogger(__name__)

# Component id → vault prompt name (mail intelligence router)
PROMPT_COMPONENT_MAP: dict[str, str] = {
    "begin": "begin_prologue",
    "Agent:InboxIndexer": "inbox_indexer",
    "Agent:CyberSecGate": "cyber_sec_gate",
    "Agent:CyberSecFocus": "cyber_sec_focus",
    "Agent:CareerMiner": "career_miner",
    "Agent:CareerMinerBrief": "career_miner",
    "Agent:CareerVerifier": "career_verifier",
    "Agent:AuctionMiner": "auction_miner",
    "Agent:AuctionMinerBrief": "auction_miner",
    "Agent:SubscriptionMiner": "subscription_miner",
    "Agent:SubscriptionMinerBrief": "subscription_miner",
    "Agent:CommerceMerge": "commerce_merge",
    "Agent:NotificationDigest": "notification_digest",
    "Agent:NotificationDigestBrief": "notification_digest",
    "Agent:FinanceMiner": "finance_miner",
    "Agent:BriefingSynth": "reception_synth",
}

_STUB_PREFIX = "[PROMPT:"
_STUB_SUFFIX = " — inject from local vault at deploy]"


def _resolve_user_id(dsl: dict[str, Any], tenant_id: str | None) -> str:
    globals_ = dsl.get("globals") or {}
    uid = (globals_.get("sys.user_id") or "").strip()
    if uid:
        return uid
    if tenant_id:
        return str(tenant_id)
    return os.environ.get("RAGFLOW_USER_ID", "").strip()


def _is_stub_prompt(text: str) -> bool:
    return isinstance(text, str) and text.strip().startswith(_STUB_PREFIX)


def inject_prompts_into_dsl(dsl: dict[str, Any], user_id: str) -> dict[str, Any]:
    if not user_id or not is_unlocked(user_id):
        return dsl
    components = dsl.get("components") or {}
    for comp_id, prompt_name in PROMPT_COMPONENT_MAP.items():
        comp = components.get(comp_id)
        if not comp:
            continue
        obj = comp.get("obj") or {}
        params = obj.get("params")
        if not isinstance(params, dict):
            continue
        prompt_text = get_prompt(user_id, prompt_name)
        if not prompt_text:
            continue
        component_name = obj.get("component_name", "")
        if component_name == "Begin":
            params["prologue"] = prompt_text
        elif "sys_prompt" in params and (_is_stub_prompt(params.get("sys_prompt", "")) or zero_trust_enabled(dsl)):
            no_think = get_prompt(user_id, "no_thinking") or ""
            params["sys_prompt"] = prompt_text.replace("{{NO_THINKING}}", no_think)
    return dsl


def inject_api_keys_into_dsl(dsl: dict[str, Any], user_id: str) -> dict[str, Any]:
    if not user_id or not is_unlocked(user_id):
        return dsl
    tavily_key = get_api_key(user_id, "TAVILY_API_KEY")
    if not tavily_key:
        return dsl
    for comp in (dsl.get("components") or {}).values():
        obj = comp.get("obj") or {}
        params = obj.get("params")
        if not isinstance(params, dict):
            continue
        for tool in params.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            if tool.get("component_name") == "TavilySearch":
                tool_params = tool.setdefault("params", {})
                if isinstance(tool_params, dict):
                    tool_params["api_key"] = tavily_key
    return dsl


def inject_connectors_into_dsl(dsl: dict[str, Any], user_id: str) -> dict[str, Any]:
    if not user_id or not is_unlocked(user_id):
        return dsl
    connectors = get_category(user_id, "connectors")
    imap_id = connectors.get("RAGFLOW_IMAP_CONNECTOR_ID") or connectors.get("imap_connector_id")
    if not imap_id:
        return dsl
    for comp_id, comp in (dsl.get("components") or {}).items():
        obj = comp.get("obj") or {}
        if obj.get("component_name") != "ImapInbox":
            continue
        params = obj.get("params")
        if isinstance(params, dict) and not params.get("connector_id"):
            params["connector_id"] = str(imap_id)
    return dsl


def maybe_inject_dsl_from_vault(dsl: dict[str, Any], tenant_id: str | None = None) -> dict[str, Any]:
    """Apply vault overrides when zero-trust policy is enabled."""
    if not zero_trust_enabled(dsl):
        return dsl
    user_id = _resolve_user_id(dsl, tenant_id)
    if not user_id:
        return dsl
    inject_prompts_into_dsl(dsl, user_id)
    inject_api_keys_into_dsl(dsl, user_id)
    inject_connectors_into_dsl(dsl, user_id)
    return dsl


def stub_prompt(name: str) -> str:
    return f"{_STUB_PREFIX}{name}{_STUB_SUFFIX}"


def build_skeleton_prompts() -> dict[str, str]:
    return {key: stub_prompt(val) for key, val in PROMPT_COMPONENT_MAP.items() if key != "begin"}


def load_vault_categories_for_deploy(user_id: str) -> dict[str, Any]:
    """Used by deploy scripts when vault is unlocked in-process."""
    from common.local_secrets_vault import SEALED_CATEGORIES

    if not is_unlocked(user_id):
        raise VaultLockedError("Unlock local vault before --inject-from-vault deploy.")
    return {cat: get_category(user_id, cat) for cat in SEALED_CATEGORIES}


def check_obsidian_gate(user_id: str) -> None:
    """Raise when Obsidian read/write is attempted without 2FA unlock."""
    if not user_id:
        raise VaultLockedError("Offline vault access is locked.")
    require_obsidian_unlocked(user_id)


def obsidian_gate_active() -> bool:
    return os.environ.get("MAIL_INTEL_OBSIDIAN_2FA", "true").strip().lower() in ("1", "true", "yes")
