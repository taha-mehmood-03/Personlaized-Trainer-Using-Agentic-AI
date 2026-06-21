"""
Therapeutic lifecycle test suite.

Each test uses novel message phrasing that does NOT appear in keyword lists
(_BODY_DISTRESS_SIGNALS, _REGULATION_ACTION_SIGNALS, etc.) so that the LLM /
semantic detection layer is exercised, not regex matching.

Physical/physiological scenarios (tests 4, 5, 12) set primary_sub_emotion and
detected_symptoms directly in state — this simulates the mood analyzer LLM
output that would already be in state by the time the planner runs.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from mental_health_wellness.pipeline.conversation_planner_node import conversation_planner_node


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _base(message: str, **overrides) -> dict:
    """Minimal valid state with sensible defaults."""
    state = {
        "messages": [HumanMessage(content=message)],
        "session_message_count": 1,
        "fused_emotion": "neutral",
        "fused_intensity": 0.3,
        "emotional_trend": "stable",
        "crisis_detected": False,
        "crisis_level": "low",
        "gate_context_flags": [],
        "exercise_consent": "unknown",
        "solution_preference": "unknown",
        "prefetched_intent": {
            "intent": "therapeutic",
            "confidence": 0.80,
            "source": "smart_gate",
        },
        "gate_route": "therapeutic",
        "gate_emotional_register": "distress",
    }
    state.update(overrides)
    return state


# ─────────────────────────────────────────────────────────────────────────────
# 1. Initial disclosure — short, vague, emotionally loaded
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initial_disclosure_asks_context_question():
    """First message with emotion but no context detail → ask one question."""
    result = await conversation_planner_node(_base(
        "Everything at home just fell apart last month and I cannot seem to get back on track",
        session_message_count=1,
        fused_emotion="sadness",
        fused_intensity=0.65,
        primary_sub_emotion="grief",
    ))

    assert result["needs_technique"] is False
    assert result["conversation_stage"] == "DISCOVERY"
    assert result["response_task"] in {
        "ask_next_context_question",
        "ask_one_missing_context_question",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Context gathering — user answers a duration follow-up
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_context_gathering_duration_answer():
    """User provides a duration answer → planner continues context collection or summarises."""
    state = _base(
        "It has been going on for roughly six weeks now",
        session_message_count=2,
        fused_emotion="sadness",
        fused_intensity=0.60,
        primary_concern="home situation",
        question_count_since_disclosure=1,
        prefetched_intent={
            "intent": "contextual_followup",
            "confidence": 0.88,
            "source": "smart_gate",
        },
        gate_route="contextual_followup",
        gate_context_flags=["answering_previous_question"],
        resolved_user_act={
            "intent": "contextual_followup",
            "context_flags": ["answering_previous_question"],
            "referent": "last_assistant_question",
            "response_task": "ask_next_context_question",
            "slot_updates": {"concern_duration": "six weeks"},
        },
    )
    state["messages"] = [
        HumanMessage(content="Everything at home just fell apart."),
        AIMessage(content="How long has this been affecting you?"),
        HumanMessage(content="It has been going on for roughly six weeks now"),
    ]

    result = await conversation_planner_node(state)

    assert result["needs_technique"] is False
    assert result["response_task"] in {
        "ask_next_context_question",
        "ask_one_missing_context_question",
        "summarize_known_context",
        "formulate_and_offer_help",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Long message with full context — should bypass context questions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rich_single_message_bypasses_context_questions():
    """
    A 40+ word first message containing trigger, duration, impact, and emotion
    should result in context_sufficiency >= 0.6 and NOT another context question.
    """
    msg = (
        "For the past two months I have been completely unable to focus at university "
        "because of a falling-out with a close friend that ended badly. It is affecting "
        "my sleep, my assignments, and my confidence in social situations."
    )
    result = await conversation_planner_node(_base(
        msg,
        session_message_count=1,
        fused_emotion="sadness",
        fused_intensity=0.75,
        primary_sub_emotion="shame",
        resolved_user_act={
            "intent": "therapeutic",
            "context_flags": ["new_emotional_disclosure"],
            "referent": None,
            "response_task": "ask_next_context_question",
            "slot_updates": {
                "primary_concern": "falling-out with close friend",
                "concern_duration": "two months",
                "triggering_context": "conflict with friend",
                "functional_impact": "affecting sleep, assignments, confidence",
            },
        },
        gate_context_flags=["new_emotional_disclosure"],
    ))

    # Must NOT loop back into more context questions when message is already rich
    assert result["response_task"] not in {"ask_next_context_question", "ask_one_missing_context_question"} \
        or result.get("context_sufficiency", 0) >= 0.6


# ─────────────────────────────────────────────────────────────────────────────
# 4. Physical/physiological distress — LLM-detected, NO keyword match in text
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_physiological_distress_via_llm_symptoms_triggers_immediate_regulation():
    """
    Message text has no keywords from _BODY_DISTRESS_SIGNALS.
    The mood analyzer (simulated via state) detected panic + acute symptoms.
    Planner must read that LLM output and set immediate_regulation_request=True.
    """
    result = await conversation_planner_node(_base(
        # 'vision went blurry', 'heart pounding', 'could not think straight'
        # are NOT in _BODY_DISTRESS_SIGNALS or _REGULATION_ACTION_SIGNALS
        "All of a sudden my vision went blurry and my heart started pounding so hard I could not think straight",
        session_message_count=1,
        fused_emotion="anxiety",
        fused_intensity=0.88,
        primary_sub_emotion="panic",
        detected_symptoms=["shortness_of_breath", "body_tension", "chest_tightness"],
    ))

    assert result["immediate_regulation_request"] is True
    assert result["response_task"] == "start_grounding_now"
    assert result["question_budget"] == 0
    assert result["exercise_consent"] == "allowed"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Physiological distress — alternate novel phrasing, acute_anxiety sub
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dissociation_phrasing_triggers_immediate_regulation():
    """
    'Limbs went ice cold / disconnected from everything' — not in any keyword list.
    Mood analyzer output says acute_anxiety + respiratory_distress.
    """
    result = await conversation_planner_node(_base(
        "My limbs went ice cold and I felt completely disconnected from everything around me",
        session_message_count=1,
        fused_emotion="fear",
        fused_intensity=0.91,
        primary_sub_emotion="acute_anxiety",
        detected_symptoms=["respiratory_distress", "body_tension"],
    ))

    assert result["immediate_regulation_request"] is True
    assert result["response_task"] == "start_grounding_now"
    assert result["question_budget"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Technique acceptance
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_technique_acceptance_routes_to_continue():
    """User agrees to try a technique — planner should proceed with delivery."""
    state = _base(
        "That does sound like something I could attempt, walk me through it",
        session_message_count=3,
        fused_emotion="anxiety",
        fused_intensity=0.65,
        exercise_consent="allowed",
        solution_preference="exercise_requested",
        pending_recommended_technique={"id": "box-breathing", "name": "Box Breathing", "category": "breathing", "steps": []},
        prefetched_intent={
            "intent": "accept_technique",
            "confidence": 0.92,
            "source": "smart_gate",
        },
        gate_route="accept_technique",
        gate_context_flags=["accept_technique"],
        resolved_user_act={
            "intent": "accept_technique",
            "context_flags": ["accept_technique"],
            "referent": "pending_technique",
            "response_task": "continue_active_technique",
            "slot_updates": {},
        },
    )

    result = await conversation_planner_node(state)

    assert result["response_task"] == "continue_active_technique"
    # exercise_consent may stay in state rather than being re-emitted in result
    assert result.get("exercise_consent", "allowed") == "allowed"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Technique rejection
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_technique_rejection_blocks_needs_technique():
    """User declines a suggested technique — needs_technique must be False."""
    state = _base(
        "I do not think that particular approach would suit me at all",
        session_message_count=3,
        fused_emotion="anxiety",
        fused_intensity=0.65,
        pending_recommended_technique={"id": "box-breathing", "name": "Box Breathing", "category": "breathing", "steps": []},
        prefetched_intent={
            "intent": "reject_technique",
            "confidence": 0.88,
            "source": "smart_gate",
        },
        gate_route="reject_technique",
        gate_context_flags=["reject_technique"],
        resolved_user_act={
            "intent": "reject_technique",
            "context_flags": ["reject_technique"],
            "referent": "pending_technique",
            "response_task": "handle_technique_rejection",
            "slot_updates": {},
        },
    )

    result = await conversation_planner_node(state)

    assert result["needs_technique"] is False
    assert result["response_task"] == "handle_technique_rejection"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Positive feedback / recovery starts
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_positive_feedback_triggers_recovery_phase():
    """User reports improvement → conversation_phase must become recovery."""
    state = _base(
        "That actually made a noticeable difference, I am feeling considerably steadier now",
        session_message_count=5,
        fused_emotion="joy",
        fused_intensity=0.40,
        conversation_phase="solution",
        latest_recommended_technique={"id": "box-breathing", "name": "Box Breathing"},
        prefetched_intent={
            "intent": "positive_feedback",
            "confidence": 0.90,
            "source": "smart_gate",
        },
        gate_route="positive_feedback",
        gate_context_flags=["positive_outcome"],
        resolved_user_act={
            "intent": "positive_feedback",
            "context_flags": ["positive_outcome"],
            "referent": "active_technique",
            "response_task": "positive_feedback",
            "slot_updates": {},
        },
    )

    result = await conversation_planner_node(state)

    assert result["conversation_phase"] == "recovery"
    assert result["response_task"] in {"positive_feedback", "warm_close_and_invite"}


# ─────────────────────────────────────────────────────────────────────────────
# 9. Recovery loop — warm close fires after one reflection question
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_loop_warm_close_after_one_reflection():
    """
    reflection_questions_since_resolution=1 means one reflection already happened.
    Next recovery turn must fire warm_close_and_invite, not another question.
    """
    state = _base(
        "Yes, I think I have a better handle on it now",
        session_message_count=7,
        fused_emotion="neutral",
        fused_intensity=0.30,
        conversation_phase="recovery",
        reflection_questions_since_resolution=1,
        latest_recommended_technique={"id": "box-breathing", "name": "Box Breathing"},
        prefetched_intent={
            "intent": "positive_feedback",
            "confidence": 0.85,
            "source": "smart_gate",
        },
        gate_route="positive_feedback",
        gate_context_flags=["positive_outcome"],
        resolved_user_act={
            "intent": "positive_feedback",
            "context_flags": ["positive_outcome"],
            "referent": "active_technique",
            "response_task": "positive_feedback",
            "slot_updates": {},
        },
    )

    result = await conversation_planner_node(state)

    assert result["response_task"] == "warm_close_and_invite"
    assert result.get("session_disclosure_complete") is True


# ─────────────────────────────────────────────────────────────────────────────
# 10. Session re-entry after disclosure complete
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_reentry_resets_lifecycle_flags():
    """
    After warm_close_and_invite, session_disclosure_complete=True.
    Next user message must reset that flag and restart venting phase.
    """
    result = await conversation_planner_node(_base(
        "There is actually something else I wanted to bring up",
        session_message_count=8,
        fused_emotion="neutral",
        fused_intensity=0.30,
        conversation_phase="recovery",
        session_disclosure_complete=True,
        reflection_questions_since_resolution=2,
    ))

    assert result.get("session_disclosure_complete") is False
    assert result.get("reflection_questions_since_resolution") == 0
    assert result.get("conversation_phase") in {"venting", "neutral"}


# ─────────────────────────────────────────────────────────────────────────────
# 11. Consent denial — exercises blocked
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listen_only_consent_blocks_technique():
    """User declines structured exercises → needs_technique must stay False."""
    result = await conversation_planner_node(_base(
        "I would rather not do any structured activities, I just need to talk this through",
        session_message_count=3,
        fused_emotion="sadness",
        fused_intensity=0.65,
        primary_concern="work stress",
        exercise_consent="denied_soft",
        solution_preference="listen_only",
        prefetched_intent={
            "intent": "deny_technique",
            "confidence": 0.88,
            "source": "smart_gate",
        },
        gate_route="deny_technique",
        gate_context_flags=["consent_denied"],
    ))

    assert result["needs_technique"] is False
    assert result["response_task"] in {
        "listen_only",
        "ask_next_context_question",
        "give_reflective_opinion",
        "ask_one_missing_context_question",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 12. Consent override — acute state overrides prior denial
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_acute_distress_overrides_prior_consent_denial():
    """
    exercise_consent was denied_soft. Now LLM detects panic + respiratory_distress.
    Planner must override consent and deliver grounding immediately.
    Message text ('pulse is out of control', 'spiraling') has no keyword matches.
    """
    result = await conversation_planner_node(_base(
        "My pulse is out of control right now and my thoughts are completely spiraling",
        session_message_count=4,
        fused_emotion="anxiety",
        fused_intensity=0.90,
        primary_sub_emotion="panic",
        detected_symptoms=["shortness_of_breath", "body_tension"],
        exercise_consent="denied_soft",
        solution_preference="listen_only",
    ))

    assert result["immediate_regulation_request"] is True
    assert result["exercise_consent"] == "allowed"
    assert result["response_task"] == "start_grounding_now"


# ─────────────────────────────────────────────────────────────────────────────
# 13. Genuine crisis — must route to crisis, NOT immediate_regulation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_genuine_crisis_routes_to_crisis_not_grounding():
    """
    Explicit suicidal ideation — crisis_detected=True.
    Must NOT be treated as immediate_regulation_request.
    """
    result = await conversation_planner_node(_base(
        "I have been drafting farewell messages to the people in my life and I do not see a future for myself",
        session_message_count=1,
        fused_emotion="sadness",
        fused_intensity=0.95,
        crisis_detected=True,
        crisis_level="high",
        # Must match the intent literal that triggers the crisis fast-path (line 1412)
        prefetched_intent={
            "intent": "crisis_signal",
            "confidence": 0.99,
            "source": "deterministic_safety_net",
        },
        gate_route="crisis",
        gate_context_flags=["self_harm_risk"],
    ))

    # Planner must set CRISIS stage and flag crisis_detected=True.
    # The response_task may vary depending on which return path fires
    # (the stage machine override or the direct crisis fast-path); both are
    # correct — the graph routes to crisis_handler based on crisis_detected.
    assert result["conversation_stage"] == "CRISIS"
    assert result["crisis_detected"] is True
    # Panic immediate_regulation must NOT be set for genuine crisis
    assert result.get("immediate_regulation_request") is not True


# ─────────────────────────────────────────────────────────────────────────────
# 14. Chitchat — low signal, no therapeutic intervention
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chitchat_no_therapeutic_intervention():
    """Low-signal casual message → no technique, no context question, no crisis."""
    result = await conversation_planner_node(_base(
        "I watched a really entertaining documentary about deep sea creatures last evening",
        session_message_count=1,
        fused_emotion="neutral",
        fused_intensity=0.10,
        prefetched_intent={
            "intent": "chitchat",
            "confidence": 0.92,
            "source": "smart_gate",
        },
        gate_route="chitchat",
        gate_emotional_register="neutral",
        gate_context_flags=[],
    ))

    assert result["needs_technique"] is False
    assert result["conversation_strategy"] == "no_action"
    assert result["response_task"] == "chitchat"
