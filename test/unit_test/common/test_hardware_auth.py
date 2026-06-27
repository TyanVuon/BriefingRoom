import base64
import hashlib
import json

import pytest

webauthn = pytest.importorskip("webauthn")

from webauthn.helpers.structs import AuthenticatorTransport

from common import hardware_auth as ha


def _user_store(tmp_path, user_id: str, payload: dict) -> None:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]
    (tmp_path / f"{digest}.json").write_text(json.dumps(payload), encoding="utf-8")


def _frontend_registration_credential(*, cred_id_b64: str) -> dict:
    """Shape produced by @simplewebauthn/browser startRegistration()."""
    client_data = base64.urlsafe_b64encode(
        json.dumps(
            {
                "type": "webauthn.create",
                "challenge": "test-challenge",
                "origin": ha.RP_ORIGIN,
            }
        ).encode()
    ).decode().rstrip("=")
    attestation_object = base64.urlsafe_b64encode(b"\xa3test-attestation").decode().rstrip("=")
    return {
        "id": cred_id_b64,
        "rawId": cred_id_b64,
        "type": "public-key",
        "clientExtensionResults": {},
        "authenticatorAttachment": "cross-platform",
        "transports": ["usb", "nfc"],
        "response": {
            "clientDataJSON": client_data,
            "attestationObject": attestation_object,
        },
    }


def _frontend_authentication_credential(*, cred_id_b64: str) -> dict:
    client_data = base64.urlsafe_b64encode(
        json.dumps(
            {
                "type": "webauthn.get",
                "challenge": "test-challenge",
                "origin": ha.RP_ORIGIN,
            }
        ).encode()
    ).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(b"test-signature").decode().rstrip("=")
    authenticator_data = base64.urlsafe_b64encode(b"\xa3test-auth-data").decode().rstrip("=")
    return {
        "id": cred_id_b64,
        "rawId": cred_id_b64,
        "type": "public-key",
        "clientExtensionResults": {},
        "response": {
            "clientDataJSON": client_data,
            "authenticatorData": authenticator_data,
            "signature": signature,
        },
    }


def test_registration_options_serializes_cross_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setattr(ha, "REDIS_CONN", type("R", (), {"set": lambda *a, **k: None})())

    opts = ha.registration_options("user-1", username="user@example.com")

    assert "challenge" in opts
    assert opts["authenticatorSelection"]["authenticatorAttachment"] == "cross-platform"
    assert opts["authenticatorSelection"]["userVerification"] == "required"
    assert opts["authenticatorSelection"]["residentKey"] == "preferred"


