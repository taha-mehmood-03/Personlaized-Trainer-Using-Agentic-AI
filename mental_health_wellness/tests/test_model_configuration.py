import os

from mental_health_wellness.llm.groq_llm import get_llm_manager


def _configured_model(name: str, default: str) -> str:
    for candidate in (
        os.getenv(f"GEMINI_{name}"),
        os.getenv(f"SENTIMIND_GEMINI_{name}"),
        os.getenv(name),
        os.getenv(f"SENTIMIND_{name}"),
    ):
        if candidate and candidate.strip().startswith("gemini-"):
            return candidate.strip()
    return default


def test_gemini_model_configuration_matches_env():
    manager = get_llm_manager()
    expected_model = "gemini-3.1-flash-lite"

    assert manager.model_gate == _configured_model("MODEL_GATE", expected_model)
    assert manager.model_mood == _configured_model("MODEL_MOOD", expected_model)
    assert manager.model_bypass == _configured_model("MODEL_BYPASS", expected_model)
    assert manager.model_response == _configured_model("MODEL_RESPONSE", expected_model)
    assert manager.model_crisis == _configured_model("MODEL_CRISIS", expected_model)
    assert manager.model_fallback == _configured_model("MODEL_FALLBACK", expected_model)
    assert manager.model_alt == _configured_model("MODEL_ALT", expected_model)

    for model in (
        manager.model_gate,
        manager.model_mood,
        manager.model_bypass,
        manager.model_response,
        manager.model_crisis,
        manager.model_fallback,
        manager.model_alt,
    ):
        assert model == expected_model
