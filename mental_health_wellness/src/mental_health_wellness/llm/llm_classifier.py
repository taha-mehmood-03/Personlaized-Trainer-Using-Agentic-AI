"""
LLM-Assisted Classifier Module — SentiMind v6.1

Provides structured JSON classification helpers for sensitive pipeline nodes.
Each function:
  - Sends a minimal, focused prompt to OpenRouter (first priority) or Groq (fallback)
    using meta-llama/llama-3.3-70b-instruct for crisis, meta-llama/llama-3.1-8b-instruct for lighter tasks
  - Expects ONLY a valid JSON response
  - Returns a safe fallback dict on any failure (never crashes the pipeline)

CRISIS NODE: OpenRouter meta-llama/llama-3.3-70b-instruct is the SOLE authoritative decision maker.
             Local ELECTRA model disabled — LLM-only path active.

v6.1 CHANGES:
  - LLM_PROVIDER=openrouter: All calls routed through OpenRouter.
  - Local ELECTRA (sentinet/suicidality) model DISABLED (commented out).
  - All Groq llama model names replaced with OpenRouter compatible model IDs.
    Heavy tasks  → meta-llama/llama-3.3-70b-instruct
    Light tasks  → meta-llama/llama-3.1-8b-instruct
"""

import json
import re
import os
import logging
from typing import Optional

from .groq_llm import get_llm_manager

logger = logging.getLogger(__name__)


# ============================================
# CRISIS SPECIALIST: Local ELECTRA Model — DISABLED
# LLM_PROVIDER=openrouter: OpenRouter LLM is now the sole decision maker.
# The local sentinet/suicidality model is commented out for performance.
# ============================================

_crisis_classifier = None  # Always returns "unavailable" (local model disabled)


def _get_crisis_classifier():
    """
    Local ELECTRA crisis classifier — DISABLED.
    Returns 'unavailable' immediately so llm_crisis_check falls through
    to the LLM-only path (OpenRouter llama-3.3-70b-instruct).
    """
    global _crisis_classifier
    if _crisis_classifier is not None:
        return _crisis_classifier

    # ── LOCAL MODEL DISABLED ──────────────────────────────────────────────
    # The sentinet/suicidality ELECTRA model is commented out.
    # OpenRouter LLM handles crisis detection as sole authoritative decision maker.
    #
    # try:
    #     from transformers import pipeline as hf_pipeline
    #     print("[CLASSIFIER] 🔄 Loading crisis specialist model (sentinet/suicidality)...")
    #     _crisis_classifier = hf_pipeline(
    #         "text-classification",
    #         model="sentinet/suicidality",
    #         top_k=None,
    #         truncation=True,
    #         max_length=512
    #     )
    #     print("[CLASSIFIER] ✅ Crisis specialist model loaded.")
    # except Exception as e:
    #     logger.warning(f"[CLASSIFIER] ⚠️ Could not load sentinet/suicidality: {e}.")
    #     _crisis_classifier = "unavailable"
    # ─────────────────────────────────────────────────────────────────────

    print("[CLASSIFIER] ╔══════════════════════════════════════════════╗")
    print("[CLASSIFIER] ║  LOCAL ELECTRA MODEL → DISABLED              ║")
    print("[CLASSIFIER] ║  Crisis detection: OpenRouter claude-3.5-sonnet ║")
    print("[CLASSIFIER] ╚══════════════════════════════════════════════╝")
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


