#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Fetch personal @outlook.com / @hotmail.com mail via Microsoft Graph + OAuth."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import msal
import requests

LOGGER = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# `common` works for personal @outlook.com and multi-tenant apps; `consumers` needs
# an app explicitly registered for personal accounts only.
DEFAULT_AUTHORITY = os.environ.get(
    "MS_GRAPH_AUTHORITY", "https://login.microsoftonline.com/common"
)
GRAPH_SCOPES = ["Mail.Read", "User.Read"]


def _public_app(client_id: str, authority: str | None = None) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id, authority=authority or DEFAULT_AUTHORITY
    )


def acquire_token_device_code(client_id: str) -> dict[str, Any]:
    """Interactive device-code login for personal Microsoft accounts."""
    app = _public_app(client_id)
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(
            f"Device code flow failed to start: {flow.get('error_description') or flow}"
        )
    print(flow["message"], flush=True)
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(
            result.get("error_description") or result.get("error") or "OAuth login failed"
        )
    return result


def acquire_token_refresh(client_id: str, refresh_token: str) -> dict[str, Any]:
    app = _public_app(client_id)
    result = app.acquire_token_by_refresh_token(refresh_token, scopes=GRAPH_SCOPES)
    if "access_token" not in result:
        raise RuntimeError(
            result.get("error_description") or result.get("error") or "Token refresh failed"
        )
    return result


def _body_text(message: dict[str, Any]) -> str:
    preview = (message.get("bodyPreview") or "").strip()
    if preview:
        return preview
    body = message.get("body") or {}
    content = (body.get("content") or "").strip()
    if not content:
        return ""
    if (body.get("contentType") or "").lower() == "html":
        # Minimal tag strip — enough for terminal preview.
        text = content
        for tag in ("script", "style"):
            while True:
                start = text.lower().find(f"<{tag}")
                if start == -1:
                    break
                end = text.lower().find(f"</{tag}>", start)
                text = text[:start] if end == -1 else text[:start] + text[end + len(tag) + 3 :]
        out: list[str] = []
        in_tag = False
        for ch in text:
            if ch == "<":
                in_tag = True
                continue
            if ch == ">":
                in_tag = False
                continue
            if not in_tag:
                out.append(ch)
        return " ".join("".join(out).split())
    return content


def _format_message(message: dict[str, Any]) -> str:
    sender = ""
    from_obj = message.get("from") or {}
    email_addr = from_obj.get("emailAddress") or {}
    sender = email_addr.get("name") or email_addr.get("address") or ""
    subject = message.get("subject") or "(no subject)"
    date = message.get("receivedDateTime") or ""
    snippet = _body_text(message)[:500]
    return f"Date: {date}\nFrom: {sender}\nSubject: {subject}\n{snippet}"


def fetch_inbox_via_graph(
    access_token: str,
    *,
    days: int = 30,
    max_messages: int = 40,
) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    url = f"{GRAPH_BASE}/me/mailFolders/inbox/messages"
    params = {
        "$top": min(int(max_messages), 50),
        "$select": "subject,from,receivedDateTime,bodyPreview,body,isRead",
        "$filter": f"receivedDateTime ge {cutoff}",
        "$orderby": "receivedDateTime desc",
    }
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=60,
    )
    if resp.status_code == 401:
        raise RuntimeError("Graph access token expired or invalid — re-run OAuth login.")
    resp.raise_for_status()
    return resp.json().get("value") or []


def format_inbox_context(
    messages: list[dict[str, Any]],
    *,
    days: int,
    source: str = "Microsoft Graph",
) -> str:
    blocks = [_format_message(m) for m in messages if _format_message(m).strip()]
    if not blocks:
        raise RuntimeError(
            f"No messages in the last {days} days via {source} (OAuth OK, inbox empty in window)."
        )
    return (
        f"=== INBOX (last {days} days, {len(blocks)} messages via {source}) ===\n\n"
        + "\n\n---\n\n".join(blocks)
    )


def graph_credentials_from_config(cfg: dict[str, Any]) -> tuple[str, str] | None:
    creds = cfg.get("credentials") or {}
    client_id = (
        creds.get("graph_client_id")
        or os.environ.get("MS_GRAPH_CLIENT_ID")
        or os.environ.get("OUTLOOK_GRAPH_CLIENT_ID")
    )
    refresh = creds.get("graph_refresh_token")
    if client_id and refresh:
        return str(client_id), str(refresh)
    return None


def fetch_outlook_personal_inbox(
    cfg: dict[str, Any],
    *,
    days: int = 30,
    max_messages: int = 40,
) -> str:
    """Fetch inbox using stored Graph OAuth refresh token."""
    pair = graph_credentials_from_config(cfg)
    if not pair:
        raise RuntimeError(
            "No Graph OAuth token on this connector. Run: "
            "python scripts/pull_outlook_mail.py --login"
        )
    client_id, refresh_token = pair
    token = acquire_token_refresh(client_id, refresh_token)
    messages = fetch_inbox_via_graph(
        token["access_token"], days=days, max_messages=max_messages
    )
    return format_inbox_context(messages, days=days)


def save_graph_tokens_to_connector(
    connector_id: str,
    *,
    client_id: str,
    refresh_token: str,
    access_token: str | None = None,
) -> None:
    from api.db.services.connector_service import ConnectorService

    ok, conn = ConnectorService.get_by_id(connector_id)
    if not ok:
        raise RuntimeError(f"Connector {connector_id} not found")
    cfg = dict(conn.config or {})
    creds = dict(cfg.get("credentials") or {})
    creds["graph_client_id"] = client_id
    creds["graph_refresh_token"] = refresh_token
    if access_token:
        creds["graph_access_token"] = access_token
    cfg["credentials"] = creds
    ConnectorService.update_by_id(connector_id, {"config": cfg})
