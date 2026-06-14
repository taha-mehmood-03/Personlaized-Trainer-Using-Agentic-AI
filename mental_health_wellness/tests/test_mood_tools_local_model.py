from mental_health_wellness.tools import mood_tools


def test_local_goemotions_preserves_fear_core(monkeypatch):
    async def mock_gemini(message, context=""):
        return {
            "emotion": "fear",
            "primary_sub_emotion": "fear",
            "secondary_sub_emotions": ["nervousness"],
            "sentiment": "negative",
            "intensity": 0.82,
            "confidence": 0.82,
            "reasoning": "scared"
        }
    monkeypatch.setattr(mood_tools, "_gemini_analyze_mood", mock_gemini)

    result = mood_tools.analyze_mood("I'm scared something bad will happen tonight")

    assert result["emotion"] == "fear"
    assert result["primary_sub_emotion"] == "fear"


def test_explicit_anger_corrects_lazy_anxiety_prediction(monkeypatch):
    async def mock_gemini(message, context=""):
        return {
            "emotion": "anger",
            "primary_sub_emotion": "frustration",
            "secondary_sub_emotions": ["annoyance"],
            "sentiment": "negative",
            "intensity": 0.76,
            "confidence": 0.76,
            "reasoning": "frustrated"
        }
    monkeypatch.setattr(mood_tools, "_gemini_analyze_mood", mock_gemini)

    result = mood_tools.analyze_mood("I am so frustrated and angry because this feels unfair")

    assert result["emotion"] == "anger"
    assert result["primary_sub_emotion"] == "frustration"


def test_exam_sleep_tags_are_derived_without_llm(monkeypatch):
    async def mock_gemini(message, context=""):
        return {
            "emotion": "anxiety",
            "primary_sub_emotion": "academic_pressure",
            "secondary_sub_emotions": ["worry"],
            "sentiment": "negative",
            "intensity": 0.78,
            "confidence": 0.78,
            "detected_contexts": ["sleep_difficulty", "exam_week"],
            "detected_symptoms": ["bedtime_racing_thoughts"],
            "reasoning": "exam anxiety"
        }
    monkeypatch.setattr(mood_tools, "_gemini_analyze_mood", mock_gemini)

    result = mood_tools.analyze_mood(
        "My mind keeps replaying exam thoughts whenever I try to sleep next week"
    )

    assert result["emotion"] == "anxiety"
    assert "sleep_difficulty" in result["detected_contexts"]
    assert "exam_week" in result["detected_contexts"]
    assert "bedtime_racing_thoughts" in result["detected_symptoms"]


def test_social_humiliation_subemotion_tags_are_derived_without_llm(monkeypatch):
    async def mock_gemini(message, context=""):
        return {
            "emotion": "sadness",
            "primary_sub_emotion": "shame",
            "secondary_sub_emotions": ["embarrassment", "rejection"],
            "sentiment": "negative",
            "intensity": 0.72,
            "confidence": 0.72,
            "detected_contexts": ["school_conflict", "social_humiliation"],
            "reasoning": "shamed by principal"
        }
    monkeypatch.setattr(mood_tools, "_gemini_analyze_mood", mock_gemini)

    result = mood_tools.analyze_mood(
        "I was insulted by my principal in front of everyone and felt humiliated"
    )

    assert result["emotion"] == "sadness"
    assert result["primary_sub_emotion"] == "shame"
    assert "embarrassment" in result["secondary_sub_emotions"]
    assert "rejection" in result["secondary_sub_emotions"]
    assert "school_conflict" in result["detected_contexts"]
    assert "social_humiliation" in result["detected_contexts"]


def test_loneliness_subemotion_tags_are_derived_without_llm(monkeypatch):
    async def mock_gemini(message, context=""):
        return {
            "emotion": "sadness",
            "primary_sub_emotion": "loneliness",
            "secondary_sub_emotions": ["isolation"],
            "sentiment": "negative",
            "intensity": 0.70,
            "confidence": 0.70,
            "detected_behaviors": ["isolation"],
            "reasoning": "all alone"
        }
    monkeypatch.setattr(mood_tools, "_gemini_analyze_mood", mock_gemini)

    result = mood_tools.analyze_mood("I feel all alone and isolated lately")

    assert result["emotion"] == "sadness"
    assert result["primary_sub_emotion"] == "loneliness"
    assert "isolation" in result["secondary_sub_emotions"]
    assert "isolation" in result["detected_behaviors"]


def test_empty_emoji_keys_do_not_pollute_plain_text(monkeypatch):
    inputs = []
    async def mock_gemini(message, context=""):
        inputs.append(message)
        return {
            "emotion": "neutral",
            "primary_sub_emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.1,
            "confidence": 0.85,
            "reasoning": "neutral day"
        }
    monkeypatch.setattr(mood_tools, "_gemini_analyze_mood", mock_gemini)

    result = mood_tools.analyze_mood("Just a normal day")

    assert result["emotion"] == "neutral"
    assert inputs == ["Just a normal day"]
