import pytest
from langchain_core.messages import AIMessage, HumanMessage

from mental_health_wellness.pipeline.consent_parser import parse_consent_and_suppression
from mental_health_wellness.nodes.conversation_context_resolver import resolve_conversation_context
from mental_health_wellness.pipeline.conversation_planner_node import conversation_planner_node
from mental_health_wellness.nodes.optimized_response_generator import _build_structured_context
import mental_health_wellness.pipeline.technique_selector_node as technique_selector_module
from mental_health_wellness.pipeline.technique_selector_node import _build_technique_need_query
from mental_health_wellness.pipeline.technique_selector_node import select_technique
from mental_health_wellness.utils.turn_signals import is_explicit_exercise_request


@pytest.mark.asyncio
async def test_neutral_context_complete_does_not_trigger_exercise():
    state = {
        "messages": [
            HumanMessage(content="The app has felt boring lately."),
            AIMessage(content="What changed that made it feel boring?"),
            HumanMessage(content="Mostly the rules changed and now it feels repetitive."),
        ],
        "session_message_count": 3,
        "fused_emotion": "neutral",
        "fused_intensity": 0.2,
        "emotional_trend": "stable",
        "crisis_detected": False,
        "prefetched_intent": {
            "intent": "contextual_followup",
            "confidence": 0.88,
            "source": "smart_gate",
        },
        "gate_route": "contextual_followup",
        "gate_emotional_register": "complaint",
        "gate_context_flags": ["elaborating_context", "answering_previous_topic"],
        "resolved_user_act": {
            "intent": "contextual_followup",
            "context_flags": ["continuation", "answering_previous_question", "pain_point_answer"],
            "referent": "last_assistant_question",
            "response_task": "ask_next_context_question",
            "expected_answer_type": "pain_point",
            "slot_updates": {
                "primary_concern": "boredom with app rules",
                "triggering_context": "the rules changed",
                "functional_impact": "it feels repetitive",
            },
        },
        "question_count_since_technique": 2,
    }

    result = await conversation_planner_node(state)

    assert result["intent"] == "contextual_followup"
    assert result["needs_technique"] is False
    assert result["conversation_strategy"] == "encourage_reflection"
    assert result["response_task"] == "summarize_known_context"
    assert "context_complete" in result["gate_context_flags"]
    assert "followup_limit_reached" in result["gate_context_flags"]
    assert "therapeutic_action_ready" not in result["gate_context_flags"]


@pytest.mark.asyncio
async def test_selector_defends_against_low_signal_contextual_technique():
    result = await select_technique(
        {
            "messages": [HumanMessage(content="Mostly the rules changed and now it feels repetitive.")],
            "conversation_strategy": "suggest_technique",
            "conversation_stage": "INTERVENTION",
            "needs_technique": True,
            "intent": "contextual_followup",
            "gate_route": "contextual_followup",
            "gate_context_flags": ["context_complete", "followup_limit_reached"],
            "fused_emotion": "neutral",
            "fused_intensity": 0.2,
        }
    )

    assert result["recommended_technique"] == {}
    assert result["recommended_techniques_by_category"] == {}
    assert result["alternative_techniques"] == []


def test_structured_context_injects_solution_preference():
    context = _build_structured_context(
        emotion="sadness",
        intensity=0.5,
        sentiment="negative",
        technique={},
        agent_role="coach",
        is_new_user=False,
        user_message="I just want you to listen.",
        needs_technique=False,
        exercise_consent="denied_soft",
        solution_preference="listen_only",
    )

    assert "- Exercise consent: denied_soft" in context
    assert "- Solution preference: listen_only" in context


def test_structured_prompt_does_not_reask_permission_for_explicit_exercise_request():
    context = _build_structured_context(
        emotion="anxiety",
        intensity=0.7,
        sentiment="negative",
        technique={"name": "Worry Time", "category": "CBT"},
        agent_role="coach",
        is_new_user=False,
        user_message="Please get on with it and give me the exercise.",
        needs_technique=True,
        current_intent="technique_request",
        response_task="offer_one_technique",
        solution_preference="exercise_requested",
        exercise_consent="allowed",
        primary_concern="nighttime overthinking",
        triggering_context="at night",
        functional_impact="stops me from sleeping",
        core_belief="I feel stuck",
    )

    assert "Lifecycle mode: explicit_exercise_requested" in context
    assert "Do not ask permission again" in context
    assert "Begin the first small step" in context


