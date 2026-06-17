from langchain_core.messages import AIMessage, HumanMessage

from mental_health_wellness.llm.llm_classifier import _normalize_smart_gate_result
from mental_health_wellness.nodes.consent_parser import parse_consent_and_suppression
from mental_health_wellness.nodes.conversation_context_resolver import resolve_conversation_context
from mental_health_wellness.nodes.parallel_intake import _gate_calibrated_mood


def test_thanks_after_technique_offer_is_acknowledgement_not_acceptance():
    state = {
        "messages": [
            AIMessage(content="I have something that might help. Would you like me to share it?"),
            HumanMessage(content="thanks"),
        ],
        "exercise_consent": "unknown",
        "solution_preference": "unknown",
    }

    resolved = resolve_conversation_context(state)
    consent = parse_consent_and_suppression(state)

    assert resolved["intent"] == "chitchat"
    assert resolved["response_task"] == "acknowledge_and_pause"
    assert "gratitude_acknowledgement" in resolved["gate_context_flags"]
    assert "exercise_consent" not in consent


def test_yes_thanks_after_technique_offer_accepts_pending_offer():
    state = {
        "messages": [
            AIMessage(content="I can share a small technique. Would you like me to share it?"),
            HumanMessage(content="yes thanks"),
        ],
        "exercise_consent": "unknown",
        "solution_preference": "unknown",
    }

    resolved = resolve_conversation_context(state)
    consent = parse_consent_and_suppression(state)

    assert resolved["intent"] == "accept_technique"
    assert resolved["response_task"] == "continue_active_technique"
    assert consent["exercise_consent"] == "allowed"
    assert consent["solution_preference"] == "exercise_requested"


def test_yes_thanks_after_context_question_is_not_technique_acceptance():
    resolved = resolve_conversation_context(
        {
            "messages": [
                AIMessage(content="Does it usually show up when you try to sleep?"),
                HumanMessage(content="yes thanks"),
            ],
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert resolved["intent"] == "contextual_followup"
    assert resolved["response_task"] == "ask_next_context_question"
    assert "accept_technique" not in resolved["gate_context_flags"]
    assert "answering_previous_question" in resolved["gate_context_flags"]


def test_direct_try_something_request_sets_exercise_requested():
    consent = parse_consent_and_suppression(
        {
            "messages": [
                AIMessage(content="What kind of support do you feel you are missing?"),
                HumanMessage(content="Yes please, I really want to try something. What do you suggest?"),
            ],
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert consent["exercise_consent"] == "allowed"
    assert consent["solution_preference"] == "exercise_requested"


def test_thank_you_that_helped_is_positive_feedback_not_acceptance():
    resolved = resolve_conversation_context(
        {
            "messages": [
                AIMessage(content="Step 1: write down the exact thought. Then we will test it gently."),
                HumanMessage(content="thank you, that helped"),
            ],
            "latest_recommended_technique": {"name": "Thought Record"},
            "active_technique": {"name": "Thought Record", "status": "active"},
        }
    )

    assert resolved["intent"] == "positive_feedback"
    assert resolved["response_task"] == "positive_feedback"
    assert "accept_technique" not in resolved["gate_context_flags"]


def test_no_thanks_after_offer_declines_without_rejection_feedback():
    state = {
        "messages": [
            AIMessage(content="Would you like me to share a small exercise?"),
            HumanMessage(content="no thanks"),
        ],
        "exercise_consent": "unknown",
        "solution_preference": "unknown",
    }

    resolved = resolve_conversation_context(state)
    consent = parse_consent_and_suppression(state)

    assert resolved["intent"] == "contextual_followup"
    assert resolved["response_task"] == "listen_only"
    assert "decline_technique_offer" in resolved["gate_context_flags"]
    assert consent["exercise_consent"] == "denied_soft"
    assert consent["solution_preference"] == "listen_only"


def test_gate_normalizer_overrides_false_acceptance_for_thanks_only():
    result = _normalize_smart_gate_result(
        {
            "route": "technique_follow_up",
            "confidence": 0.9,
            "context_flags": ["accept_technique"],
            "metadata": {},
        },
        "thanks",
        "AI: I have something that might help. Would you like me to share it?",
    )

    assert result["route"] == "chitchat"
    assert "gratitude_acknowledgement" in result["context_flags"]
    assert "accept_technique" not in result["context_flags"]
    assert result["exercise_consent"] == "unknown"


def test_gate_normalizer_yes_thanks_uses_previous_question_context():
    accepted = _normalize_smart_gate_result(
        {"route": "chitchat", "confidence": 0.7, "context_flags": [], "metadata": {}},
        "yes thanks",
        "AI: Would you like me to share it?",
    )
    contextual = _normalize_smart_gate_result(
        {"route": "technique_follow_up", "confidence": 0.7, "context_flags": ["accept_technique"], "metadata": {}},
        "yes thanks",
        "AI: Does it usually happen when you try to sleep?",
    )

    assert accepted["route"] == "technique_follow_up"
    assert "accept_technique" in accepted["context_flags"]
    assert accepted["exercise_consent"] == "allowed"
    assert contextual["route"] == "contextual_followup"
    assert "accept_technique" not in contextual["context_flags"]


def test_gate_calibrated_mood_keeps_thanks_low_signal_neutral():
    mood = _gate_calibrated_mood(
        {
            "gate_route": "chitchat",
            "gate_context_flags": ["gratitude_acknowledgement"],
            "last_detected_emotion": "anxiety",
            "last_detected_intensity": 0.7,
        },
        "thanks",
    )

    assert mood["emotion"] == "neutral"
    assert mood["sentiment"] == "neutral"
    assert mood["intensity"] <= 0.08
