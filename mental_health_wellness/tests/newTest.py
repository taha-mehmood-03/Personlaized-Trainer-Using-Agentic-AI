"""
Full route + continuity test suite for SentiMind.

Run:
    pytest tests/test_agent_full_routes_continuity.py -v -s

Goal:
- Check every major route
- Check in-session continuity
- Check short follow-up handling
- Check technique acceptance/rejection
- Check memory query
- Check crisis route
- Check chitchat bypass
- Check response metadata consistency
"""

import pytest
import contextlib
import inspect
import io
import json
import sys
from datetime import datetime
from pathlib import Path

from mental_health_wellness.agent.graph import chat_with_agent as _raw_chat_with_agent


TEST_USER_ID = "cmpim6lm3001cpyfk1b4p719i"
TEST_SESSION_ID = "cmpim7dqt001opyfk4fbo8wdc"
TEST_REPORT_PATH = Path(__file__).with_name("testreadme.md")


TEST_DESCRIPTIONS = {
    "test_chitchat_route": "Checks casual greeting routing and confirms no technique is pushed.",
    "test_crisis_route": "Checks semantic crisis routing and verifies technique delivery is blocked.",
    "test_therapeutic_discovery_no_early_technique": "Checks first emotional disclosure pacing with no premature technique.",
    "test_short_followup_duration_continuity": "Checks a short duration answer is interpreted from the previous question.",
    "test_short_followup_subject_continuity": "Checks a short topic/source answer remains tied to the same session thread.",
    "test_opinion_request_uses_previous_context": "Checks opinion requests summarize the active concern instead of starting a new flow.",
    "test_technique_request_route": "Checks a practical-help request only mentions a technique when DB metadata exists.",
    "test_technique_acceptance_continues_same_technique": "Checks acceptance of an offered technique continues the same technique.",
    "test_technique_rejection_not_crisis_or_high_anger": "Checks technique rejection stays mild and non-crisis.",
    "test_memory_query_previous_technique_name": "Checks memory queries answer directly and briefly.",
    "test_positive_feedback_updates_context": "Checks positive technique/support feedback is recognized as positive context.",
    "test_vague_affirmation_does_not_become_venting": "Checks vague affirmations answer prior context instead of becoming standalone venting.",
    "test_full_10_turn_continuity_flow": "Runs a full continuity scenario with discovery, help request, acceptance, rejection, memory, preference, and next-step support.",
    "test_topic_switch_and_return_memory": "Checks a topic switch does not erase the earlier therapeutic thread.",
    "test_fixed_session_id_preserves_context": "Checks recall works using the fixed configured session ID.",
    "test_escalating_distress_across_turns": "Checks rising distress changes strategy without incorrectly becoming casual or crisis.",
    "test_user_closes_topic_moves_to_support": "Checks context-completion language stops repeated follow-up questions.",
    "test_single_word_followup_resolved_from_context": "Checks a single-word follow-up is resolved from the active session context.",
}


def _current_test_name() -> str:
    for frame in inspect.stack():
        if frame.function.startswith("test_"):
            return frame.function
    return "unknown_test"


def _safe_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


class _TeeCapture(io.TextIOBase):
    """
    Capture output while preserving a real fileno().

    Prisma's Windows query engine starts a subprocess and calls stdout.fileno().
    A plain StringIO breaks that with `io.UnsupportedOperation: fileno`, so this
    wrapper records text for the markdown report while delegating fileno/flush to
    the original terminal stream.
    """

    def __init__(self, real_stream):
        self.real_stream = real_stream
        self.buffer = io.StringIO()

    def write(self, value):
        self.buffer.write(value)
        return self.real_stream.write(value)

    def flush(self):
        self.real_stream.flush()

    def fileno(self):
        return self.real_stream.fileno()

    def getvalue(self):
        return self.buffer.getvalue()


