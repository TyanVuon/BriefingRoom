from api.apps.restful_apis import privacy_api as pa


def test_request_body_unwraps_frontend_data_wrapper():
    payload = {"data": {"credential": {"id": "abc", "rawId": "abc"}}}
    assert pa._request_body(payload) == payload["data"]


def test_request_body_passes_through_flat_payload():
    payload = {"credential": {"id": "abc"}}
    assert pa._request_body(payload) == payload


def test_request_body_empty_when_missing():
    assert pa._request_body(None) == {}
    assert pa._request_body({}) == {}


def test_user_safe_hardware_error_hides_internal_tracebacks():
    assert "attribute" not in pa._user_safe_hardware_error(
        AttributeError("'str' object has no attribute 'value'")
    ).lower()
    assert pa._user_safe_hardware_error(
        ValueError("No YubiKey registered. Enroll your USB security key first.")
    ) == "No hardware module enrolled. Complete initial provisioning first."


def test_user_safe_hardware_error_passes_through_plain_messages():
    assert pa._user_safe_hardware_error(
        ValueError("Module enrollment session expired.")
    ) == "Module enrollment session expired."

