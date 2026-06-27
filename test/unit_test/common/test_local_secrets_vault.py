#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Unit tests for local secrets vault (seal/unlock/TOTP, no plaintext leak)."""

from __future__ import annotations

import json
import os

import pytest

from common.local_secrets_vault import (
    VaultError,
    VaultLockedError,
    begin_totp_setup,
    get_prompt,
    init_vault,
    is_unlocked,
    lock_vault,
    require_obsidian_unlocked,
    seal_categories,
    unlock_vault,
    vault_initialized,
    vault_status,
    verify_totp,
)


@pytest.fixture(autouse=True)
def vault_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_INTEL_VAULT_MASTER", "test-master-key-not-real")
    monkeypatch.setenv("MAIL_INTEL_LOCAL_VAULT", str(tmp_path / "vault"))
    monkeypatch.setenv("MAIL_INTEL_VAULT_SESSION_TTL_SEC", "60")
    store: dict[str, str] = {}

    class _FakeRedis:
        def set(self, key, value, _ttl=None):
            store[key] = value if isinstance(value, str) else value.decode("utf-8")

        def get(self, key):
            return store.get(key)

        def delete(self, key):
            store.pop(key, None)

    import common.local_secrets_vault as lsv

    monkeypatch.setattr(lsv, "_redis_conn", lambda: _FakeRedis())
    yield


@pytest.fixture
def user_id():
    return "user-test-001"


def test_init_and_status(user_id):
    secret = init_vault(user_id=user_id, categories={"prompts": {"cyber_sec_master": "secret prompt"}})
    assert len(secret) >= 16
    assert vault_initialized(user_id)
    status = vault_status(user_id)
    assert status["initialized"] is True
    assert status["needs_totp_setup"] is False
    assert status["vault_unlocked"] is False


def test_unlock_requires_valid_totp(user_id):
    init_vault(user_id=user_id)
    with pytest.raises(VaultError):
        unlock_vault(user_id=user_id, totp_code="000000")
    assert is_unlocked(user_id) is False


def test_unlock_and_read_prompt_without_plaintext_on_disk(user_id, monkeypatch):
    init_vault(
        user_id=user_id,
        categories={"prompts": {"cyber_sec_master": "top secret instruction"}},
    )
    import pyotp

    meta_path = os.environ["MAIL_INTEL_LOCAL_VAULT"]
    for path in os.listdir(meta_path):
        full = os.path.join(meta_path, path)
        raw = open(full, encoding="utf-8").read()
        assert "top secret instruction" not in raw

    # Recover secret from init for test verification only
    from common.local_secrets_vault import _load_meta, _meta_key, _decrypt_blob

    meta = _load_meta(user_id)
    secret = _decrypt_blob(meta["totp_secret_enc"], _meta_key(user_id)).decode("utf-8")
    code = pyotp.TOTP(secret).now()
    unlock_vault(user_id=user_id, totp_code=code)
    assert is_unlocked(user_id)
    assert get_prompt(user_id, "cyber_sec_master") == "top secret instruction"


def test_lock_clears_session(user_id):
    init_vault(user_id=user_id)
    import pyotp
    from common.local_secrets_vault import _load_meta, _meta_key, _decrypt_blob

    meta = _load_meta(user_id)
    secret = _decrypt_blob(meta["totp_secret_enc"], _meta_key(user_id)).decode("utf-8")
    code = pyotp.TOTP(secret).now()
    unlock_vault(user_id=user_id, totp_code=code)
    lock_vault(user_id=user_id)
    assert is_unlocked(user_id) is False
    assert get_prompt(user_id, "cyber_sec_master") is None


def test_obsidian_gate(user_id):
    init_vault(user_id=user_id)
    with pytest.raises(VaultLockedError):
        require_obsidian_unlocked(user_id)


def test_seal_categories_merge(user_id):
    init_vault(user_id=user_id, categories={"api_keys": {"TAVILY_API_KEY": "tvly-1"}})
    seal_categories(user_id=user_id, categories={"api_keys": {"TAVILY_API_KEY": "tvly-2"}})
    import pyotp
    from common.local_secrets_vault import _load_meta, _meta_key, _decrypt_blob, get_api_key

    meta = _load_meta(user_id)
    secret = _decrypt_blob(meta["totp_secret_enc"], _meta_key(user_id)).decode("utf-8")
    unlock_vault(user_id=user_id, totp_code=pyotp.TOTP(secret).now())
    assert get_api_key(user_id, "TAVILY_API_KEY") == "tvly-2"


def test_verify_totp_rejects_garbage(user_id):
    init_vault(user_id=user_id)
    assert verify_totp(user_id, "abc") is False


def test_begin_totp_setup(user_id):
    status = vault_status(user_id)
    assert status["needs_totp_setup"] is True
    payload = begin_totp_setup(user_id=user_id)
    assert payload["initialized"] is True
    assert "provisioning_uri" in payload
    assert vault_initialized(user_id)
    with pytest.raises(VaultError):
        begin_totp_setup(user_id=user_id)
