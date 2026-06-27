#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Canvas component: save/load mail briefings in a local Obsidian vault."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from abc import ABC
from functools import partial

from agent.component.base import ComponentBase, ComponentParamBase
from common.connection_utils import timeout
from common.llm_output_sanitize import sanitize_user_facing_llm_output
from common.agent_privacy import zero_trust_enabled
from common.obsidian_vault_store import (
    DEFAULT_SUBFOLDER,
    DEFAULT_VAULT,
    load_context_if_relevant,
    save_briefing,
    search_notes,
)
from common.local_secrets_vault import VaultLockedError
from common.vault_runtime import check_obsidian_gate, obsidian_gate_active

LOGGER = logging.getLogger(__name__)


class ObsidianVaultParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.vault_path = DEFAULT_VAULT
        self.subfolder = DEFAULT_SUBFOLDER
        self.mode = "save"
        self.max_notes = 1
        self.content = ""
        self.query = "{sys.query}"
        self.title_prefix = "inbox-briefing"
        self.outputs = {
            "saved_path": {"type": "string", "value": ""},
            "vault_context": {"type": "string", "value": ""},
            "status": {"type": "string", "value": ""},
        }

    def check(self):
        self.check_positive_number(self.max_notes, "[ObsidianVault] max_notes")


class ObsidianVault(ComponentBase, ABC):
    component_name = "ObsidianVault"

    async def _materialize_value(self, val) -> str:
        if val is None:
            return ""
        if isinstance(val, partial):
            val = val()
        if inspect.isasyncgen(val):
            chunks: list[str] = []
            async for chunk in val:
                chunks.append(chunk if chunk is not None else "")
            val = "".join(chunks)
        elif inspect.isgenerator(val):
            val = "".join(str(chunk or "") for chunk in val)
        elif inspect.isawaitable(val):
            val = await val
        text = "" if val is None else str(val)
        return sanitize_user_facing_llm_output(text)

    async def _resolve(self, template: str) -> str:
        if not template:
            return ""
        text = template.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                val = self._canvas.get_variable_value(text)
                return await self._materialize_value(val)
            except Exception:
                return template
        return text

    def _vault_user_id(self) -> str:
        try:
            return str(self._canvas.globals.get("sys.user_id") or self._canvas.get_tenant_id() or "")
        except Exception:
            return ""

    async def _run_mode(self, **kwargs):
        if obsidian_gate_active() and zero_trust_enabled(self._canvas.dsl):
            check_obsidian_gate(self._vault_user_id())

        mode = (self._param.mode or "save").lower()
        vault_path = self._param.vault_path or DEFAULT_VAULT
        subfolder = self._param.subfolder or DEFAULT_SUBFOLDER
        query = await self._resolve(self._param.query or kwargs.get("query", ""))
        max_notes = int(self._param.max_notes or 1)

        if mode == "save":
            content = await self._resolve(self._param.content or kwargs.get("content", ""))
            saved = save_briefing(
                vault_path=vault_path,
                subfolder=subfolder,
                content=content,
                user_query=query,
                title_prefix=self._param.title_prefix or "inbox-briefing",
            )
            self.set_output("saved_path", saved)
            self.set_output("status", "saved")
            self.set_output("vault_context", "")
            return saved

        if mode == "search":
            ctx = search_notes(
                vault_path=vault_path,
                subfolder=subfolder,
                query=query,
                max_notes=max_notes,
            )
        elif mode == "load_relevant":
            ctx = load_context_if_relevant(
                vault_path=vault_path,
                subfolder=subfolder,
                user_query=query,
                max_notes=max_notes,
            )
        else:
            from common.obsidian_vault_store import load_recent

            ctx = load_recent(
                vault_path=vault_path,
                subfolder=subfolder,
                max_notes=max_notes,
            )

        self.set_output("vault_context", ctx or "")
        self.set_output("status", "loaded" if ctx else "empty")
        self.set_output("saved_path", "")
        return ctx or ""

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        return asyncio.run(self._run_mode(**kwargs))

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    async def _invoke_async(self, **kwargs):
        try:
            return await self._run_mode(**kwargs)
        except VaultLockedError as exc:
            LOGGER.warning("ObsidianVault locked: %s", exc)
            self.set_output("status", "locked")
            self.set_output("vault_context", str(exc))
            self.set_output("saved_path", "")
            return ""
        except Exception as exc:
            LOGGER.warning("ObsidianVault failed: %s", exc)
            self.set_output("status", "skipped")
            self.set_output("vault_context", "")
            self.set_output("saved_path", "")
            return ""

    def thoughts(self) -> str:
        return f"Obsidian vault ({self._param.mode})…"