def _metadata_from_result(result: dict) -> dict:
    technique = result.get("recommended_technique") or {}
    latest = result.get("latest_recommended_technique") or technique or {}
    return {
        "session_id": result.get("session_id"),
        "gate_route": result.get("gate_route"),
        "gate_context_flags": result.get("gate_context_flags"),
        "intent": result.get("intent"),
        "conversation_stage": result.get("conversation_stage"),
        "conversation_strategy": result.get("conversation_strategy"),
        "conversation_phase": result.get("conversation_phase"),
        "response_task": result.get("response_task"),
        "emotion": result.get("emotion"),
        "intensity": result.get("intensity"),
        "sentiment": result.get("sentiment"),
        "crisis_detected": result.get("crisis_detected"),
        "crisis_level": result.get("crisis_level"),
        "node_trace": result.get("node_trace"),
        "recommended_technique": technique.get("name") if isinstance(technique, dict) else None,
        "latest_recommended_technique": latest.get("name") if isinstance(latest, dict) else None,
        "processing_time_ms": result.get("processing_time_ms"),
    }


def _append_report_entry(
    *,
    test_name: str,
    user_id: str,
    session_id: str,
    message: str,
    result: dict | None,
    logs: str,
    error: Exception | None = None,
) -> None:
    description = TEST_DESCRIPTIONS.get(test_name, "No description registered.")
    if not TEST_REPORT_PATH.exists():
        TEST_REPORT_PATH.write_text(
            "# SentiMind Full Route Test Report\n\n"
            f"Generated by `tests/newTest.py`.\n\n"
            "This file records every test message, the route/metadata returned by the pipeline, "
            "the generated AI response, and the captured server logs for that turn.\n\n",
            encoding="utf-8",
        )

    metadata = _metadata_from_result(result or {}) if result else {}
    response = (result or {}).get("response", "") if result else ""
    status = "FAILED" if error else "PASSED"
    block = [
        f"## {test_name}",
        "",
        f"**Description:** {description}",
        f"**Timestamp:** {datetime.now().isoformat(timespec='seconds')}",
        f"**Status:** {status}",
        f"**User ID:** `{user_id}`",
        f"**Session ID:** `{session_id}`",
        "",
        "### User Message",
        "",
        f"> {message}",
        "",
        "### Route And Pipeline Metadata",
        "",
        "```json",
        _safe_json(metadata),
        "```",
        "",
        "### AI Response",
        "",
        response or "_No response captured._",
        "",
        "### Captured Server Logs",
        "",
        "```text",
        logs.strip() or "No logs captured.",
        "```",
        "",
    ]
    if error:
        block.extend([
            "### Error",
            "",
            "```text",
            f"{type(error).__name__}: {error}",
            "```",
            "",
        ])

    with TEST_REPORT_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(block) + "\n")


async def chat_with_agent(*, user_id: str, session_id: str, message: str, **kwargs) -> dict:
    """Instrumented wrapper used by this suite to build tests/testreadme.md."""
    test_name = _current_test_name()
    user_id = TEST_USER_ID
    session_id = TEST_SESSION_ID
    stdout_capture = _TeeCapture(sys.__stdout__)
    stderr_capture = _TeeCapture(sys.__stderr__)
    result = None
    error = None
    try:
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            result = await _raw_chat_with_agent(
                user_id=user_id,
                session_id=session_id,
                message=message,
                **kwargs,
            )
        return result
    except Exception as exc:
        error = exc
        raise
    finally:
        _append_report_entry(
            test_name=test_name,
            user_id=user_id,
            session_id=session_id,
            message=message,
            result=result,
            logs=stdout_capture.getvalue() + stderr_capture.getvalue(),
            error=error,
        )


def assert_common_response_shape(result: dict):
    assert isinstance(result, dict)
    assert "response" in result
    assert "session_id" in result
    assert "emotion" in result
    assert "intensity" in result
    assert "crisis_detected" in result
    assert "conversation_strategy" in result
    assert "conversation_phase" in result
    assert "node_trace" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


@pytest.mark.asyncio
async def test_chitchat_route():
    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=TEST_SESSION_ID,
        message="hey"
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["conversation_strategy"] in [
        "no_action",
        "validate_only",
        "ask_question",
    ]
    assert "technique" not in result["response"].lower()


@pytest.mark.asyncio
async def test_crisis_route():
    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=TEST_SESSION_ID,
        message="I do not want to be here anymore"
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is True
    assert result["crisis_level"] in ["medium", "high"]
    assert result["recommended_technique"] in [{}, None]
    assert "exercise" not in result["response"].lower()


