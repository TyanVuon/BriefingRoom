from common.agent_privacy import (
    ephemeral_sessions_enabled,
    hardware_auth_required,
    privacy_policy,
    zero_trust_enabled,
)


def test_ephemeral_flag_from_globals():
    dsl = {"globals": {"privacy": {"ephemeral_sessions": True}}}
    assert ephemeral_sessions_enabled(dsl) is True


def test_ephemeral_disabled_by_default():
    assert ephemeral_sessions_enabled({"globals": {}}) is False


def test_hardware_auth_flag():
    dsl = {"globals": {"privacy": {"hardware_auth_required": True}}}
    assert hardware_auth_required(dsl) is True


def test_privacy_policy():
    dsl = {
        "globals": {
            "privacy": {
                "ephemeral_sessions": True,
                "hardware_auth_required": True,
                "zero_trust": True,
            }
        }
    }
    assert privacy_policy(dsl) == {
        "ephemeral_sessions": True,
        "hardware_auth_required": True,
        "zero_trust": True,
        "local_vault_required": True,
        "obsidian_2fa": True,
    }
    assert zero_trust_enabled(dsl) is True
