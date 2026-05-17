"""
Parallel Intake Node  SentiMind v5.3 Latency Optimization

Runs FOUR tasks concurrently via asyncio.gather:
  1. Crisis Pre-Screener    OpenRouter Llama 3.3 70B safety LLM
  2. Context Loader         DB context + ChromaDB memory
  3. Mood Analyzer Node     DistilBERT local inference
  4. Intent Pre-Check       Groq 8b intent (now truly async)

WHY THIS IS SAFE:
  All four tasks only READ from the initial state (messages, user_id, session_id)
  and write to COMPLETELY DISJOINT state keys:
    - crisis_screener   crisis_detected, crisis_level, crisis_pre_screened
    - context_loader    is_new_user, session_count, memory_context, chat_history, ...
    - mood_analyzer     emotion, sentiment, intensity, confidence
    - intent_pre_check  prefetched_intent

BEFORE v5.2 (sequential ~700ms):
  START  crisis_screener (400ms)  intake (300ms)  mood_analyzer (400ms)  ...
  then in conversation_planner: intent_check (8001500ms)  ON CRITICAL PATH

AFTER v5.2 (parallel intake + serial mood ~400ms + serial intent ~1000ms):
  START  parallel_intake [crisis||intake] (400ms)  mood  ...  planner  intent_check

AFTER v5.3 (4-way parallel ~max(400,300,400,800) = ~800ms, intent OFF critical path):
  START  parallel_intake_v2 [crisis||intake||mood||intent] (~800ms)  emotion_fusion
  conversation_planner uses prefetched_intent  ZERO extra LLM call

  Net saving over v5.2: ~8001500ms (intent check moved off critical path)
  Net saving over v5.1: ~8001500ms (intent) + ~400ms (mood parallelised) = ~1.21.9s

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
        print(f"[PARALLEL_INTAKE]  Intent prefetch failed: {str(e)[:80]}  using venting fallback")
        return {"intent": "venting", "confidence": 0.0}


async def run_parallel_intake(state: MentalHealthState) -> dict:
    """
    v5.4: Run crisis screening, context loading, mood analysis, and intent
    pre-check CONCURRENTLY via asyncio.gather (4-way parallel).

    Gate-aware optimizations:
      - Skips intent pre-check when smart_pipeline_gate already seeded intent
      - Skips crisis screener when gate already routed as non-crisis therapeutic
        (gate implicitly deems message safe; saves the expensive 70b LLM call)

    All tasks read from the initial state only and write to disjoint keys.
    Returns: merged dict across all nodes' outputs.
    """
    from ..nodes.context_loader import load_user_context
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

    from ..nodes.voice_preprocessing import preprocess_voice_input

    # --- Gate-aware skip flags ---
    prefetched = state.get("prefetched_intent") or {}
    gate_source = isinstance(prefetched, dict) and prefetched.get("source") == "smart_gate"
    gate_route  = state.get("gate_route", "")

    # Skip intent pre-check when gate already seeded intent
    has_gate_intent = gate_source

    # Skip crisis screener when gate explicitly routed as therapeutic (non-crisis).
    # Gate uses the same Llama-3.1-8b that also handles chitchat vs crisis — if it
    # said "therapeutic" the message is safe enough; save the expensive 70b call.
    skip_crisis = False

    # --- Build task log ---
    if skip_crisis:
        print("   screen_for_crisis       SKIPPED (gate_route=therapeutic, non-crisis confirmed)")
    else:
        print("   screen_for_crisis     (llama-3.3-70b via OpenRouter)")
    print("   load_user_context     (Prisma DB context)")
    print("   analyze_mood          (llama-3.3-70b via OpenRouter)")
    if has_gate_intent:
        print("   intent_pre_check        SKIPPED (gate intent already available)")
    else:
        print("   intent_pre_check      (llama-3.3-70b-free async, off critical path)")
    if state.get("audio_file_path") or state.get("audio_bytes"):
        print("   preprocess_voice_input (librosa + wav2vec2 + Deepgram Nova-2)")

    # --- Assemble task list ---
    tasks = []
    _task_map = []  # track which result slot maps to which task

    if not skip_crisis:
        from ..agent.graph import screen_for_crisis
        tasks.append(screen_for_crisis(state))
        _task_map.append("crisis")

    tasks.append(load_user_context(state))
    _task_map.append("intake")
    tasks.append(analyze_mood(state))
    _task_map.append("mood")

    if not has_gate_intent:
        tasks.append(_intent_pre_check_task(current_message, recent_context))
        _task_map.append("intent")

    has_voice = bool(state.get("audio_file_path") or state.get("audio_bytes"))
    if has_voice:
        tasks.append(preprocess_voice_input(state))
        _task_map.append("voice")

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Map results dynamically based on which tasks actually ran
    result_map = dict(zip(_task_map, results))

    crisis_result = result_map.get("crisis")
    intake_result = result_map.get("intake")
    mood_result   = result_map.get("mood")
    voice_result  = result_map.get("voice")

    if has_gate_intent:
        intent_result = state.get("prefetched_intent", {"intent": "venting", "confidence": 0.5})
    else:
        _raw = result_map.get("intent")
        intent_result = _raw if isinstance(_raw, dict) else {"intent": "venting", "confidence": 0.0}

    merged = {}

    #  Crisis screener 
    if crisis_result is None:
        # Gate already routed as therapeutic — safe to assume no crisis
        print("[NODE: PARALLEL_INTAKE]  Crisis screener skipped (gate=therapeutic) — defaulting to no-crisis")
        merged.update({
            "crisis_detected": False,
            "crisis_level": "none",
            "crisis_pre_screened": True,   # Mark screened so downstream skips re-check
        })
    elif isinstance(crisis_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Crisis screener failed: {str(crisis_result)[:100]}")
        merged.update({
            "crisis_detected": False,
            "crisis_level": "none",
            "crisis_pre_screened": False,
        })
    else:
        merged.update(crisis_result)

    #  Intake node 
    if isinstance(intake_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Intake failed: {str(intake_result)[:100]}")
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

    #  Mood analyzer 
    if isinstance(mood_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Mood analyzer failed: {str(mood_result)[:100]}")
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
        print(f"[NODE: PARALLEL_INTAKE]  Mood pre-computed: {_em} ({_it:.0%})")

    #  Intent pre-check 
    if isinstance(intent_result, Exception):
        print(f"[NODE: PARALLEL_INTAKE]  Intent prefetch failed: {str(intent_result)[:100]}")
        merged["prefetched_intent"] = None
    elif isinstance(intent_result, dict):
        merged["prefetched_intent"] = intent_result
        print(f"[NODE: PARALLEL_INTAKE]  Intent pre-computed: "
              f"{intent_result.get('intent')} ({intent_result.get('confidence', 0):.0%})")
    else:
        merged["prefetched_intent"] = None

    #  Voice preprocessing 
    if voice_result is not None:
        if isinstance(voice_result, Exception):
            print(f"[NODE: PARALLEL_INTAKE]  Voice preprocessing failed: {str(voice_result)[:100]}")
        else:
            merged.update(voice_result)
            deepgram_transcript = voice_result.get("transcription", "")
            if deepgram_transcript:
                #  ALWAYS prefer Deepgram over browser SpeechRecognition text.
                # Browser STT (Web Speech API) is noisy and inaccurate. Deepgram Nova-2
                # is significantly more accurate  override whatever the browser sent.
                merged["message"] = deepgram_transcript
                print(f"[NODE: PARALLEL_INTAKE]  Deepgram override  '{deepgram_transcript[:80]}'")

    crisis_flag = merged.get("crisis_detected", False)
    crisis_level = merged.get("crisis_level", "none")
    print(f"[NODE: PARALLEL_INTAKE]  Complete | "
          f"Crisis: {crisis_flag} ({crisis_level}) | "
          f"Context: {merged.get('context_ready', False)} | "
          f"Mood: {merged.get('emotion', '?')} | "
          f"Voice: {merged.get('voice_features', {}).get('emotion', '?') if merged.get('voice_features') else 'None'} | "
          f"Intent: {merged.get('prefetched_intent', {}).get('intent', '?')}")

    return merged
