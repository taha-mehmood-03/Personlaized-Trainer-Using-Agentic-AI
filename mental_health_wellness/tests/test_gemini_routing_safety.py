import pytest
from mental_health_wellness.llm import message_content_to_text
from mental_health_wellness.llm.llm_classifier import (
    deterministic_crisis_safety_net,
    llm_crisis_check,
)


def test_gemini_content_parts_are_flattened_to_text():
    content = [{"type": "text", "text": "hello"}, {"text": " world"}]

    assert message_content_to_text(content) == "hello world"


def test_deterministic_crisis_safety_net_catches_explicit_self_harm():
    result = deterministic_crisis_safety_net("I want to kill myself tonight.")

    assert result["crisis_detected"] is True
    assert result["crisis_level"] == "high"


@pytest.mark.asyncio
async def test_crisis_check_uses_safety_net_before_provider_call(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("provider should not be called for explicit crisis safety-net match")

    monkeypatch.setattr(
        "mental_health_wellness.llm.llm_classifier._call_gemini_async",
        fail_if_called,
    )

    result = await llm_crisis_check("I do not want to exist anymore.")

    assert result["crisis_detected"] is True
    assert result["crisis_level"] == "medium"
    assert result["source"] == "deterministic_safety_net"


def test_crisis_routes_imports_with_location_request_model():
    from mental_health_wellness.api.crisis_routes import LocationAlertRequest

    payload = LocationAlertRequest(
        user_id="user_123",
        latitude=24.8607,
        longitude=67.0011,
        crisis_level="high",
    )

    assert payload.user_id == "user_123"


@pytest.mark.skip(reason="_instant_chitchat_reply removed from current graph version")
def test_instant_chitchat_only_handles_exact_low_risk_greetings():
    pass
