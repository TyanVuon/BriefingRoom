#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
"""Runtime vault injection into agent DSL."""

from __future__ import annotations

import pytest

from common.vault_runtime import inject_prompts_into_dsl, maybe_inject_dsl_from_vault, stub_prompt


def _dsl_with_stub():
    return {
        "globals": {"privacy": {"zero_trust": True}, "sys.user_id": "u1"},
        "components": {
            "Agent:CyberSecMaster": {
                "obj": {
                    "component_name": "Agent",
                    "params": {"sys_prompt": stub_prompt("cyber_sec_master")},
                }
            }
        },
    }


def test_stub_prompt_format():
    text = stub_prompt("foo")
    assert "foo" in text
    assert text.startswith("[PROMPT:")


def test_inject_prompts_when_unlocked(monkeypatch, tmp_path):
    monkeypatch.setenv("MAIL_INTEL_VAULT_MASTER", "test-master")
    monkeypatch.setenv("MAIL_INTEL_LOCAL_VAULT", str(tmp_path / "vault"))
    store: dict[str, str] = {}

    class _FakeRedis:
        def set(self, key, value, _ttl=None):
            store[key] = value if isinstance(value, str) else value.decode("utf-8")

        def get(self, key):
            return store.get(key)

        def delete(self, key):
            store.pop(key, None)

    import common.local_secrets_vault as lsv

    monkeypatch.setattr(lsv, "REDIS_CONN", _FakeRedis())

    from common.local_secrets_vault import init_vault, unlock_vault
    import pyotp
    from common.local_secrets_vault import _load_meta, _meta_key, _decrypt_blob

    user = "inject-user"
    init_vault(user_id=user, categories={"prompts": {"cyber_sec_master": "REAL PROMPT"}})
    meta = _load_meta(user)
    secret = _decrypt_blob(meta["totp_secret_enc"], _meta_key(user)).decode("utf-8")
    unlock_vault(user_id=user, totp_code=pyotp.TOTP(secret).now())

    dsl = _dsl_with_stub()
    dsl["globals"]["sys.user_id"] = user
    maybe_inject_dsl_from_vault(dsl, user)
    params = dsl["components"]["Agent:CyberSecMaster"]["obj"]["params"]
    assert params["sys_prompt"] == "REAL PROMPT"


def test_no_inject_when_locked(monkeypatch):
    monkeypatch.setenv("MAIL_INTEL_VAULT_MASTER", "test-master")
    from common.local_secrets_vault import init_vault

    user = "locked-user"
    init_vault(user_id=user, categories={"prompts": {"cyber_sec_master": "REAL PROMPT"}})
    dsl = _dsl_with_stub()
    dsl["globals"]["sys.user_id"] = user
    inject_prompts_into_dsl(dsl, user)
    params = dsl["components"]["Agent:CyberSecMaster"]["obj"]["params"]
    assert stub_prompt("cyber_sec_master") in params["sys_prompt"]
