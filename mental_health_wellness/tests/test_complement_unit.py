"""
Offline unit tests for the series-complement logic (no live LLM / no server).
Verifies the deterministic routing/promotion pieces added for consistent
two-exercise delivery.
"""

import sys
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mental_health_wellness.nodes.optimized_response_generator import (
    _build_complement_offer_line,
    _maybe_append_complement_offer,
)
from mental_health_wellness.pipeline.conversation_planner_node import _final_response_task
from mental_health_wellness.pipeline.technique_selector_node import (
    select_technique,
    _describe_complement_signal,
)

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \033[92m✅ {name}\033[0m")
    else:
        FAIL += 1
        print(f"  \033[91m❌ {name}\033[0m")


COMP = {"name": "Cognitive Restructuring", "category": "CBT"}


def test_signal_phrases():
    print("\n— _describe_complement_signal —")
    s1 = _describe_complement_signal(COMP, {"detected_contexts": ["teacher_conflict"]})
    check("context tag → teacher phrase", "teacher" in s1.lower())
    s2 = _describe_complement_signal(COMP, {"secondary_sub_emotions": ["rumination"]})
    check("secondary emotion → looping thoughts", "thought" in s2.lower())
    s3 = _describe_complement_signal(COMP, {})  # category fallback (CBT)
    check("empty state → CBT fallback phrase", "thought" in s3.lower())


def test_offer_line():
    print("\n— _build_complement_offer_line —")
    line = _build_complement_offer_line(COMP, "the feeling of injustice")
    check("names the technique", "Cognitive Restructuring" in line)
    check("names the signal", "injustice" in line)
    check("empty when no complement", _build_complement_offer_line(None, "x") == "")


def test_append_guard():
    print("\n— _maybe_append_complement_offer —")
    base = "Here are your breathing steps. **Steps:**\n1. Inhale\n2. Exhale"

    out = _maybe_append_complement_offer(
        base, response_task="start_grounding_now",
        pending_complement=COMP, pending_complement_signal="the injustice",
        primary_delivered=True,
    )
    check("appends on start_grounding_now + delivered", "Cognitive Restructuring" in out and len(out) > len(base))

    out2 = _maybe_append_complement_offer(
        base, response_task="ask_next_context_question",
        pending_complement=COMP, pending_complement_signal="x", primary_delivered=True,
    )
    check("skips when task != start_grounding_now", out2 == base)

    out3 = _maybe_append_complement_offer(
        base, response_task="start_grounding_now",
        pending_complement=COMP, pending_complement_signal="x", primary_delivered=False,
    )
    check("skips when primary not delivered", out3 == base)

    already = base + "\n\nI also have **Cognitive Restructuring** ready."
    out4 = _maybe_append_complement_offer(
        already, response_task="start_grounding_now",
        pending_complement=COMP, pending_complement_signal="x", primary_delivered=True,
    )
    check("no duplicate when name already present", out4 == already)


def test_final_task_passthrough():
    print("\n— _final_response_task passthrough —")
    # intent=accept_technique would normally → continue_active_technique;
    # the offer_complement_technique resolver_task must win.
    t = _final_response_task("accept_technique", "suggest_technique", True,
                             resolver_task="offer_complement_technique")
    check("offer_complement_technique survives accept_technique", t == "offer_complement_technique")
    t2 = _final_response_task("accept_technique", "suggest_technique", True)
    check("plain accept_technique → continue_active_technique", t2 == "continue_active_technique")


def test_selector_promotion():
    print("\n— select_technique complement promotion (no DB) —")
    state = {
        "session_id": "unit-test",
        "user_id": "unit-user",
        "needs_technique": True,
        "response_task": "offer_complement_technique",
        "conversation_strategy": "suggest_technique",
        "conversation_stage": "INTERVENTION",
        "intent": "accept_technique",
        "messages": [],
        "fused_emotion": "anxiety",
        "fused_intensity": 0.8,
        "pending_complement_technique": COMP,
        "pending_complement_signal": "the feeling of injustice",
        "alternative_techniques": [COMP],
    }
    out = asyncio.run(select_technique(state))
    check("promotes queued complement as recommended_technique",
          (out.get("recommended_technique") or {}).get("name") == "Cognitive Restructuring")
    check("clears pending_complement_technique after promotion",
          out.get("pending_complement_technique") is None)
    check("single plan mode after promotion", out.get("technique_plan_mode") == "single")


if __name__ == "__main__":
    print("\033[1m\n══ Series Complement — Offline Unit Tests ══\033[0m")
    test_signal_phrases()
    test_offer_line()
    test_append_guard()
    test_final_task_passthrough()
    test_selector_promotion()
    print(f"\n\033[1mResults: {PASS} passed, {FAIL} failed\033[0m\n")
    sys.exit(1 if FAIL else 0)
