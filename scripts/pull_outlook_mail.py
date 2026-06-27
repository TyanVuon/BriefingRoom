#!/usr/bin/env python3
"""Pull personal Outlook inbox text to the terminal via Microsoft Graph OAuth.

Plain IMAP username/password does NOT work on security-hardened @outlook.com
accounts (passkeys, encryption, modern auth). This script uses OAuth instead.

One-time setup (free, ~3 min):
  1. https://portal.azure.com → App registrations → New registration
  2. Name: RAGFlow Mail, Supported accounts: "Personal Microsoft accounts only"
  3. Redirect URI: leave blank (public / native client)
  4. After create: copy Application (client) ID
  5. API permissions → Add → Microsoft Graph → Delegated → Mail.Read, User.Read
  6. Authentication → Allow public client flows → Yes → Save

Usage:
  export MS_GRAPH_CLIENT_ID='<your-azure-app-client-id>'
  # optional: export MS_GRAPH_AUTHORITY='https://login.microsoftonline.com/common'
  python scripts/pull_outlook_mail.py --login          # browser device login once
  python scripts/pull_outlook_mail.py                  # fetch with saved token
  python scripts/pull_outlook_mail.py --days 7 --max 10
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TENANT_ID = os.environ.get("RAGFLOW_TENANT_ID", "")
DEFAULT_CONNECTOR_ID = os.environ.get("RAGFLOW_IMAP_CONNECTOR_ID", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull Outlook mail via Graph OAuth")
    parser.add_argument("--login", action="store_true", help="Run device-code OAuth login")
    parser.add_argument("--client-id", default=os.environ.get("MS_GRAPH_CLIENT_ID", ""))
    parser.add_argument("--connector-id", default=DEFAULT_CONNECTOR_ID)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--max", type=int, default=10, dest="max_messages")
    parser.add_argument("--try-imap-first", action="store_true", help="Try IMAP before Graph")
    args = parser.parse_args()

    from common import settings

    settings.init_settings()

    from api.db.services.connector_service import ConnectorService
    from common.data_source.outlook_personal_graph import (
        acquire_token_device_code,
        acquire_token_refresh,
        fetch_inbox_via_graph,
        format_inbox_context,
        graph_credentials_from_config,
        save_graph_tokens_to_connector,
    )

    ok, connector = ConnectorService.get_by_id(args.connector_id)
    if not ok:
        print(f"Connector {args.connector_id} not found", file=sys.stderr)
        return 1

    cfg = dict(connector.config or {})
    creds = cfg.get("credentials") or {}
    client_id = (args.client_id or creds.get("graph_client_id") or os.environ.get("MS_GRAPH_CLIENT_ID") or "").strip()
    if not client_id:
        print(
            "Set MS_GRAPH_CLIENT_ID, pass --client-id, or store graph_client_id on the connector.\n"
            "See script header for setup steps.",
            file=sys.stderr,
        )
        return 1

    if args.try_imap_first:
        try:
            from agent.tools.imap_inbox import fetch_imap_inbox

            text = fetch_imap_inbox(
                TENANT_ID,
                connector_id=args.connector_id,
                days=args.days,
                max_messages=args.max_messages,
            )
            print(text)
            return 0
        except Exception as exc:
            print(f"IMAP failed ({exc}); trying Graph OAuth…", file=sys.stderr)

    access_token: str | None = None

    if args.login:
        print("Sign in with your Outlook account in the browser (passkey / 2FA OK)…")
        result = acquire_token_device_code(client_id)
        refresh = result.get("refresh_token")
        if not refresh:
            print("No refresh_token returned — check Azure app: public client + Mail.Read.", file=sys.stderr)
            return 1
        save_graph_tokens_to_connector(
            args.connector_id,
            client_id=client_id,
            refresh_token=refresh,
            access_token=result.get("access_token"),
        )
        print(f"Saved Graph refresh token to connector {args.connector_id}")
        access_token = result["access_token"]
    else:
        pair = graph_credentials_from_config(cfg)
        if not pair:
            print("No saved OAuth token. Run with --login first.", file=sys.stderr)
            return 1
        cid, refresh = pair
        token = acquire_token_refresh(cid, refresh)
        access_token = token["access_token"]

    messages = fetch_inbox_via_graph(
        access_token,
        days=args.days,
        max_messages=args.max_messages,
    )
    print(format_inbox_context(messages, days=args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