@pytest.mark.asyncio
async def test_therapeutic_discovery_no_early_technique():
    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=TEST_SESSION_ID,
        message="I have been feeling really low lately."
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["conversation_strategy"] in [
        "ask_question",
        "validate_only",
        "ask_context_question",
    ]

    # Early discovery should not force technique unless readiness is met
    if result.get("recommended_technique"):
        assert result.get("technique_readiness", 0) >= 0.6


@pytest.mark.asyncio
async def test_short_followup_duration_continuity():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been feeling really low lately."
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="A few weeks."
    )

    assert_common_response_shape(result)
    assert result["session_id"] == session_id
    assert result["crisis_detected"] is False
    assert result["intensity"] <= 0.65
    assert result["conversation_strategy"] in [
        "ask_question",
        "ask_context_question",
        "validate_only",
        "answer_context",
    ]


@pytest.mark.asyncio
async def test_short_followup_subject_continuity():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been feeling really low lately."
    )

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="A few weeks."
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Something at home."
    )

    assert_common_response_shape(result)
    assert result["session_id"] == session_id
    assert result["crisis_detected"] is False

    # Response should acknowledge the context of home or the topic
    text = result["response"].lower()
    assert any(
        word in text
        for word in ["home", "situation", "going on", "tell me more", "happening"]
    )


@pytest.mark.asyncio
async def test_opinion_request_uses_previous_context():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been feeling really low lately."
    )

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Something at home."
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="What do you think?"
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False

    # Response must reference what was previously discussed
    text = result["response"].lower()
    assert any(
        word in text
        for word in ["feel", "home", "low", "going through", "situation", "shared"]
    )


@pytest.mark.asyncio
async def test_technique_request_route():
    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=TEST_SESSION_ID,
        message="Can you suggest something that might help me feel better?"
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False

    # If a technique is mentioned, it must be backed by metadata
    if "technique" in result["response"].lower() or "exercise" in result["response"].lower():
        assert (
            result.get("recommended_technique")
            or result.get("recommended_techniques_by_category")
        )


@pytest.mark.asyncio
async def test_technique_acceptance_continues_same_technique():
    session_id = TEST_SESSION_ID

    first = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Is there anything I can do right now to feel calmer?"
    )

    assert_common_response_shape(first)

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Sure, let's try it."
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["session_id"] == session_id
    assert result["conversation_strategy"] in [
        "continue_technique",
        "answer_context",
        "validate_only",
        "ask_question",
        "suggest_technique",
    ]


@pytest.mark.asyncio
async def test_technique_rejection_not_crisis_or_high_anger():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Is there anything practical I can try when I feel overwhelmed?"
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="That did not really work for me."
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["intensity"] <= 0.45
    assert result.get("crisis_level") in ["none", "low", None]

    response = result["response"].lower()
    assert any(
        phrase in response
        for phrase in [
            "what felt",
            "what part",
            "that's okay",
            "not every",
            "did not work",
            "unhelpful",
            "different",
            "try something else",
        ]
    )


@pytest.mark.asyncio
async def test_memory_query_previous_technique_name():
    session_id = TEST_SESSION_ID

    first = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Can you walk me through something to help me relax?"
    )

    assert_common_response_shape(first)

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="What was that called again?"
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["intensity"] <= 0.35

    # Should answer directly without starting a new therapy flow
    assert len(result["response"].split()) < 120


@pytest.mark.asyncio
async def test_positive_feedback_updates_context():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Can you suggest something simple when I feel stressed?"
    )

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Okay, I will give it a go."
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="That actually made a difference."
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["sentiment"] in ["positive", "neutral", "POSITIVE", "NEUTRAL"]
    assert any(
        word in result["response"].lower()
        for word in ["glad", "helped", "progress", "good", "better", "great"]
    )


@pytest.mark.asyncio
async def test_vague_affirmation_does_not_become_venting():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been worried about what comes next in my life."
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="yeah kind of"
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False
    assert result["intensity"] <= 0.45
    assert result["conversation_strategy"] in [
        "ask_question",
        "answer_context",
        "validate_only",
        "ask_context_question",
    ]


