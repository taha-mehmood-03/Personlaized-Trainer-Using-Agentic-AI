# Three-Issue Fix: User Identity, Gate Routing & Smart DB Storage

## Background

After the NextAuth integration, three interconnected failure modes appeared:
1. `user_id` passed to the FastAPI backend is the real CUID from Prisma, but some code paths still fall back to `"anonymous"`, causing orphaned DB records with FK violations.
2. The smart pipeline gate uses `llama-3.1-8b-instruct` — a 8B model on OpenRouter with no structured output guarantee. It misclassifies chitchat as therapeutic and misses memory queries.
3. The memory layer (`extract_and_save_facts`) stores raw user messages without any intelligence about *what* is actually worth persisting. It stores facts for every message unconditionally, and `session_saver` triggers a full session summary via a simple `% 5 == 0` counter with no quality filter.

---

## Proposed Changes

---

### Issue 1 — Dynamic User ID (All data paths must carry the real NextAuth CUID)

The flow is: `NextAuth session → layout.tsx (server) → ChatLayout props → useStream → fetch /api/chat/stream → FastAPI → graph.py → parallel_persist`.

The key audit findings:
- ✅ `layout.tsx`: Already correctly extracts `session.user.id` server-side and passes it as `userId` prop.
- ✅ `useStream.ts`: Correctly sends `user_id: userId` in the fetch body to `/api/chat/stream`.
- ✅ `api_server.py /api/chat/stream`: Passes `request.user_id` directly to `chat_with_agent_streaming`.
- ✅ `graph.py`: Passes `user_id` into the `input_state` dict and into `create_new_session`.
- ⚠️ **`/api/pipeline/complete`**: Still has `user_id = request.user_id or "anonymous"` — this is the only remaining hardcoded fallback.
- ⚠️ **`/api/user/ensure`**: Creates users with `id = user_id or "anonymous"` — acceptable, but needs to never be called with anonymous for real users.
- ✅ `user_tools.py save_session`: Already fixed in the last session (session claiming).
- ⚠️ **`explicit_facts.py extract_and_save_facts`**: Uses a *synchronous* LLM call (`llm.invoke`) inside an `asyncio.create_task`. This will block the event loop. Must be changed to `await llm.ainvoke`.

**Fix:** Remove the `or "anonymous"` fallback in `/api/pipeline/complete`. Fix the sync LLM call in `explicit_facts.py`.

#### [MODIFY] [api_server.py](file:///e:/FYP/mental_health_wellness/api_server.py)
- Line 433: Change `user_id = request.user_id or "anonymous"` → raise 400 if `user_id` is empty, else use as-is.

#### [MODIFY] [explicit_facts.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/memory/explicit_facts.py)
- Line 34: Use `manager.get_llm()` async call — change `llm.invoke(...)` → `await llm.ainvoke(...)`.
- This function is always called via `asyncio.create_task()`, so it runs in an async context and can safely use `await`.

---

### Issue 2 — LLM Gate Routing (`smart_pipeline_gate`)

**Root causes:**
1. **Wrong model:** `llama-3.1-8b-instruct` is too small for reliable 7-way intent routing with context. It hallucinates routes and ignores examples. The gate should use the **same 70b model** used for crisis — `meta-llama/llama-3.3-70b-instruct`. This is the single highest-impact change.
2. **No structured output:** The prompt asks for JSON but doesn't enforce schema strictly enough. The 8b model often wraps it in markdown or adds extra text.
3. **`memory_query` examples are too narrow:** The prompt only shows "do you remember" but users say things like "what have we talked about?" or "tell me about myself".

**Fix:** Upgrade the gate model to `llama-3.3-70b-instruct` and tighten the `memory_query` examples.

> [!IMPORTANT]
> This will increase gate latency by ~200-400ms but dramatically improve routing accuracy. The 70b model is already running for crisis checks, so it's already in your cost budget. The chitchat bypass saves far more time per turn than this overhead.

#### [MODIFY] [llm_classifier.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/llm/llm_classifier.py)
- Line 673: Change gate model from `"meta-llama/llama-3.1-8b-instruct"` → `"meta-llama/llama-3.3-70b-instruct"`.
- Lines 619-624: Expand `memory_query` examples to include: `"what have we talked about"`, `"what do you know about me"`, `"remind me what we discussed"`, `"summarize our conversation"`.

---

### Issue 3 — Smart DB Storage Decision

**Root causes:**
1. **`extract_and_save_facts`** runs on *every* user message without pre-filtering. It extracts facts even when the message is a greeting or therapeutic venting (no stable facts possible). The LLM does this filtering, but it's an unnecessary LLM call for most messages.
2. **Session summary** triggers at every 5th message regardless of whether meaningful content was exchanged. A session of chitchat gets a summary. A session with 4 deep therapeutic messages (just under the threshold) gets no summary.
3. **No storage decision node:** There's no single LLM call that decides: (a) worth storing a fact? (b) worth summarizing now? (c) skip? — instead facts and summaries are decided by separate, disconnected code paths.

**Fix:** Add a lightweight **storage decision guard** as a pre-filter in `session_saver.py`. Before calling `extract_and_save_facts`, quickly check if the message is "storage-worthy" (contains personal facts OR is therapeutic, not just chitchat). The check can be a cheap regex/keyword scan (no LLM cost).

Also: change the session summary trigger from a fixed `% 5 == 0` counter to a **content-aware** trigger: summarize if `msg_count >= 4` AND the session has any non-chitchat message (detected from `conversation_strategy != "no_action"`).

#### [MODIFY] [session_saver.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/session_saver.py)
- Before the `asyncio.create_task(summarize_session(...))` call: change the condition from `msg_count % 5 == 0` → `msg_count >= 4 and strategy not in ("no_action", "")` so the summary only fires when meaningful therapeutic content exists.

#### [MODIFY] [explicit_facts.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/memory/explicit_facts.py)
- Add a `_is_storage_worthy(message: str) -> bool` guard at the top of `extract_and_save_facts`. Returns `False` for short greetings (<30 chars) and messages that are clearly temporal emotions ("I feel sad today"). Only calls the LLM if the message might contain a stable fact.

---

## Verification Plan

### Automated Checks
1. Send a chat message as an authenticated user → check backend logs for `[CHAT] [NEW] New message from user: cmo...` (should show real CUID, not `anonymous`).
2. Send "hey how are you?" → verify gate logs show `Route: CHITCHAT` not `THERAPEUTIC`.
3. Send "what do you know about me?" → verify gate logs show `Route: MEMORY_QUERY`.
4. Say your name in a message ("my name is Taha") → check `UserFact` table for a saved fact.
5. After 4+ meaningful therapeutic exchanges, check `SessionSummary` table for a new row.

### Manual Verification
- Check the FastAPI terminal after restart: you should NEVER see `[TOOL] save_session: Created fallback session` after the first message in a new session.
- The `[NODE: SESSION_SAVER]` log should show `Using session <cuid>` on every subsequent message, not `Created fallback session`.