def test_authentication_options_with_string_transports(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setattr(ha, "REDIS_CONN", type("R", (), {"set": lambda *a, **k: None})())
    cred_id = base64.urlsafe_b64encode(b"test-credential-id").decode().rstrip("=")
    pub_key = base64.urlsafe_b64encode(b"test-public-key").decode().rstrip("=")
    _user_store(
        tmp_path,
        "user-1",
        {
            "credentials": [
                {
                    "credential_id": cred_id,
                    "public_key": pub_key,
                    "sign_count": 0,
                    "transports": ["usb"],
                }
            ]
        },
    )

    opts = ha.authentication_options("user-1")

    assert "challenge" in opts
    assert opts["userVerification"] == "required"
    assert opts["allowCredentials"]
    assert opts["allowCredentials"][0]["transports"] == ["usb"]


def test_transport_helpers_round_trip():
    assert ha._transport_value_list(["USB", "nfc"]) == ["usb", "nfc"]
    enums = ha._transport_enums(["usb", "nfc"])
    assert enums == [AuthenticatorTransport.USB, AuthenticatorTransport.NFC]


def test_verify_registration_persists_string_transports(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setattr(ha, "REDIS_CONN", type("R", (), {"set": lambda *a, **k: None})())

    cred_id = base64.urlsafe_b64encode(b"cred-id-bytes").decode().rstrip("=")
    credential = _frontend_registration_credential(cred_id_b64=cred_id)
    transports = ha._transport_value_list(credential.get("transports"))

    _user_store(
        tmp_path,
        "user-1",
        {
            "credentials": [
                {
                    "credential_id": cred_id,
                    "public_key": base64.urlsafe_b64encode(b"pub").decode().rstrip("="),
                    "sign_count": 0,
                    "transports": transports,
                }
            ]
        },
    )

    assert transports == ["usb", "nfc"]
    opts = ha.authentication_options("user-1")
    assert opts["allowCredentials"][0]["transports"] == ["usb", "nfc"]


def test_load_store_marks_decrypt_failure_as_corrupted(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setenv("MAIL_INTEL_HARDWARE_STORE_KEY", "wrong-key")
    digest = hashlib.sha256(b"user-bad").hexdigest()[:32]
    # Write blob encrypted with a different key
    monkeypatch.setenv("MAIL_INTEL_HARDWARE_STORE_KEY", "correct-key")
    ha._save_store("user-bad", {"credentials": [{"credential_id": "x", "public_key": "y", "sign_count": 0}]})
    monkeypatch.setenv("MAIL_INTEL_HARDWARE_STORE_KEY", "wrong-key")
    loaded = ha._load_store("user-bad")
    assert loaded.get("credentials") == []
    assert loaded.get("_store_corrupted") is True
    assert ha.store_corrupted("user-bad") is True


def test_clear_store_removes_enrollment(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    ha._save_store("user-clear", {"credentials": [{"credential_id": "x", "public_key": "y", "sign_count": 0}]})
    assert ha.has_registered_credentials("user-clear")
    ha.clear_store("user-clear")
    assert not ha.has_registered_credentials("user-clear")


def test_transport_enums_fallback_for_unknown():
    enums = ha._transport_enums(["unknown-transport"])
    assert enums == ha._cross_platform_transports()


def test_hardware_token_ttl_defaults_to_24h(monkeypatch):
    monkeypatch.delenv("MAIL_INTEL_HARDWARE_TOKEN_TTL_SEC", raising=False)
    monkeypatch.delenv("MAIL_INTEL_HARDWARE_TOKEN_TTL", raising=False)
    import importlib

    import common.hardware_auth as reloaded

    importlib.reload(reloaded)
    assert reloaded.HARDWARE_TOKEN_TTL == 86400


def test_save_store_encrypts_at_rest(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setenv("MAIL_INTEL_HARDWARE_STORE_KEY", "test-store-key")
    payload = {
        "credentials": [
            {
                "credential_id": "abc",
                "public_key": "def",
                "sign_count": 0,
                "transports": ["usb"],
            }
        ]
    }
    ha._save_store("user-enc", payload)
    path = tmp_path / f"{hashlib.sha256(b'user-enc').hexdigest()[:32]}.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk.get("encrypted") is True
    assert "blob" in on_disk
    assert "credentials" not in on_disk
    assert ha._load_store("user-enc") == payload


def test_load_store_migrates_legacy_plain_json(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setenv("MAIL_INTEL_HARDWARE_STORE_KEY", "test-store-key")
    legacy = {
        "credentials": [
            {
                "credential_id": "legacy-id",
                "public_key": "legacy-pub",
                "sign_count": 1,
                "transports": ["usb"],
            }
        ]
    }
    _user_store(tmp_path, "user-legacy", legacy)
    loaded = ha._load_store("user-legacy")
    assert loaded == legacy
    creds = ha.list_credentials("user-legacy")
    assert len(creds) == 1
    assert creds[0].credential_id == "legacy-id"


def test_save_store_reencrypts_legacy_on_write(monkeypatch, tmp_path):
    monkeypatch.setattr(ha, "STORE_DIR", tmp_path)
    monkeypatch.setenv("MAIL_INTEL_HARDWARE_STORE_KEY", "test-store-key")
    legacy = {"credentials": [{"credential_id": "x", "public_key": "y", "sign_count": 0}]}
    _user_store(tmp_path, "user-migrate", legacy)
    ha._save_store("user-migrate", legacy)
    path = tmp_path / f"{hashlib.sha256(b'user-migrate').hexdigest()[:32]}.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk.get("encrypted") is True