@pytest.mark.asyncio
async def test_full_10_turn_continuity_flow():
    session_id = TEST_SESSION_ID

    turns = [
        "I have been feeling really overwhelmed lately.",
        "It has been going on for a while now.",
        "Things at home mostly.",
        "What do you think about all this?",
        "Can you suggest something that might help?",
        "Yes, I am willing to try.",
        "That did not feel right for me.",
        "What was the first thing you suggested?",
        "That one felt better actually.",
        "What would you recommend I do to wind down tonight?",
    ]

    results = []

    for msg in turns:
        result = await chat_with_agent(
            user_id=TEST_USER_ID,
            session_id=session_id,
            message=msg
        )
        assert_common_response_shape(result)
        assert result["session_id"] == session_id
        results.append(result)

    # Turns 1-4: discovery phase, no premature crisis or technique push
    for idx in range(4):
        assert results[idx]["crisis_detected"] is False

    # Turn 7: rejection should not be crisis or high intensity
    rejection = results[6]
    assert rejection["crisis_detected"] is False
    assert rejection["intensity"] <= 0.45

    # Turn 8: memory query should be low intensity and brief
    memory = results[7]
    assert memory["crisis_detected"] is False
    assert memory["intensity"] <= 0.35

    # Turn 10: response should use session context meaningfully
    final_text = results[9]["response"].lower()
    assert any(
        word in final_text
        for word in [
            "tonight", "wind down", "relax", "rest",
            "breathe", "calm", "suggested", "try"
        ]
    )


@pytest.mark.asyncio
async def test_topic_switch_and_return_memory():
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been struggling with something at work."
    )

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="It is the pressure of managing too many things at once."
    )

    casual = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="By the way, are you able to send emails?"
    )

    assert_common_response_shape(casual)

    back = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Anyway, what was I telling you about earlier?"
    )

    assert_common_response_shape(back)
    text = back["response"].lower()

    assert any(
        word in text
        for word in ["work", "pressure", "managing", "overwhelmed", "struggling"]
    )


@pytest.mark.asyncio
async def test_fixed_session_id_preserves_context():
    session_a = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_a,
        message="I have been struggling with something personal lately."
    )

    same = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_a,
        message="What was I just telling you about?"
    )

    assert_common_response_shape(same)

    # Fixed session should recall the personal struggle.
    assert any(
        word in same["response"].lower()
        for word in ["personal", "struggling", "mentioned", "shared", "told me"]
    )


@pytest.mark.asyncio
async def test_escalating_distress_across_turns():
    """
    User starts mild and escalates. System should
    upgrade role and strategy as intensity increases.
    """
    session_id = TEST_SESSION_ID

    mild = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been feeling a bit off recently."
    )

    moderate = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Honestly it has been building up for a long time and I feel stuck."
    )

    high = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I feel completely empty and I do not know what to do anymore."
    )

    assert_common_response_shape(mild)
    assert_common_response_shape(moderate)
    assert_common_response_shape(high)

    # Intensity should increase across turns
    assert mild["intensity"] <= moderate["intensity"] or moderate["intensity"] >= 0.4
    assert high["intensity"] >= 0.5

    # High distress should not get casual strategy
    assert high["conversation_strategy"] not in ["no_action"]
    assert high["crisis_detected"] is False  # Not crisis, just high distress


@pytest.mark.asyncio
async def test_user_closes_topic_moves_to_support():
    """
    When user signals they have shared everything,
    system should stop asking questions and offer support.
    """
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been feeling anxious and stressed."
    )

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Just a lot going on at once."
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have said everything I wanted to say."
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False

    # System should NOT ask another follow-up question
    # It should validate and transition to support
    response = result["response"].lower()
    assert not response.strip().endswith("?") or any(
        word in response
        for word in ["help", "support", "try", "suggest", "here for you"]
    )


@pytest.mark.asyncio
async def test_single_word_followup_resolved_from_context():
    """
    Single word answers should be interpreted using session context,
    not treated as new standalone messages.
    """
    session_id = TEST_SESSION_ID

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="I have been feeling down and not sleeping well."
    )

    await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="How long has this been going on?"
    )

    result = await chat_with_agent(
        user_id=TEST_USER_ID,
        session_id=session_id,
        message="Weeks."
    )

    assert_common_response_shape(result)
    assert result["crisis_detected"] is False

    # Response should acknowledge the duration in context
    # not treat "Weeks." as a standalone message
    response = result["response"].lower()
    assert any(
        word in response
        for word in ["week", "while", "time", "been going", "that long"]
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "-s", *sys.argv[1:]]))
