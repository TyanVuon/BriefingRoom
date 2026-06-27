#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Fetch recent inbox mail over IMAP — no embedding / vector search required."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC

from agent.tools.base import ToolBase, ToolMeta, ToolParamBase
from api.db.services.connector_service import ConnectorService
from common.connection_utils import timeout
from common.data_source.imap_connector import ImapConnector
from common.data_source.outlook_personal_graph import fetch_outlook_personal_inbox
from common.data_source.utils import load_all_docs_from_checkpoint_connector

LOGGER = logging.getLogger(__name__)


class ImapInboxParam(ToolParamBase):
    def __init__(self):
        self.meta: ToolMeta = {
            "name": "fetch_imap_inbox",
            "description": "Fetch recent inbox messages over IMAP (no embedding).",
            "parameters": {
                "query": {
                    "type": "string",
                    "description": "User query (for logging only).",
                    "default": "{sys.query}",
                    "required": False,
                }
            },
        }
        super().__init__()
        self.connector_id = ""
        self.days = 30
        self.max_messages = 40
        self.query = "{sys.query}"
        self.outputs = {
            "inbox_context": {"type": "string", "value": ""},
        }

    def check(self):
        self.check_positive_number(self.days, "[ImapInbox] days")
        self.check_positive_number(self.max_messages, "[ImapInbox] max_messages")

    def get_input_form(self) -> dict[str, dict]:
        return {"query": {"name": "Query", "type": "line"}}


def _format_doc(doc) -> str:
    sender = ""
    if doc.primary_owners:
        owner = doc.primary_owners[0]
        sender = owner.display_name or owner.email or ""
    date = ""
    if doc.doc_updated_at:
        date = doc.doc_updated_at.strftime("%Y-%m-%d %H:%M UTC")
    subject = doc.semantic_identifier or doc.title or "(no subject)"
    body = doc.blob if isinstance(doc.blob, str) else (doc.blob or b"").decode("utf-8", errors="ignore")
    snippet = " ".join(body.split())[:500]
    return f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n{snippet}"


def fetch_imap_inbox(
    tenant_id: str,
    *,
    connector_id: str = "",
    days: int = 30,
    max_messages: int = 40,
) -> str:
    filters: dict = {"tenant_id": tenant_id, "source": "imap"}
    if connector_id:
        filters["id"] = connector_id
    connectors = ConnectorService.query(**filters)
    if not connectors:
        raise RuntimeError(
            "No IMAP data source found. Add one under Profile → Data source → IMAP."
        )

    conn = connectors[0]
    cfg = conn.config or {}
    creds = (cfg.get("credentials") or {}).copy()
    host = cfg.get("imap_host") or "outlook.office365.com"
    port = int(cfg.get("imap_port") or 993)
    mailboxes = cfg.get("imap_mailbox") or []

    imap = ImapConnector(host=host, port=port, mailboxes=mailboxes or None)
    imap.load_credentials(creds)

    end = time.time()
    start = end - int(days) * 86400
    try:
        docs = load_all_docs_from_checkpoint_connector(imap, start, end)
    except Exception as exc:
        msg = str(exc)
        if "AUTHENTICATE failed" in msg or "authentication failed" in msg.lower():
            # Security-hardened Outlook accounts require OAuth, not IMAP password.
            try:
                return fetch_outlook_personal_inbox(
                    cfg, days=days, max_messages=max_messages
                )
            except Exception as graph_exc:
                raise RuntimeError(
                    f"IMAP rejected login on {host}:{port} (TLS OK). "
                    "This account likely uses modern auth / encryption — run "
                    "`python scripts/pull_outlook_mail.py --login` once to OAuth, "
                    f"then retry. Graph fallback: {graph_exc}"
                ) from exc
        raise

    blocks: list[str] = []
    for doc in docs:
        if doc.metadata and doc.metadata.get("attachment_filename"):
            continue
        if not doc.blob:
            continue
        blocks.append(_format_doc(doc))
        if len(blocks) >= max_messages:
            break

    if not blocks:
        raise RuntimeError(
            f"No messages in the last {days} days (IMAP OK but nothing in that window)."
        )

    return (
        f"=== INBOX (last {days} days, {len(blocks)} messages) ===\n\n"
        + "\n\n---\n\n".join(blocks)
    )


class ImapInbox(ToolBase, ABC):
    component_name = "ImapInbox"

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        tenant_id = self._canvas.get_tenant_id()
        text = fetch_imap_inbox(
            tenant_id,
            connector_id=self._param.connector_id or "",
            days=int(self._param.days or 30),
            max_messages=int(self._param.max_messages or 40),
        )
        self.set_output("inbox_context", text)
        return text

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    async def _invoke_async(self, **kwargs):
        return await asyncio.to_thread(self._invoke, **kwargs)

    def thoughts(self) -> str:
        return f"Fetching last {self._param.days} days of inbox over IMAP…"
