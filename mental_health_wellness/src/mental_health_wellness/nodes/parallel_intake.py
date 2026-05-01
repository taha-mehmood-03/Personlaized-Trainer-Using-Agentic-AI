"""
Parallel Intake Node — SentiMind v5.3 Latency Optimization

Runs FOUR tasks concurrently via asyncio.gather:
  1. Crisis Pre-Screener   — ELECTRA + optional Groq 70b
  2. Intake Node           — DB context + ChromaDB memory
  3. Mood Analyzer Node    — DistilBERT local inference
  4. Intent Pre-Check      — Groq 8b intent (now truly async)

WHY THIS IS SAFE:
  All four tasks only READ from the initial state (messages, user_id, session_id)
  and write to COMPLETELY DISJOINT state keys:
    - crisis_screener  → crisis_detected, crisis_level, crisis_pre_screened
    - intake_node      → is_new_user, session_count, memory_context, chat_history, ...
    - mood_analyzer    → emotion, sentiment, intensity, confidence
    - intent_pre_check → prefetched_intent

BEFORE v5.2 (sequential ~700ms):
  START → crisis_screener (400ms) → intake (300ms) → mood_analyzer (400ms) → ...
  then in conversation_planner: intent_check (800–1500ms) — ON CRITICAL PATH

AFTER v5.2 (parallel intake + serial mood ~400ms + serial intent ~1000ms):
  START → parallel_intake [crisis||intake] (400ms) → mood → ... → planner → intent_check

AFTER v5.3 (4-way parallel ~max(400,300,400,800) = ~800ms, intent OFF critical path):
  START → parallel_intake_v2 [crisis||intake||mood||intent] (~800ms) → emotion_fusion
  conversation_planner uses prefetched_intent → ZERO extra LLM call

  Net saving over v5.2: ~800–1500ms (intent check moved off critical path)
  Net saving over v5.1: ~800–1500ms (intent) + ~400ms (mood parallelised) = ~1.2–1.9s

v5.3 PERF BONUS:
  ELECTRA CPU inference is now offloaded to a ThreadPoolExecutor so that the
  ~200ms forward pass doesn't stall the event loop and lets the other three
  coroutines (intake DB queries, mood DistilBERT, intent Groq call) make
  genuine concurrent progress during that window.
"""

import asyncio
from ..agent.state import MentalHealthState


async def _intent_pre_check_task(message: str, recent_context: str = "") -> dict:
    """
    Calls llm_intent_pre_check asynchronously.
    """
    try:
        from ..llm.llm_classifier import llm_intent_pre_check
        return await llm_intent_pre_check(message, recent_context)
    except Exception as e:
        print(f"[PARALLEL_INTAKE] ⚠️ Intent prefetch failed: {str(e)[:80]} — using venting fallback")
        return {"intent": "venting", "confidence": 0.0}


