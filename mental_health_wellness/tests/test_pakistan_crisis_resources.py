from mental_health_wellness.services.country_detector import (
    CountryDetector,
    format_phone_for_country,
)
from mental_health_wellness.tools.crisis_tools import get_crisis_resources, handle_crisis


def test_crisis_resources_default_to_pakistan():
    resources = get_crisis_resources()

    assert resources["primary_hotline"]["name"] == "Umang Pakistan Mental Health Helpline"
    assert resources["primary_hotline"]["number"] == "+92-311-7786264"
    assert resources["secondary_hotline"]["number"] == "1122"
    assert resources["tertiary_hotline"]["number"] == "15"
    assert resources["emergency_service"]["number"] == "115"


def test_unknown_country_uses_pakistan_resources():
    resources = get_crisis_resources("ZZ")

    assert resources["primary_hotline"]["number"] == "+92-311-7786264"
    assert "Pakistan" in resources["message"]


def test_country_detection_falls_back_to_pakistan():
    assert CountryDetector.detect(user_data={}) == "PK"
    assert CountryDetector.detect() == "PK"


def test_pakistan_phone_formatting_handles_local_and_e164_like_numbers():
    assert format_phone_for_country("0311-7786264", "PK") == "+923117786264"
    assert format_phone_for_country("923117786264", "PK") == "+923117786264"


def test_crisis_tool_defaults_to_pakistan_resources():
    result = handle_crisis.invoke({"message": "I might hurt myself", "reason": "test"})

    assert result["country_code"] == "PK"
    assert result["resources"]["primary_hotline"]["number"] == "+92-311-7786264"
