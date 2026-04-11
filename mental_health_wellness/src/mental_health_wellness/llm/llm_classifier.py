"""
LLM-Assisted Classifier Module — SentiMind v5.3

Provides structured JSON classification helpers for sensitive pipeline nodes.
Each function:
  - Sends a minimal, focused prompt to Groq (llama-3.3-70b-versatile for crisis,
    llama-3.1-8b-instant for lighter tasks)
  - Expects ONLY a valid JSON response
  - Returns a safe fallback dict on any failure (never crashes the pipeline)

CRISIS NODE: Uses sentinet/suicidality (local ELECTRA fine-tuned model) as
             a first-pass specialist, then Groq 70b as a second validator.
             Two-layer approach for maximum safety in the most critical scenario.

v5.3 PERF:
  - _call_groq_async: removed redundant key-index pre-check (manager.get_llm()
    already handles key rotation/exhaustion internally).
  - ELECTRA inference offloaded to a thread executor in crisis_pre_screener_node
    so it doesn't block the event loop during the ~200ms CPU-bound forward pass.
"""

import json
import re
import os
import logging
from typing import Optional

from .groq_llm import get_llm_manager

logger = logging.getLogger(__name__)


# ============================================
# CRISIS SPECIALIST: Local ELECTRA Model
# Fine-tuned specifically on crisis/suicide datasets
# ============================================

_crisis_classifier = None  # Lazy-loaded on first use


def _get_crisis_classifier():
    """
    Lazy-load the sentinet/suicidality ELECTRA classifier.
    Falls back gracefully if transformers is not installed or model unavailable.
    """
    global _crisis_classifier
    if _crisis_classifier is not None:
        return _crisis_classifier

    try:
        from transformers import pipeline as hf_pipeline
        print("[CLASSIFIER] 🔄 Loading crisis specialist model (sentinet/suicidality)...")
        _crisis_classifier = hf_pipeline(
            "text-classification",
            model="sentinet/suicidality",
            top_k=None,  # Return all labels with scores
            truncation=True,
            max_length=512
        )
        print("[CLASSIFIER] ✅ Crisis specialist model loaded.")
    except Exception as e:
        logger.warning(f"[CLASSIFIER] ⚠️ Could not load sentinet/suicidality: {e}. Will use LLM-only fallback.")
        _crisis_classifier = "unavailable"

    return _crisis_classifier