async def _call_groq_async(prompt: str, model: str = "meta-llama/llama-3.1-8b-instruct", temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """
    Make an ASYNC OpenRouter LLM call via the unified LLM manager.
    Returns raw content string or None on failure.

    v6.1: Default model updated to meta-llama/llama-3.1-8b-instruct (fast classification).
    Heavy tasks (crisis) pass meta-llama/llama-3.3-70b-instruct explicitly.
    """
    try:
        manager = get_llm_manager()
        llm = manager.get_llm(model=model)
        call_llm = llm.bind(max_tokens=max_tokens, temperature=temperature)
        print(f"[CLASSIFIER] ▶  Calling OpenRouter | model={model} | max_tokens={max_tokens}")
        response = await call_llm.ainvoke(prompt)  # NON-BLOCKING — event loop free
        print(f"[CLASSIFIER] ◀  Response received  | model={model}")
        return response.content
    except Exception as e:
        logger.warning(f"[CLASSIFIER] ❌ OpenRouter call FAILED | model={model} | error: {e}")
        return None


# Keep sync alias for any legacy callers (wraps async in thread executor)
def _call_groq(prompt: str, model: str = "meta-llama/llama-3.1-8b-instruct", temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
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
# CRISIS CLASSIFIER — OpenRouter Llama-70b (sole decision maker)
# ============================================

async def llm_crisis_check(message: str) -> dict:
    """
    Semantic crisis detection — OpenRouter meta-llama/llama-3.3-70b-instruct as the authoritative decision maker.

    ARCHITECTURE (v6.1 — LLM-Only, Fully Async):
      Step 1: Keyword gate handled upstream (graph.py screen_for_crisis Layer 1).
      Step 2: llama-3.3-70b-instruct runs async (await ainvoke) — best empathy + clinical reasoning.
              Local ELECTRA model is DISABLED (always returned 'unavailable').

    Returns:
      {
        "crisis_detected": bool,
        "crisis_level": "high" | "medium" | "low",
        "reason": str,
        "source": "llm" | "fallback"
      }
    """
    # ELECTRA disabled — OpenRouter llama is the sole decision maker

    # ---- CRISIS ANALYSIS: OpenRouter llama-3.3-70b ----
    print("[CLASSIFIER] │  CRISIS CHECK  →  llama-3.3-70b-instruct │")
    print("[CLASSIFIER] │  3-step dimensional reasoning (desire/context/  │")
    print("[CLASSIFIER] │  lethality) for accurate mental health safety    │")
    print("[CLASSIFIER] └─────────────────────────────────────────────────┘")
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

Respond ONLY with valid JSON — no other text:
{{"crisis_detected": true or false, "crisis_level": "high" or "medium" or "low", "reason": "one concise sentence"}}

Message to classify: "{message}"

JSON:"""

    try:
        content = await _call_groq_async(prompt, model="meta-llama/llama-3.3-70b-instruct", temperature=0.0, max_tokens=128)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "crisis_detected" in parsed:
                if parsed.get("crisis_level") == "low":
                    parsed["crisis_detected"] = False
                parsed["source"] = "llm"
                crisis_icon = "🚨" if parsed["crisis_detected"] else "✅"
                print(f"[CLASSIFIER] {crisis_icon} CRISIS RESULT │ detected={parsed['crisis_detected']} │ level={parsed.get('crisis_level','?').upper()} │ reason='{parsed.get('reason', '')}'")
                return parsed
    except Exception as e:
        logger.error(f"[CLASSIFIER] ❌ Crisis LLM call FAILED: {e}")

    print("[CLASSIFIER] ⚠️  ALL classifiers failed — returning safe non-crisis fallback")
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

        print("[CLASSIFIER] 🧠 DISTORTION CHECK → llama-3.1-8b")
        content = await _call_groq_async(prompt, model="meta-llama/llama-3.1-8b-instruct", temperature=0.0, max_tokens=64)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "distortion_type" in parsed:
                dtype = parsed.get('distortion_type') or 'none'
                conf  = parsed.get('confidence', 0)
                print(f"[CLASSIFIER] 🧠 DISTORTION RESULT │ type={dtype} │ confidence={conf:.0%}")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] ❌ Distortion check FAILED: {e}")

    return {
        "distortion_type": None,
        "confidence": 0.0,
        "all_distortions": [],
        "explanation": "Classification unavailable"
    }


# ============================================
# CONVERSATION INTENT CLASSIFIER — Groq 8b
# ============================================

async def llm_intent_check(message: str, recent_context: str = "") -> dict:
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
        prompt = f"""You are a mental health conversation assistant. Classify the USER's latest intent based on their latest message.

Choose ONE: technique_request | reflection | venting | chitchat | crisis_signal

- technique_request: user asks for help, exercises, coping mechanisms, OR asks for an alternative/different technique after one was suggested.
- reflection: user shows understanding, insight, or asks "why/how" about their feelings
- venting: user expressing strong emotion, needs to be heard
- chitchat: casual, off-topic, non-emotional message
- crisis_signal: user expresses hopelessness, wanting to disappear, or indirect self-harm signals

Respond ONLY with valid JSON:
{{"intent": string, "confidence": float 0.0-1.0}}

Previous Conversation Context:
{recent_context}

User's Latest Message: "{message}"

JSON:"""

        print("[CLASSIFIER] 💬 INTENT CHECK → llama-3.1-8b")
        content = await _call_groq_async(prompt, model="meta-llama/llama-3.1-8b-instruct", temperature=0.0, max_tokens=64)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "intent" in parsed:
                print(f"[CLASSIFIER] 💬 INTENT RESULT │ intent={parsed.get('intent')} │ confidence={parsed.get('confidence', 0):.0%}")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] ❌ Intent check FAILED: {e}")

    print("[CLASSIFIER] ⚠️  Intent check failed — defaulting to 'venting'")
    return {"intent": "venting", "confidence": 0.0}


async def llm_intent_pre_check(message: str, recent_context: str = "") -> dict:
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
    print("[CLASSIFIER] ⚡ PREFETCH │ Intent check starting concurrently with intake...")
    result = await llm_intent_check(message, recent_context)
    print(f"[CLASSIFIER] ⚡ PREFETCH │ Intent done → {result.get('intent')} ({result.get('confidence', 0):.0%}) — stored for planner")
    return result

