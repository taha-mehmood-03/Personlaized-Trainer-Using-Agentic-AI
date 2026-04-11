# SentiMind v5.3 — Latency Optimization Plan

## Background

After a deep audit of the v5.2 codebase I found **three classes of latency bugs**
that are adding 1–4 seconds of unnecessary delay per message even on the warm-server path.
The optimizations below address each class and introduce one small architectural change.

---

## Root Cause Analysis

### 🔴 Class 1 — Async Façade Bug (CRITICAL, ~1–3s per message)

Every "async" Groq classifier call is actually **blocking the event loop**.

`_call_groq()` in `llm_classifier.py` is a **sync function** that calls
`llm.invoke(prompt)` — a blocking HTTP request using the `requests` library.
It is called from three `async def` functions (`llm_crisis_check`,
`llm_intent_check`, `llm_distortion_check`) **without** `run_in_executor`, which
means the entire event loop freezes while the HTTP round-trip completes (~800–1500ms).

The same bug exists in `optimized_response_generator.py` where both:
- `llm.invoke(fast_messages)` (casual path)  
- `response = llm.invoke(llm_messages)` (therapeutic path)

…are synchronous calls inside an `async def` node, blocking the event loop for
the full LLM round-trip (~1–3s).

**Impact:**  
- `parallel_intake` runs `asyncio.gather(crisis_screener, intake)` — but if
  `crisis_screener` hits the ELECTRA escalation threshold and calls
  `_call_groq()` (sync), the event loop freezes and `intake_node` can't
  make progress on its own async DB queries. The "parallel" execution isn't parallel.
- The intent check in `conversation_planner` blocks for 800–1500ms on every
  **ambiguous** message.
- The response generator blocks for 1–3s on every message.

**Fix:** Convert `_call_groq` to `async def _call_groq_async(...)` using
`await llm.ainvoke(prompt)`, and update all three classifier functions to
`await _call_groq_async(...)`. Convert both `llm.invoke()` calls in the
response generator to `await llm.ainvoke()`.

---

### 🟡 Class 2 — LLM Instance Thrashing (moderate, ~20–50ms per call)

`get_chat_llm()` creates a **new `ChatGroq` object** on every single call.
It is called in `conversation_planner`, `optimized_response_generator`, and
`agentic.py`. ChatGroq's `__init__` validates credentials, builds headers, and
sets up the httpx client — not free.

**Fix:** Add an LRU-style instance cache keyed on `(key_idx, model)` inside
`MultiKeyGroqChat.get_llm()`.

---

### 🟡 Class 3 — Intent Check on the Critical Path (~800–1500ms per ambiguous message)

`llm_intent_check` is called inside `conversation_planner_node` **sequentially
after** `parallel_analysis`. Since `llm_intent_check` only reads
`state["messages"][-1].content` (available from the start), it can be computed
much earlier — concurrently with the entire `parallel_intake` phase.

**Architectural change (v5.3):** Extend `parallel_intake_node` to also launch
`mood_analyzer_node` **and** a lightweight async intent pre-check concurrently
with crisis screening and context loading. All four inputs needed by these tasks
are present in the initial state (messages, user_id, session_id only).

New parallel tier:
```
START → parallel_intake_v2:
  ┌── crisis_pre_screener     (ELECTRA + optional 70b LLM)
  ├── intake_node             (DB + ChromaDB memory)
  ├── mood_analyzer_node      (DistilBERT local inference)
  └── intent_pre_check        (Groq 8b intent — async now!)
```

`conversation_planner` receives `prefetched_intent` from state and **skips
the LLM call entirely** when heuristics don't match.

Combined, this moves ~800–1500ms of serial work onto the parallel intake bus,
reducing the critical path proportionally.

---

## Proposed Changes

### Core LLM Layer

#### [MODIFY] [groq_llm.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/llm/groq_llm.py)
- Add `_llm_cache: dict` to `MultiKeyGroqChat.__init__`
- In `get_llm()`, return cached `ChatGroq` instance when key/model are unchanged
- Cache is invalidated when a key is marked as failed

#### [MODIFY] [llm_classifier.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/llm/llm_classifier.py)
- Rename `_call_groq` → `_call_groq_async`, make it `async def`, use `await llm.ainvoke(prompt)`
- Update `llm_crisis_check`, `llm_intent_check`, `llm_distortion_check` to `await _call_groq_async(...)`
- Add new lightweight export: `async def llm_intent_pre_check(message)` — thin wrapper around `llm_intent_check` for use in parallel intake

---

### Response Generator

#### [MODIFY] [optimized_response_generator.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/optimized_response_generator.py)
- Change `casual_response = llm.invoke(fast_messages)` → `casual_response = await llm.ainvoke(fast_messages)`
- Change `response = llm.invoke(llm_messages)` → `response = await llm.ainvoke(llm_messages)`

---

### Architectural Tier Upgrade (v5.3)

#### [MODIFY] [parallel_intake.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/parallel_intake.py)
- Extend `asyncio.gather` from 2 tasks → 4 tasks: add `mood_analyzer_node` and `_intent_pre_check_task`
- Write `mood` result keys + `prefetched_intent` dict into merged state
- Keep all existing crash-safe defaults for each task

#### [MODIFY] [conversation_planner_node.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/conversation_planner_node.py)
- Read `state.get("prefetched_intent")` at the top of the function
- If present (and confidence ≥ 0.65), use it as `intent_result` and **skip the LLM call**
- Log clearly when prefetched intent is used vs. fresh LLM call

#### [MODIFY] [graph.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/agent/graph.py)
- Remove standalone `mood_analyzer` node from the graph (it now runs inside `parallel_intake`)
- Update edges: `parallel_intake → emotion_fusion` (was `parallel_intake → mood_analyzer → emotion_fusion`)
- Add `prefetched_intent` to the architectural docstring

#### [MODIFY] [state.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/agent/state.py)
- Add `prefetched_intent: Optional[dict]` field to `MentalHealthState`

---

## Expected Outcome

| Scenario | v5.2 (est.) | v5.3 (est.) | Saving |
|---|---|---|---|
| Casual chitchat | 1.5–2.5s | 0.8–1.2s | ~1s |
| Obvious venting (heuristic match) | 2–3s | 1–1.8s | ~1s |
| Ambiguous message (LLM intent needed) | 3–5s | 1.5–2.5s | ~1.5–2.5s |
| Crisis path | 4–7s | 2–3s | ~2–4s |

> All estimates assume warm server. The async fix alone (Class 1) is expected to save the most.

## Verification Plan

1. Run `python test_latency.py` from `mental_health_wellness/` before and after to compare numbers
2. Check terminal logs to confirm `[PARALLEL_INTAKE]` now shows 4 concurrent tasks
3. Confirm `[NODE: PLANNER]` logs show "prefetched intent used" on most messages
4. Confirm `[NODE:RESPONSE]` LLM call time is now non-blocking (other tasks can proceed)