def _parse_json_from_llm(content: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown fences."""
    # Strip markdown code fences if present
    content = re.sub(r"```(?:json)?", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON object within the response
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


async def _call_groq_async(prompt: str, model: str = "llama-3.1-8b-instant", temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """
    Make an ASYNC Groq LLM call with automatic key rotation.
    Returns raw content string or None on failure.

    v5.3 CRITICAL FIX: Was previously sync (llm.invoke = blocking HTTP via requests).
    Now uses await llm.ainvoke() so the event loop is never frozen.
    This means asyncio.gather() in parallel_intake and parallel_persist
    now achieves TRUE concurrency instead of false parallelism.

    v5.3 PERF: Removed redundant _get_available_groq_key_idx() pre-check —
    manager.get_llm() already handles rotation and full exhaustion internally.
    This eliminates one extra dict-scan call on every single classifier invocation.

    v5.2 OPT-5: max_tokens is caller-specified.
    Crisis (70b CoT) uses 128, intent/distortion (8b JSON) uses 64.
    """
    try:
        manager = get_llm_manager()

        # Use cached instance from manager (avoids per-call ChatGroq construction).
        # manager.get_llm() handles key rotation + exhaustion reset internally.
        llm = manager.get_llm(model=model)

        # Bind per-call overrides (max_tokens, temperature) without reconstructing
        # the underlying ChatGroq/httpx client.
        call_llm = llm.bind(max_tokens=max_tokens, temperature=temperature)

        response = await call_llm.ainvoke(prompt)  # NON-BLOCKING ─ event loop free
        return response.content
    except Exception as e:
        logger.warning(f"[CLASSIFIER] Groq async call failed: {e}")
        return None


# Keep sync alias for any legacy callers (wraps async in thread executor)
def _call_groq(prompt: str, model: str = "llama-3.1-8b-instant", temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """Legacy sync wrapper — prefer _call_groq_async in async contexts."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _call_groq_async(prompt, model, temperature, max_tokens))
                return future.result(timeout=30)
        else:
            return loop.run_until_complete(_call_groq_async(prompt, model, temperature, max_tokens))
    except Exception as e:
        logger.warning(f"[CLASSIFIER] Legacy sync Groq call failed: {e}")
        return None



# ============================================
# CRISIS CLASSIFIER — Two-Layer (ELECTRA + Groq 70b)
# ============================================

async def llm_crisis_check(message: str) -> dict:
    """
    Semantic crisis detection — Groq llama-3.3-70b-versatile as the authoritative decision maker.
    
    ARCHITECTURE (v5.3 — Fully Async):
      Step 1: ELECTRA specialist model runs to get a suicidality score.
              This score is used ONLY as an informational hint to the LLM.
      Step 2: Groq llama-3.3-70b-versatile runs async (await ainvoke) so the
              event loop is NOT blocked during the HTTP round-trip.

    Returns:
      {
        "crisis_detected": bool,
        "crisis_level": "high" | "medium" | "low",
        "reason": str,
        "source": "llm" | "electra+llm" | "fallback"
      }
    """
    electra_score = None
    electra_hint = ""

    try:
        # ---- STEP 1: ELECTRA (advisory only — cannot make final decision) ----
        classifier = _get_crisis_classifier()
        if classifier and classifier != "unavailable":
            results = classifier(message[:512])
            scores = results[0] if results else []
            score_map = {r["label"].lower(): r["score"] for r in scores}
            print(f"[CLASSIFIER] 🔬 ELECTRA raw labels: {score_map}")

            electra_score = score_map.get(
                "suicidal",
                score_map.get(
                    "suicide",
                    score_map.get(
                        "label_1",
                        score_map.get(
                            "1",
                            score_map.get(
                                "positive",
                                max(scores, key=lambda x: x["score"])["score"] if scores else 0.0
                            )
                        )
                    )
                )
            )
            print(f"[CLASSIFIER] 🔬 ELECTRA suicidality score: {electra_score:.2%} (advisory, not final)")
            electra_hint = (
                f"\n\n[Specialist suicide model pre-score: {electra_score:.0%} suicidality confidence. "
                f"NOTE: This model often over-scores normal emotional distress language. "
                f"Use this as a weak signal only — your semantic reasoning below is authoritative.]"
            )

    except Exception as e:
        logger.warning(f"[CLASSIFIER] ELECTRA error: {e} — continuing with LLM-only")

    # ---- STEP 2: Groq llama-3.3-70b-versatile (ALWAYS runs — authoritative decision maker) ----
    print(f"[CLASSIFIER] 🤖 Running Groq llama-3.3-70b-versatile semantic crisis analysis (async)...")

    prompt = f"""You are a mental health crisis safety specialist AI. Your task is to determine whether a message contains genuine suicidal ideation or explicit self-harm risk.

You must reason step-by-step across THREE dimensions before giving your final answer. This is MANDATORY.

---

**STEP A — DESIRE DIMENSION**
Does the person express an active, first-person *desire or wish* to die, end their life, stop existing, or physically harm themselves?
- YES → This may indicate crisis. Proceed to Step B and C.
- NO → This is emotional distress, venting, cognitive distortion, or figurative language. The message is level="low" and crisis_detected=false.

**STEP B — CONTEXT DIMENSION**
What is the nature of the statement?
- Emotional venting/distress: describing sadness, loneliness, worthlessness, exhaustion, or worsening mood WITHOUT any expressed wish to die → level="low"
- Cognitive distortion: statements like "I'm worthless", "nobody understands me", "I'm the only one who struggles", "I must be perfect" → these are self-critical thoughts, NOT suicidal ideation → level="low"
- Figurative/hyperbolic: "I could sleep forever" (after a long week), "I want to disappear from social media", "tired of fighting" (daily struggles) → level="low"
- Passive ideation explicitly tied to wishing to be gone: "everyone would be better off without me" + wishing not to exist → level="medium", crisis_detected=true
- Active desire: clear first-person wish to end life, self-harm, or stop living → level="high", crisis_detected=true

**STEP C — LETHALITY DIMENSION**
Is there any specificity: a method, timeline, or concrete plan?
- YES (e.g. "I have pills", "I plan to...", "tonight") → level="high", crisis_detected=true
- NO → rely on Steps A and B

---

**FINAL RULE: Only set crisis_detected=true WHEN:**
- Step A = YES (clear desire to die/harm) AND it is not figurative/distortion language, OR
- Step C = YES (lethality specifics present)

**NON-CRISIS examples (level=low, crisis_detected=false):**
- "I feel so lonely, nobody really understands me" → emotional venting, no desire to die
- "Everything feels really heavy lately" → metaphorical emotional weight
- "I feel so worthless and useless at everything" → cognitive distortion, no ideation
- "I'm the only one who struggles like this" → mind-reading distortion
- "I must be perfect or I'm completely worthless" → black-and-white thinking
- "I'm so tired of fighting every single day" → exhaustion metaphor (fighting = daily life)
- "I could sleep forever after this long week" → tiredness figurative
- "I want to disappear from social media" → digital detox
- "Every day is worse than the last" → worsening mood, no ideation

**CRISIS examples (crisis_detected=true):**
- "I want to kill myself" → explicit desire → HIGH
- "I don't want to be here anymore" (hopelessness context) → MEDIUM
- "I have a plan to end my life this weekend" → lethality → HIGH
- "Everyone would be better off without me" + wishing to be gone → MEDIUM
{electra_hint}

Respond ONLY with valid JSON — no other text:
{{"crisis_detected": true or false, "crisis_level": "high" or "medium" or "low", "reason": "one concise sentence"}}

Message to classify: "{message}"

JSON:"""

    try:
        content = await _call_groq_async(prompt, model="llama-3.3-70b-versatile", temperature=0.0, max_tokens=128)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "crisis_detected" in parsed:
                if parsed.get("crisis_level") == "low":
                    parsed["crisis_detected"] = False
                parsed["source"] = "electra+llm" if electra_score is not None else "llm"
                print(f"[CLASSIFIER] 🤖 Groq 70b crisis result: crisis={parsed['crisis_detected']} level={parsed.get('crisis_level')} reason='{parsed.get('reason', '')}' electra_score={f'{electra_score:.2%}' if electra_score is not None else 'N/A'}")
                return parsed
    except Exception as e:
        logger.error(f"[CLASSIFIER] Groq LLM crisis check failed: {e}")

    return {
        "crisis_detected": False,
        "crisis_level": "low",
        "reason": "All classifiers failed — defaulting to safe non-crisis",
        "source": "fallback"
    }


# ============================================
# COGNITIVE DISTORTION CLASSIFIER — Groq 8b
# ============================================

async def llm_distortion_check(message: str) -> dict:
    """
    LLM-assisted cognitive distortion detection.
    Called when keyword confidence is low (< 0.4).
    v5.3: Now truly async via _call_groq_async.

    Returns:
      {
        "distortion_type": str | null,
        "confidence": float,
        "all_distortions": [str],
        "explanation": str
      }
    """
    try:
        prompt = f"""You are a CBT (Cognitive Behavioral Therapy) specialist AI.
Identify cognitive distortions in the user message.
Choose from: catastrophizing, black_white, overgeneralization, mind_reading, personalization, should_statements, emotional_reasoning, magnification, or null.

Respond ONLY with valid JSON in this exact format:
{{"distortion_type": string or null, "confidence": float 0.0-1.0, "all_distortions": [list of strings], "explanation": "brief explanation"}}

Message: "{message}"

JSON:"""

        content = await _call_groq_async(prompt, model="llama-3.1-8b-instant", temperature=0.0, max_tokens=64)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "distortion_type" in parsed:
                print(f"[CLASSIFIER] 🧠 LLM distortion: {parsed.get('distortion_type')} ({parsed.get('confidence', 0):.0%})")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] Distortion check failed: {e}")

    return {
        "distortion_type": None,
        "confidence": 0.0,
        "all_distortions": [],
        "explanation": "Classification unavailable"
    }