async def run_parallel_intake(state: MentalHealthState) -> dict:
    """
    v5.3: Run crisis screening, context loading, mood analysis, and intent
    pre-check CONCURRENTLY via asyncio.gather (4-way parallel).

    All four tasks read from the initial state only and write to disjoint keys.
    The downstream conditional edge uses crisis_detected to route; emotion/
    sentiment/intensity are now available immediately after this node (no
    separate mood_analyzer step in the graph).

    Returns: merged dict across all 4 nodes' outputs.
    """
    from ..agent.graph import screen_for_crisis
    from ..nodes.intake import load_user_context
    from ..nodes.mood_analyzer_node import analyze_mood

    messages = state.get("messages", [])
    current_message = messages[-1].content if messages else ""
    
    recent_context = ""
    if len(messages) > 1:
        # Get up to the last 3 messages before the current one
        ctx_msgs = messages[-4:-1]
        lines = []
        for m in ctx_msgs:
            role = "User" if getattr(m, "type", "") == "human" else "System"
            content = getattr(m, "content", "")
            lines.append(f"{role}: {content}")
        recent_context = "\n".join(lines)

    print("  ├── screen_for_crisis     (ELECTRA + optional Groq 70b)")
    print("  ├── load_user_context     (DB context + ChromaDB memory)")
    print("  ├── analyze_mood          (DistilBERT local ML)")
    print("  ├── intent_pre_check      (Groq 8b — async, off critical path)")
    if state.get("audio_file_path") or state.get("audio_bytes"):
        print("  └── preprocess_voice_input (Wav2Vec2 + OpenSMILE)")

    from ..nodes.voice_preprocessing import preprocess_voice_input

    tasks = [
        screen_for_crisis(state),
        load_user_context(state),
        analyze_mood(state),
        _intent_pre_check_task(current_message, recent_context)
    ]
    
    if state.get("audio_file_path") or state.get("audio_bytes"):
        tasks.append(preprocess_voice_input(state))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    crisis_result = results[0]
    intake_result = results[1]
    mood_result = results[2]
    intent_result = results[3]
    voice_result = results[4] if len(results) > 4 else None

    merged = {}

    # ── Crisis screener ────────────────────────────────────────────────────────
    if isinstance(crisis_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE] ⚠️ Crisis screener failed: {str(crisis_result)[:100]}")
        merged.update({
            "crisis_detected": False,
            "crisis_level": "none",
            "crisis_pre_screened": False,
        })
    else:
        merged.update(crisis_result)

    # ── Intake node ────────────────────────────────────────────────────────────
    if isinstance(intake_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE] ⚠️ Intake failed: {str(intake_result)[:100]}")
        merged.update({
            "is_new_user": True,
            "session_count": 0,
            "most_common_emotion": "neutral",
            "historical_mood": "neutral",
            "user_preferences": {},
            "chat_history": [],
            "memory_context": "",
            "context_ready": False,
            "messages": state.get("messages", []),
        })
    else:
        merged.update(intake_result)

    # ── Mood analyzer ─────────────────────────────────────────────────────────
    if isinstance(mood_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE] ⚠️ Mood analyzer failed: {str(mood_result)[:100]}")
        merged.update({
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.0,
        })
    else:
        merged.update(mood_result)
        _em = mood_result.get("emotion", "neutral")
        _it = mood_result.get("intensity", 0.5)
        print(f"[NODE: PARALLEL_INTAKE] 🎯 Mood pre-computed: {_em} ({_it:.0%})")

    # ── Intent pre-check ───────────────────────────────────────────────────────
    if isinstance(intent_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE] ⚠️ Intent prefetch failed: {str(intent_result)[:100]}")
        merged["prefetched_intent"] = None
    elif isinstance(intent_result, dict):
        merged["prefetched_intent"] = intent_result
        print(f"[NODE: PARALLEL_INTAKE] 🎯 Intent pre-computed: "
              f"{intent_result.get('intent')} ({intent_result.get('confidence', 0):.0%})")
    else:
        merged["prefetched_intent"] = None

    # ── Voice preprocessing ───────────────────────────────────────────────────
    if voice_result is not None:
        if isinstance(voice_result, Exception):
            print(f"[NODE: PARALLEL_INTAKE] ⚠️ Voice preprocessing failed: {str(voice_result)[:100]}")
        else:
            merged.update(voice_result)
            if voice_result.get("transcription") and not current_message.strip():
                # If there was no text passed initially, use the transcription directly.
                print(f"[NODE: PARALLEL_INTAKE] 🎯 Used voice STT override for message")

    crisis_flag = merged.get("crisis_detected", False)
    crisis_level = merged.get("crisis_level", "none")
    print(f"[NODE: PARALLEL_INTAKE] ✅ Complete | "
          f"Crisis: {crisis_flag} ({crisis_level}) | "
          f"Context: {merged.get('context_ready', False)} | "
          f"Mood: {merged.get('emotion', '?')} | "
          f"Voice: {merged.get('voice_features', {}).get('emotion', '?') if merged.get('voice_features') else 'None'} | "
          f"Intent: {merged.get('prefetched_intent', {}).get('intent', '?')}")

    return merged
