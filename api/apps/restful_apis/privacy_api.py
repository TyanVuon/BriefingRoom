#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Zero-trust privacy APIs: WebAuthn / FIDO2 and encrypted vault."""

from __future__ import annotations

import logging

from quart import request

from api.apps import current_user, login_required
from api.utils.api_utils import get_data_error_result, get_json_result, get_request_json, server_error_response
from common.agent_privacy import privacy_policy
from common.hardware_auth import (
    authentication_options,
    clear_store,
    has_registered_credentials,
    issue_hardware_token,
    registration_options,
    store_corrupted,
    verify_hardware_token,
    verify_registration,
)
from common.local_secrets_vault import (
    VaultError,
    begin_totp_setup,
    lock_vault,
    seal_categories,
    unlock_vault,
    vault_status,
)
from common.privacy_vault import seal_user_vault, unseal_user_vault

LOGGER = logging.getLogger(__name__)


def _user_safe_hardware_error(exc: Exception) -> str:
    """Map internal WebAuthn failures to HSM-safe API messages."""
    message = str(exc).strip()
    lower = message.lower()
    if not message or "has no attribute" in lower or "attributeerror" in lower:
        return "Hardware module operation failed. Try again."
    if any(term in lower for term in ("fido", "webauthn", "yubikey", "passkey", "security key")):
        if "expired" in lower or "challenge" in lower:
            return "Module session expired. Reconnect your hardware module and try again."
        if "enroll" in lower or "register" in lower or "unknown" in lower:
            return "No hardware module enrolled. Complete initial provisioning first."
        return "Hardware module operation failed. Try again."
    return message


def _hardware_token_from_request() -> str | None:
    return request.headers.get("X-Hardware-Auth") or request.headers.get("x-hardware-auth")


def _request_body(req: dict | None) -> dict:
    """Unwrap ``{data: {...}}`` payloads from the frontend HTTP client."""
    if not isinstance(req, dict):
        return {}
    nested = req.get("data")
    if isinstance(nested, dict):
        return nested
    return req


@manager.route("/privacy/status", methods=["GET"])  # noqa: F821
@login_required
def privacy_status():
    user_id = current_user.id
    corrupted = store_corrupted(user_id)
    return get_json_result(
        data={
            "registered": has_registered_credentials(user_id),
            "store_corrupted": corrupted,
            "needs_reprovision": corrupted,
            "rp_id": __import__("common.hardware_auth", fromlist=["RP_ID"]).RP_ID,
            "rp_name": __import__("common.hardware_auth", fromlist=["RP_NAME"]).RP_NAME,
        }
    )


@manager.route("/privacy/webauthn/register/options", methods=["POST"])  # noqa: F821
@login_required
async def webauthn_register_options():
    try:
        if store_corrupted(current_user.id):
            clear_store(current_user.id)
        options = registration_options(current_user.id, username=current_user.email)
        return get_json_result(data=options)
    except Exception as exc:
        LOGGER.exception(exc)
        return get_data_error_result(message=_user_safe_hardware_error(exc))


@manager.route("/privacy/webauthn/register/verify", methods=["POST"])  # noqa: F821
@login_required
async def webauthn_register_verify():
    req = _request_body(await get_request_json())
    credential = req.get("credential")
    if not credential:
        return get_data_error_result(message="Module enrollment payload is required.")
    try:
        verify_registration(current_user.id, credential)
        return get_json_result(data={"registered": True})
    except Exception as exc:
        LOGGER.exception(exc)
        return get_data_error_result(message=_user_safe_hardware_error(exc))


@manager.route("/privacy/webauthn/authenticate/options", methods=["POST"])  # noqa: F821
@login_required
async def webauthn_authenticate_options():
    try:
        options = authentication_options(current_user.id)
        return get_json_result(data=options)
    except Exception as exc:
        LOGGER.exception(exc)
        return get_data_error_result(message=_user_safe_hardware_error(exc))


@manager.route("/privacy/webauthn/authenticate/verify", methods=["POST"])  # noqa: F821
@login_required
async def webauthn_authenticate_verify():
    req = _request_body(await get_request_json())
    credential = req.get("credential")
    if not credential:
        return get_data_error_result(message="Module verification payload is required.")
    try:
        token = issue_hardware_token(current_user.id, credential)
        from common.hardware_auth import HARDWARE_TOKEN_TTL

        return get_json_result(
            data={"hardware_token": token, "expires_in": HARDWARE_TOKEN_TTL}
        )
    except Exception as exc:
        LOGGER.exception(exc)
        return get_data_error_result(message=_user_safe_hardware_error(exc))


@manager.route("/privacy/vault/status", methods=["GET"])  # noqa: F821
@login_required
def privacy_vault_status():
    user_id = current_user.id
    try:
        status = vault_status(user_id)
    except VaultError as exc:
        return get_data_error_result(message=str(exc))
    status["hardware_registered"] = has_registered_credentials(user_id)
    return get_json_result(data=status)