# ============================================
# CONVERSATION INTENT CLASSIFIER — Groq 8b
# ============================================

async def llm_intent_check(message: str) -> dict:
    """
    LLM-assisted intent classification for the conversation planner.
    v5.3: Now truly async via _call_groq_async.

    Returns:
      {
        "intent": "technique_request" | "reflection" | "venting" | "chitchat" | "crisis_signal",
        "confidence": float
      }
    """
    try:
        prompt = f"""You are a mental health conversation assistant. Classify the USER's intent.

Choose ONE: technique_request | reflection | venting | chitchat | crisis_signal

- technique_request: user asks for help, exercises, or something to calm down
- reflection: user shows understanding, insight, or asks "why/how" about their feelings
- venting: user expressing strong emotion, needs to be heard
- chitchat: casual, off-topic, non-emotional message
- crisis_signal: user expresses hopelessness, wanting to disappear, or indirect self-harm signals

Respond ONLY with valid JSON:
{{"intent": string, "confidence": float 0.0-1.0}}

Message: "{message}"

JSON:"""

        content = await _call_groq_async(prompt, model="llama-3.1-8b-instant", temperature=0.0, max_tokens=64)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "intent" in parsed:
                print(f"[CLASSIFIER] 💬 LLM intent: {parsed.get('intent')} ({parsed.get('confidence', 0):.0%})")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] Intent check failed: {e}")

    return {"intent": "venting", "confidence": 0.0}


async def llm_intent_pre_check(message: str) -> dict:
    """
    v5.3 NEW: Lightweight intent pre-check for parallel_intake.

    Identical to llm_intent_check but named separately so parallel_intake
    can import and launch it as a 4th concurrent task alongside crisis screening,
    intake loading, and mood analysis.

    The result is stored as state["prefetched_intent"] and consumed by
    conversation_planner_node — which skips its own LLM call when the
    prefetched result is available.

    This removes the intent LLM call from the serial critical path entirely.
    """
    print("[CLASSIFIER] ⚡ [PREFETCH] Running intent check concurrently with intake...")
    result = await llm_intent_check(message)
    print(f"[CLASSIFIER] ✅ [PREFETCH] Intent prefetch done: {result.get('intent')} ({result.get('confidence', 0):.0%})")
    return result