def test_structured_prompt_prevents_repeated_context_question():
    context = _build_structured_context(
        emotion="sadness",
        intensity=0.5,
        sentiment="negative",
        technique={},
        agent_role="coach",
        is_new_user=False,
        user_message="Overthinking.",
        needs_technique=False,
        current_intent="contextual_followup",
        response_task="ask_next_context_question",
        primary_concern="loneliness and overthinking",
        last_assistant_question="What part of that feels hardest to carry today?",
        expected_answer_type="pain_point",
    )

    assert "Ask exactly one focused next question for a missing detail, not a repeated detail" in context
    assert "do not ask that again" in context


def test_bare_later_does_not_create_exercise_denial_without_exercise_context():
    result = parse_consent_and_suppression(
        {
            "messages": [
                AIMessage(content="When did this start feeling worse?"),
                HumanMessage(content="Later, after exams."),
            ],
            "session_message_count": 2,
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert "exercise_consent" not in result
    assert "solution_preference" not in result


def test_soft_refusal_after_technique_offer_sets_listen_only():
    result = parse_consent_and_suppression(
        {
            "messages": [
                AIMessage(content="I have something that might help. Would you like to try it?"),
                HumanMessage(content="Not now, just listen for now."),
            ],
            "session_message_count": 2,
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["exercise_consent"] == "denied_soft"
    assert result["solution_preference"] == "listen_only"


def test_expected_technique_acceptance_yes_sure_allows_exercise():
    result = parse_consent_and_suppression(
        {
            "messages": [
                AIMessage(content="I have something that might help. Would you like me to share it?"),
                HumanMessage(content="Yes sure"),
            ],
            "session_message_count": 4,
            "expected_answer_type": "technique_acceptance",
            "response_task": "ask_permission_before_technique",
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["exercise_consent"] == "allowed"
    assert result["solution_preference"] == "exercise_requested"


def test_technique_need_query_uses_followup_context_not_bare_acceptance():
    query = _build_technique_need_query(
        user_message="Yes sure",
        emotion="anxiety",
        intensity=0.35,
        primary_sub_emotion="anxiety",
        secondary_sub_emotions=["overwhelm"],
        detected_symptoms=["sleep_disturbance"],
        detected_behaviors=["rumination"],
        detected_contexts=["exam_stress"],
        state={
            "primary_concern": "exam anxiety",
            "triggering_context": "upcoming exam tomorrow",
            "functional_impact": "cannot sleep and keeps replaying what could go wrong",
            "core_belief": "I will fail if I do not calm down",
        },
    )

    assert "latest message: Yes sure" not in query
    assert "primary concern: exam anxiety" in query
    assert "triggering context: upcoming exam tomorrow" in query
    assert "symptoms: sleep_disturbance" in query
    assert "behaviors: rumination" in query
    assert "context tags: exam_stress" in query


def test_rich_followup_answer_marks_context_complete_without_new_question():
    result = resolve_conversation_context(
        {
            "messages": [
                HumanMessage(content="I spend most of my time alone listening to music. I feel lonely and anxious."),
                AIMessage(content="What has been the hardest part of it today?"),
                HumanMessage(content="The hardest part has been coping with my overthinking."),
                AIMessage(content="What part of that feels hardest to carry today?"),
                HumanMessage(
                    content=(
                        "I keep overthinking everything at night, it stops me from sleeping "
                        "and I just feel stuck and don't know how to get out of it."
                    )
                ),
            ],
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["intent"] == "contextual_followup"
    assert result["response_task"] == "formulate_and_offer_help"
    assert "context_complete" in result["gate_context_flags"]
    assert "rich_context_answer" in result["gate_context_flags"]
    assert "sleeping" in result["functional_impact"]
    assert "at night" in result["triggering_context"]


def test_thin_followup_answer_keeps_context_question_open():
    result = resolve_conversation_context(
        {
            "messages": [
                HumanMessage(content="I feel lonely and anxious."),
                AIMessage(content="What part of that feels hardest to carry today?"),
                HumanMessage(content="Overthinking."),
            ],
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["intent"] == "contextual_followup"
    assert result["response_task"] == "ask_next_context_question"
    assert "context_complete" not in result["gate_context_flags"]
    assert "rich_context_answer" not in result["gate_context_flags"]


def test_explicit_exercise_request_after_context_is_not_another_followup_question():
    result = resolve_conversation_context(
        {
            "messages": [
                HumanMessage(content="I feel lonely and anxious."),
                AIMessage(content="What part of that feels hardest to carry today?"),
                HumanMessage(content="I keep overthinking at night and it stops me from sleeping."),
                AIMessage(content="We can stay with that and move toward what would help."),
                HumanMessage(content="Please get on with it and give me the exercises."),
            ],
            "primary_concern": "nighttime overthinking and anxiety",
            "triggering_context": "overthinking at night",
            "functional_impact": "it stops me from sleeping",
            "core_belief": "I feel stuck",
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["intent"] == "technique_request"
    assert result["response_task"] == "offer_one_technique"
    assert "explicit_technique_request" in result["gate_context_flags"]
    assert "answering_previous_question" not in result["gate_context_flags"]


def test_explicit_exercise_request_after_permission_offer_accepts_pending_technique():
    result = resolve_conversation_context(
        {
            "messages": [
                HumanMessage(content="I keep overthinking at night and it stops me from sleeping."),
                AIMessage(content="I have something that might help. Would you like me to share it?"),
                HumanMessage(content="Please get on with it and give me the exercise."),
            ],
            "expected_answer_type": "technique_acceptance",
            "response_task": "ask_permission_before_technique",
            "primary_concern": "nighttime overthinking",
            "triggering_context": "at night",
            "functional_impact": "stops me from sleeping",
            "pending_recommended_technique": {"id": "worry-time", "name": "Worry Time", "category": "CBT"},
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["intent"] == "accept_technique"
    assert result["response_task"] == "continue_active_technique"
    assert "accept_technique" in result["gate_context_flags"]
    assert "technique_offer_deferred" not in result["gate_context_flags"]


def test_advice_seeking_is_internal_resolver_intent_not_smart_gate_route():
    result = resolve_conversation_context(
        {
            "messages": [
                HumanMessage(content="I keep overthinking at night and it stops me sleeping."),
                AIMessage(content="What feels most urgent right now?"),
                HumanMessage(content="What should I do now?"),
            ],
            "primary_concern": "nighttime overthinking",
            "triggering_context": "at night",
            "functional_impact": "stops me sleeping",
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["intent"] == "advice_seeking"
    assert result["response_task"] == "ask_next_context_question"
    assert "help_request" in result["gate_context_flags"]


def test_try_something_suggestion_phrase_is_explicit_exercise_request():
    assert is_explicit_exercise_request(
        "Yes please, I really want to try something. What do you suggest?"
    )


@pytest.mark.asyncio
async def test_planner_offers_technique_for_explicit_request_with_context():
    result = await conversation_planner_node(
        {
            "messages": [
                HumanMessage(content="I feel lonely and anxious."),
                AIMessage(content="What part of that feels hardest to carry today?"),
                HumanMessage(content="I keep overthinking at night and it stops me from sleeping."),
                AIMessage(content="We can stay with that and move toward what would help."),
                HumanMessage(content="Please get on with it and give me the exercises."),
            ],
            "session_message_count": 3,
            "fused_emotion": "anxiety",
            "fused_intensity": 0.72,
            "emotional_trend": "stable",
            "crisis_detected": False,
            "exercise_consent": "allowed",
            "solution_preference": "exercise_requested",
            "prefetched_intent": {
                "intent": "technique_request",
                "confidence": 0.92,
                "source": "smart_gate",
            },
            "gate_route": "technique_request",
            "gate_emotional_register": "distress",
            "gate_context_flags": ["explicit_technique_request", "help_request"],
            "resolved_user_act": {
                "intent": "technique_request",
                "context_flags": ["continuation", "explicit_technique_request", "help_request"],
                "referent": "active_concern",
                "response_task": "offer_one_technique",
                "slot_updates": {
                    "primary_concern": "nighttime overthinking and anxiety",
                    "triggering_context": "overthinking at night",
                    "functional_impact": "it stops me from sleeping",
                    "core_belief": "I feel stuck",
                },
            },
            "primary_concern": "nighttime overthinking and anxiety",
            "triggering_context": "overthinking at night",
            "functional_impact": "it stops me from sleeping",
            "core_belief": "I feel stuck",
        }
    )

    assert result["needs_technique"] is True
    assert result["conversation_strategy"] == "suggest_technique"
    assert result["conversation_stage"] == "INTERVENTION"
    assert result["response_task"] == "offer_one_technique"


@pytest.mark.asyncio
async def test_planner_respects_try_something_request_without_extra_context_question():
    result = await conversation_planner_node(
        {
            "messages": [
                HumanMessage(content="I spend most of my time alone and feel lonely."),
                AIMessage(content="When does the loneliness hit the hardest?"),
                HumanMessage(content="It is worst at night and I overthink until I can't sleep."),
                AIMessage(content="What kind of support do you feel you are missing?"),
                HumanMessage(content="Yes please, I really want to try something. What do you suggest?"),
            ],
            "session_message_count": 3,
            "fused_emotion": "anxiety",
            "fused_intensity": 0.68,
            "emotional_trend": "stable",
            "crisis_detected": False,
            "exercise_consent": "allowed",
            "solution_preference": "exercise_requested",
            "prefetched_intent": {
                "intent": "contextual_followup",
                "confidence": 0.74,
                "source": "smart_gate",
            },
            "gate_route": "contextual_followup",
            "gate_emotional_register": "distress",
            "gate_context_flags": ["answering_previous_question"],
            "primary_concern": "loneliness with anxiety and overthinking",
            "triggering_context": "worst at night",
            "functional_impact": "overthinking stops sleep",
            "core_belief": "I feel stuck",
        }
    )

    assert result["needs_technique"] is True
    assert result["conversation_strategy"] == "suggest_technique"
    assert result["conversation_stage"] == "INTERVENTION"
    assert result["response_task"] == "offer_one_technique"


@pytest.mark.asyncio
async def test_planner_asks_context_question_for_bare_exercise_request():
    result = await conversation_planner_node(
        {
            "messages": [HumanMessage(content="Give me an exercise.")],
            "session_message_count": 1,
            "fused_emotion": "neutral",
            "fused_intensity": 0.2,
            "emotional_trend": "stable",
            "crisis_detected": False,
            "exercise_consent": "allowed",
            "solution_preference": "exercise_requested",
            "prefetched_intent": {
                "intent": "technique_request",
                "confidence": 0.9,
                "source": "smart_gate",
            },
            "gate_route": "technique_request",
            "gate_emotional_register": "neutral",
            "gate_context_flags": ["explicit_technique_request", "help_request"],
            "resolved_user_act": {
                "intent": "technique_request",
                "context_flags": ["explicit_technique_request", "help_request"],
                "referent": "active_concern",
                "response_task": "offer_one_technique",
                "slot_updates": {},
            },
        }
    )

    assert result["needs_technique"] is False
    assert result["conversation_strategy"] == "ask_question"
    assert result["conversation_stage"] == "UNDERSTANDING"
    # v13.0: "Give me an exercise." also matches is_solution_requested(), so the
    # SOLUTION_REQUESTED routing block (conversation_planner_node.py) now owns
    # this turn ahead of the older technique_request path. With no emotion,
    # intensity, or problem signal yet, _context_is_enough() is False, so the
    # planner asks a single *targeted* context question (context_missing_reason
    # = "vague_disclosure") instead of the older generic question task.
    assert result["response_task"] == "ask_one_missing_context_question"
    assert result["context_missing_reason"] == "vague_disclosure"


def test_elaboration_after_technique_offer_defers_instead_of_new_disclosure():
    result = resolve_conversation_context(
        {
            "messages": [
                HumanMessage(content="I am anxious about my final exam."),
                AIMessage(content="What happens when you try to study at night?"),
                HumanMessage(content="I cant sleep and keep replaying that I will fail."),
                AIMessage(content="I have something that might help. Would you like me to share it?"),
                HumanMessage(content="Also my chest gets tight and I keep thinking I will disappoint everyone."),
            ],
            "expected_answer_type": "technique_acceptance",
            "response_task": "ask_permission_before_technique",
            "primary_concern": "exam anxiety",
            "concern_duration": "two weeks",
            "triggering_context": "trying to study at night",
            "functional_impact": "cant sleep and keeps replaying failure",
            "active_thread_summary": "exam anxiety; duration: two weeks; context: trying to study at night; impact: cant sleep",
            "pending_recommended_technique": {"id": "worry-time", "name": "Worry Time", "category": "CBT"},
        }
    )

    assert result["intent"] == "contextual_followup"
    assert result["response_task"] == "ask_permission_before_technique"
    assert "technique_offer_deferred" in result["gate_context_flags"]
    assert "new_emotional_disclosure" not in result["gate_context_flags"]
    assert "disappoint everyone" in result["core_belief"]


@pytest.mark.asyncio
async def test_planner_reasks_permission_after_deferred_technique_offer():
    state = {
        "messages": [
            HumanMessage(content="I am anxious about my final exam."),
            AIMessage(content="What happens when you try to study at night?"),
            HumanMessage(content="I cant sleep and keep replaying that I will fail."),
            AIMessage(content="I have something that might help. Would you like me to share it?"),
            HumanMessage(content="Also my chest gets tight and I keep thinking I will disappoint everyone."),
        ],
        "session_message_count": 5,
        "fused_emotion": "anxiety",
        "fused_intensity": 0.72,
        "emotional_trend": "stable",
        "crisis_detected": False,
        "exercise_consent": "unknown",
        "solution_preference": "unknown",
        "prefetched_intent": {
            "intent": "contextual_followup",
            "confidence": 0.88,
            "source": "smart_gate",
        },
        "gate_route": "contextual_followup",
        "gate_emotional_register": "distress",
        "gate_context_flags": ["answering_previous_question", "technique_offer_deferred"],
        "resolved_user_act": {
            "intent": "contextual_followup",
            "context_flags": ["continuation", "answering_previous_question", "technique_offer_deferred"],
            "referent": "active_concern",
            "response_task": "ask_permission_before_technique",
            "expected_answer_type": "technique_acceptance",
            "slot_updates": {
                "primary_concern": "exam anxiety",
                "concern_duration": "two weeks",
                "triggering_context": "trying to study at night",
                "functional_impact": "cant sleep and keeps replaying failure",
                "core_belief": "I will disappoint everyone",
            },
        },
        "primary_concern": "exam anxiety",
        "concern_duration": "two weeks",
        "triggering_context": "trying to study at night",
        "functional_impact": "cant sleep and keeps replaying failure",
        "question_count_since_technique": 2,
        "pending_recommended_technique": {"id": "worry-time", "name": "Worry Time", "category": "CBT"},
    }

    result = await conversation_planner_node(state)

    assert result["intent"] == "contextual_followup"
    assert result["needs_technique"] is True
    assert result["response_task"] == "ask_permission_before_technique"
    assert result["conversation_strategy"] == "suggest_technique"
    assert "technique_offer_deferred" in result["gate_context_flags"]


@pytest.mark.asyncio
async def test_planner_listen_only_blocks_technique_even_when_distressed():
    result = await conversation_planner_node(
        {
            "messages": [
                HumanMessage(content="I am overwhelmed about exams."),
                AIMessage(content="What part feels heaviest?"),
                HumanMessage(content="I keep panicking and I only want to talk."),
            ],
            "session_message_count": 3,
            "fused_emotion": "fear",
            "fused_intensity": 0.82,
            "emotional_trend": "stable",
            "clinical_severity": "severe",
            "crisis_detected": False,
            "exercise_consent": "denied_soft",
            "solution_preference": "listen_only",
            "prefetched_intent": {
                "intent": "therapeutic",
                "confidence": 0.9,
                "source": "smart_gate",
            },
        }
    )

    assert result["needs_technique"] is False
    assert result["conversation_strategy"] != "suggest_technique"
    assert result["response_task"] == "listen_only"


@pytest.mark.asyncio
async def test_selector_does_not_preload_technique_during_permission_check(monkeypatch):
    class FailIfCalledTool:
        async def ainvoke(self, _payload):
            raise AssertionError("recommend_technique should not be called before consent")

    monkeypatch.setattr(
        technique_selector_module,
        "recommend_technique",
        FailIfCalledTool(),
    )

    result = await select_technique(
        {
            "messages": [HumanMessage(content="I feel anxious all the time.")],
            "conversation_strategy": "suggest_technique",
            "conversation_stage": "INTERVENTION",
            "response_task": "ask_permission_before_technique",
            "needs_technique": True,
            "intent": "therapeutic",
            "fused_emotion": "fear",
            "fused_intensity": 0.8,
            "exercise_consent": "unknown",
            "solution_preference": "unknown",
        }
    )

    assert result["recommended_technique"] == {}
    assert result["recommended_techniques_by_category"] == {}
    assert result["alternative_techniques"] == []