@manager.route("/privacy/vault/setup", methods=["POST"])  # noqa: F821
@login_required
def privacy_vault_setup():
    """First-time TOTP enrollment — returns QR provisioning data once per user vault."""
    user_id = current_user.id
    try:
        payload = begin_totp_setup(user_id=user_id)
        return get_json_result(data=payload)
    except VaultError as exc:
        return get_data_error_result(message=str(exc))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/privacy/vault/unlock", methods=["POST"])  # noqa: F821
@login_required
async def privacy_vault_unlock():
    req = _request_body(await get_request_json())
    totp_code = str(req.get("totp_code") or req.get("code") or "").strip()
    if not totp_code:
        return get_data_error_result(message="Verification code is required.")
    user_id = current_user.id
    token = _hardware_token_from_request()
    policy_requires_hw = False
    try:
        from api.db.services.canvas_service import UserCanvasService

        agent_hint = req.get("agent_id")
        if agent_hint:
            ok, row = UserCanvasService.get_by_canvas_id(agent_hint)
            if ok and row:
                dsl = row.get("dsl")
                policy_requires_hw = hardware_auth_required_from_dsl(dsl)
    except Exception:
        policy_requires_hw = False
    if policy_requires_hw and not verify_hardware_token(token, user_id):
        return get_data_error_result(message="Hardware authentication required.")
    try:
        result = unlock_vault(
            user_id=user_id,
            totp_code=totp_code,
            hardware_token=token or "",
            unlock_vault=bool(req.get("unlock_vault", True)),
            unlock_obsidian=bool(req.get("unlock_obsidian", True)),
        )
        return get_json_result(data=result)
    except VaultError as exc:
        return get_data_error_result(message=str(exc))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/privacy/vault/lock", methods=["POST"])  # noqa: F821
@login_required
def privacy_vault_lock():
    lock_vault(user_id=current_user.id)
    return get_json_result(data={"locked": True})


@manager.route("/privacy/vault/seal", methods=["POST"])  # noqa: F821
@login_required
async def privacy_vault_seal():
    token = _hardware_token_from_request()
    if not verify_hardware_token(token, current_user.id):
        return get_data_error_result(message="Hardware authentication required.")
    req = _request_body(await get_request_json())
    secrets = req.get("secrets")
    categories = req.get("categories")
    if isinstance(categories, dict):
        try:
            seal_categories(user_id=current_user.id, categories=categories)
            return get_json_result(data={"sealed": True, "store": "local_vault"})
        except VaultError as exc:
            return get_data_error_result(message=str(exc))
        except Exception as exc:
            return server_error_response(exc)
    if not isinstance(secrets, dict):
        return get_data_error_result(message="`secrets` or `categories` object is required.")
    try:
        seal_user_vault(user_id=current_user.id, hardware_token=token, secrets=secrets)
        return get_json_result(data={"sealed": True, "store": "legacy"})
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/privacy/vault/unseal", methods=["POST"])  # noqa: F821
@login_required
async def privacy_vault_unseal():
    """Legacy hardware-bound unseal (deprecated — prefer /privacy/vault/unlock)."""
    token = _hardware_token_from_request()
    if not verify_hardware_token(token, current_user.id):
        return get_data_error_result(message="Hardware authentication required.")
    try:
        secrets = unseal_user_vault(user_id=current_user.id, hardware_token=token)
        return get_json_result(data={"secrets": secrets})
    except Exception as exc:
        return server_error_response(exc)


def hardware_auth_required_from_dsl(dsl) -> bool:
    return bool(privacy_policy(dsl).get("hardware_auth_required"))


def require_hardware_auth_for_dsl(dsl) -> tuple[bool, str]:
    """Return (ok, error_message). Checks DSL policy + request header."""
    policy = privacy_policy(dsl)
    if not policy.get("hardware_auth_required"):
        return True, ""
    user_id = current_user.id
    if not has_registered_credentials(user_id):
        return False, "Enroll your hardware security module before using this agent."
    token = _hardware_token_from_request()
    if not verify_hardware_token(token, user_id):
        return False, "Verify with your hardware security module to continue."
    return True, ""


def require_local_vault_for_dsl(dsl) -> tuple[bool, str]:
    """Return (ok, error_message) when zero-trust local vault must be unlocked."""
    policy = privacy_policy(dsl)
    if not policy.get("local_vault_required") and not policy.get("zero_trust"):
        return True, ""
    from common.local_secrets_vault import is_unlocked, vault_initialized

    user_id = current_user.id
    if not vault_initialized(user_id):
        return False, "Initialize your local secrets vault before using this agent."
    if not is_unlocked(user_id):
        return False, "Local vault is locked. Enter your authenticator code to unlock."
    return True, ""
