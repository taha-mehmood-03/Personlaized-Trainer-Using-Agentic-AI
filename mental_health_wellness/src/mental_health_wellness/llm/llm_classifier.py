"""
LLM-Assisted Classifier Module  SentiMind v8.7 FIXED

Provides structured JSON classification helpers for sensitive pipeline nodes.
Each function:
  - Sends a minimal, focused prompt to Google AI Studio / Gemini.
  - Expects ONLY a valid JSON response
  - Returns a safe fallback dict on any failure (never crashes the pipeline)

CRISIS NODE: Gemini is the sole authoritative LLM decision maker.
             Local ELECTRA model disabled  LLM-only path active.

GATE NODE: Gemini Flash-Lite for low-latency structured routing.

v8.7 FIXES vs v6.1:
  - smart_pipeline_gate  : uses llama-3.3-70b-instruct for stable routing
  - llm_crisis_check     : FIXED model mismatch - prompt said 70b but code called 8b (safety-critical bug)
  - Gate prompt          : Fully rewritten with numbered steps, expanded examples, ambiguous edge cases covered
  - Crisis prompt        : Sharpened 3-step dimensional reasoning, added more non-crisis examples
  - Distortion prompt    : Added concrete examples for every distortion type
  - Intent prompt        : Unchanged (was already solid)
  - All prompts          : temperature=0.0 enforced everywhere, JSON-only output enforced
  - All LLM calls are routed through Google AI Studio / Gemini.
  - Local ELECTRA (sentinet/suicidality) model DISABLED (commented out).
"""

import json
import re
import os
import logging
from typing import Optional

from .groq_llm import get_llm_manager, message_content_to_text
from ..utils.turn_signals import (
    assistant_likely_gave_steps,
    assistant_offered_technique,
    has_negative_feedback_signal,
    has_positive_outcome_signal,
    is_explicit_exercise_request,
    is_no_thanks,
    is_polite_acknowledgement,
    is_technique_acceptance_reply,
    last_ai_from_recent_context,
    plain_text,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  MODEL CONSTANTS  change once here, applies everywhere below
# ─────────────────────────────────────────────────────────────
def _gemini_model_env(default: str, *names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip().startswith("gemini-"):
            return value.strip()
    return default


MODEL_GATE = _gemini_model_env("gemini-3.1-flash-lite", "GEMINI_MODEL_GATE", "MODEL_GATE", "SENTIMIND_MODEL_GATE")
MODEL_MOOD = _gemini_model_env("gemini-3.1-flash-lite", "GEMINI_MODEL_MOOD", "MODEL_MOOD", "SENTIMIND_MODEL_MOOD")
MODEL_CRISIS = _gemini_model_env("gemini-3.1-flash-lite", "GEMINI_MODEL_CRISIS", "MODEL_CRISIS", "SENTIMIND_MODEL_CRISIS")
MODEL_FALLBACK = _gemini_model_env("gemini-3.1-flash-lite", "GEMINI_MODEL_FALLBACK", "MODEL_FALLBACK", "SENTIMIND_MODEL_FALLBACK")

# Backward-compatible names used by older call sites in this module.
MODEL_HEAVY = MODEL_GATE
MODEL_LIGHT = MODEL_MOOD


def deterministic_crisis_safety_net(message: str) -> dict:
    """
    High-precision deterministic safety net for explicit self-harm language.

    This is intentionally narrow. It does not replace semantic LLM screening;
    it catches obvious crisis statements when the LLM router/classifier is
    unavailable or before latency-sensitive routing.
    """
    text = re.sub(r"\s+", " ", (message or "").lower()).strip()
    if not text:
        return {
            "crisis_detected": False,
            "crisis_level": "low",
            "reason": "empty message",
            "source": "deterministic_safety_net",
        }

    # Panic attack phrases are acute anxiety episodes — NEVER suicidal ideation.
    # Short-circuit before any crisis pattern matching so they cannot be mis-escalated.
    _panic_patterns = (
        # fuzzy: panic/pnic/panik/panick/pannick + attack (covers typos)
        r"\bpa?ni?c?k?\s*att?ack\b",
        # "im having a pnic/panic/panik..."
        r"\bim\s+having\s+a\s+pa?ni?c?k?\b",
        r"\bi('?m| am)\s+having\s+a\s+pa?ni?c?k?\b",
        r"\bi\s+think\s+i('?m| am)\s+having\s+a\s+pa?ni?c?k?\b",
        # standalone typo variants
        r"\bpni[ck]\b",
        r"\bpani[ck]\b",
        r"\bpannick?\b",
    )
    for _p in _panic_patterns:
        if re.search(_p, text):
            return {
                "crisis_detected": False,
                "crisis_level": "low",
                "reason": "panic attack is acute anxiety, not suicidal ideation",
                "source": "deterministic_safety_net",
                "immediate_regulation_request": True,
            }

    high_patterns = (
        r"\bi\s+(want|need|plan|intend)\s+to\s+(kill myself|end my life|take my own life|die)\b",
        r"\bi\s+(am|m|'m)\s+(going|planning)\s+to\s+(kill myself|end my life|take my own life|die)\b",
        r"\bi\s+have\s+a\s+plan\s+to\s+(kill myself|end my life|take my own life|die)\b",
        r"\b(i have|i've got|ive got)\s+(pills|a knife|a gun|a rope|a blade).{0,40}\b(ready|tonight|to do it|to end it)\b",
        r"\bi\s+(already\s+)?(cut|hurt)\s+myself\b",
        r"\b(i've|ive)\s+been\s+cutting\s+(myself|again)\b",
    )
    for pattern in high_patterns:
        if re.search(pattern, text):
            return {
                "crisis_detected": True,
                "crisis_level": "high",
                "reason": "explicit self-harm intent, plan, means, or recent self-harm matched deterministic safety net",
                "source": "deterministic_safety_net",
            }

    medium_patterns = (
        r"\bi\s+(do not|don't|dont)\s+want\s+to\s+(be here|exist|live)(\s+anymore|\s+any more)?\b",
        r"\bi\s+want\s+to\s+disappear\s+forever\b",
        r"\beveryone\s+would\s+be\s+better\s+off\s+without\s+me\b",
        r"\bi\s+might\s+hurt\s+myself\b",
        r"\bend\s+it\s+all\b",
    )
    for pattern in medium_patterns:
        if re.search(pattern, text):
            return {
                "crisis_detected": True,
                "crisis_level": "medium",
                "reason": "passive suicidal ideation or self-harm risk matched deterministic safety net",
                "source": "deterministic_safety_net",
            }

    return {
        "crisis_detected": False,
        "crisis_level": "low",
        "reason": "no explicit deterministic crisis pattern matched",
        "source": "deterministic_safety_net",
    }


# ============================================
# DATABASE HELPERS - Fetch exercises from DB
# ============================================

async def _get_technique_from_db(technique_name: str) -> Optional[dict]:
    """
    Fetch technique/exercise from database by name.
    Returns complete exercise data: name, description, steps, etc.
    
    Args:
      technique_name: Exercise name to search for (e.g., "Timeline Journal")
    
    Returns:
      {
        "id": str,
        "name": str,
        "category": str,
        "description": str,
        "brief": str,
        "steps": [str],
        "durationMinutes": int,
        "difficulty": str,
        "whyItWorks": str
      }
      or None if not found
    """
    try:
        from ..db.client import get_prisma_client
        
        prisma = await get_prisma_client()
        
        # Search by exact name match first
        technique = await prisma.technique.find_first(
            where={
                "name": {"equals": technique_name, "mode": "insensitive"},
                "isActive": True
            },
            include={"category": True}
        )
        
        if technique:
            return {
                "id": technique.id,
                "name": technique.name,
                "category": technique.category.name if technique.category else None,
                "description": technique.description,
                "brief": technique.brief,
                "steps": technique.steps,
                "durationMinutes": technique.durationMinutes,
                "difficulty": technique.difficulty,
                "whyItWorks": technique.whyItWorks,
                "targetEmotions": technique.targetEmotions,
                "effectiveness": technique.effectiveness
            }
        
        return None
    except Exception as e:
        logger.warning(f"[DB] Could not fetch technique '{technique_name}': {e}")
        return None


async def _get_techniques_by_category(category_name: str) -> Optional[list]:
    """
    Fetch all active techniques from a category.
    
    Args:
      category_name: Category name (e.g., "Journaling", "Breathing")
    
    Returns:
      List of technique dicts with full details, or None if not found
    """
    try:
        from ..db.client import get_prisma_client
        
        prisma = await get_prisma_client()
        
        # Find techniques by category
        techniques = await prisma.technique.find_many(
            where={
                "category": {
                    "name": {"equals": category_name, "mode": "insensitive"}
                },
                "isActive": True
            },
            include={"category": True}
        )
        
        if techniques:
            return [
                {
                    "id": t.id,
                    "name": t.name,
                    "category": t.category.name if t.category else None,
                    "description": t.description,
                    "brief": t.brief,
                    "steps": t.steps,
                    "durationMinutes": t.durationMinutes,
                    "difficulty": t.difficulty,
                    "whyItWorks": t.whyItWorks,
                    "targetEmotions": t.targetEmotions,
                    "effectiveness": t.effectiveness
                }
                for t in techniques
            ]
        
        return None
    except Exception as e:
        logger.warning(f"[DB] Could not fetch techniques for category '{category_name}': {e}")
        return None


# ============================================
# CRISIS SPECIALIST: Local ELECTRA Model  DISABLED
# Gemini LLM is now the sole decision maker.
# The local sentinet/suicidality model is commented out for performance.
# ============================================

_crisis_classifier = None  # Always returns "unavailable" (local model disabled)


def _get_crisis_classifier():
    """
    Local ELECTRA crisis classifier  DISABLED.
    Returns 'unavailable' immediately so llm_crisis_check falls through
    to the LLM-only path.
    """
    global _crisis_classifier
    if _crisis_classifier is not None:
        return _crisis_classifier

    #  LOCAL MODEL DISABLED 
    # The sentinet/suicidality ELECTRA model is commented out.
    # Gemini handles crisis detection as the sole authoritative LLM decision maker.
    #
    # try:
    #     from transformers import pipeline as hf_pipeline
    #     print("[CLASSIFIER]  Loading crisis specialist model (sentinet/suicidality)...")
    #     _crisis_classifier = hf_pipeline(
    #         "text-classification",
    #         model="sentinet/suicidality",
    #         top_k=None,
    #         truncation=True,
    #         max_length=512
    #     )
    #     print("[CLASSIFIER]  Crisis specialist model loaded.")
    # except Exception as e:
    #     logger.warning(f"[CLASSIFIER]  Could not load sentinet/suicidality: {e}.")
    #     _crisis_classifier = "unavailable"
    # 

    print("[CLASSIFIER] ")
    print("[CLASSIFIER]   LOCAL ELECTRA MODEL  DISABLED                    ")
    print(f"[CLASSIFIER]   Crisis detection: Gemini {MODEL_CRISIS} ")
    print("[CLASSIFIER] ")
    _crisis_classifier = "unavailable"
    return _crisis_classifier


def _parse_json_from_llm(content: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown fences and preamble text.

    Robust multi-strategy parser:
      1. Direct parse (already clean JSON).
      2. Extract JSON from a markdown code fence (```json ... ``` or ``` ... ```).
      3. Brace-balanced extraction — finds the first '{' and walks to its
         matching '}', correctly handling nested objects.
      4. Broad first-'{' to last-'}' fallback.

    Handles LLM preamble text such as "Here is the JSON requested:"
    that sometimes precedes the actual JSON block.
    """
    if not content:
        return None

    content = content.strip()

    # Strategy 1: direct parse (ideal — model returned clean JSON)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract from markdown code fence  ```[json]  ...  ```
    import re as _re
    fence_match = _re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 3: brace-balanced extraction (handles nested objects correctly)
    start = content.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(content[start:], start=start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = content[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break  # malformed — fall through to strategy 4

    # Strategy 4: broad first-'{' to last-'}' fallback
    first = content.find("{")
    last = content.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = content[first:last + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None



async def _call_gemini_async(prompt: str, model: str = MODEL_LIGHT, temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """
    Make an ASYNC Gemini LLM call via the unified LLM manager.
    Returns raw content string or None on failure.

    All LLM classification calls use Gemini model tiers.
    """
    manager = get_llm_manager()
    candidates = [model]
    fallback = getattr(manager, "model_fallback", MODEL_FALLBACK)
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    alt_model = getattr(manager, "model_alt", None)
    if alt_model and alt_model not in candidates:
        candidates.append(alt_model)
    json_models = [model]
    if alt_model:
        json_models.append(alt_model)
    try:
        print(f"[CLASSIFIER]   Calling Gemini | model={model} | max_tokens={max_tokens}")
        response = await manager.ainvoke_gemini_with_rotation(
            prompt,
            model=model,
            model_candidates=candidates,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            response_format_models=json_models,
        )
        print(f"[CLASSIFIER]   Response received  | model={model}")
        return message_content_to_text(response.content if hasattr(response, "content") else response)
    except Exception as e:
        logger.warning(f"[CLASSIFIER]  Gemini call FAILED | model={model} | error: {e}")
    return None


# Keep sync alias for any legacy callers (wraps async in thread executor)
def _call_gemini(prompt: str, model: str = MODEL_LIGHT, temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """Legacy sync wrapper; prefer _call_gemini_async in async contexts."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _call_gemini_async(prompt, model, temperature, max_tokens))
                return future.result(timeout=30)
        else:
            return loop.run_until_complete(_call_gemini_async(prompt, model, temperature, max_tokens))
    except Exception as e:
        logger.warning(f"[CLASSIFIER] Legacy sync Gemini call failed: {e}")
        return None


# ============================================
# CRISIS CLASSIFIER  Gemini (sole LLM decision maker)
# ============================================

async def llm_crisis_check(message: str) -> dict:
    """
    Semantic crisis detection using Gemini as the authoritative LLM decision maker.

    ARCHITECTURE (v8.7  LLM-Only, Fully Async):
      Step 1: Keyword gate handled upstream (graph.py screen_for_crisis Layer 1).
      Step 2: Gemini runs async (await ainvoke) for empathy + clinical reasoning.
              Local ELECTRA model is DISABLED (always returned 'unavailable').

    FIX v8.7: Crisis detection is safety-critical and uses MODEL_HEAVY (70b).

    Returns:
      {
        "crisis_detected": bool,
        "crisis_level": "high" | "medium" | "low",
        "reason": str,
        "source": "llm" | "fallback"
      }
    """
    # ELECTRA disabled; Gemini is the sole LLM decision maker.
    deterministic = deterministic_crisis_safety_net(message)
    if deterministic.get("crisis_detected"):
        print(
            "[CLASSIFIER] SAFETY NET CRISIS RESULT  "
            f"detected=True  level={deterministic.get('crisis_level', '?').upper()}  "
            f"reason='{deterministic.get('reason', '')}'"
        )
        return deterministic

    # ---- CRISIS ANALYSIS: Gemini ----
    print(f"[CLASSIFIER]   CRISIS CHECK    {MODEL_CRISIS} (MODEL_CRISIS) ")
    print("[CLASSIFIER]   3-step dimensional reasoning (desire/context/lethality) ")
    print("[CLASSIFIER]   for accurate mental health safety detection              ")
    print("[CLASSIFIER] ")

    prompt = f"""You are a mental health crisis safety specialist AI. Your ONLY task is to determine whether a message contains genuine suicidal ideation or explicit self-harm risk.

You MUST reason step-by-step across THREE dimensions before giving your final answer. Skipping steps is NOT allowed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP A — DESIRE DIMENSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Does the person express an active, first-person DESIRE or WISH to:
  • Die or end their life
  • Stop existing
  • Physically harm themselves

→ YES: This may indicate crisis. Proceed to Step B and Step C.
→ NO:  This is emotional distress, venting, cognitive distortion, or figurative language.
       Set crisis_detected=false, crisis_level="low". STOP here.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP B — CONTEXT DIMENSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What is the NATURE of the statement? Pick the best match:

  • Emotional venting/distress:
    Describing sadness, loneliness, worthlessness, exhaustion, or worsening mood
    WITHOUT any expressed wish to die.
    → crisis_detected=false, level="low"

  • Cognitive distortion:
    Statements like "I'm worthless", "nobody understands me",
    "I'm the only one who struggles", "I must be perfect".
    These are self-critical thoughts, NOT suicidal ideation.
    → crisis_detected=false, level="low"

  • Figurative / hyperbolic language:
    "I could sleep forever" (after a long week),
    "I want to disappear from social media",
    "tired of fighting" (meaning daily struggles, not life itself).
    → crisis_detected=false, level="low"

  • Passive ideation — wishing NOT to exist, but no active plan:
    "everyone would be better off without me" + expressed wish to be gone.
    → crisis_detected=true, level="medium"

  • Active desire — clear first-person wish to end life, self-harm, or stop living:
    → crisis_detected=true, level="high"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP C — LETHALITY DIMENSION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Is there any specificity — a method, timeline, or concrete plan?

  • YES (e.g. "I have pills ready", "I plan to...", "tonight", "I already cut myself")
    → crisis_detected=true, level="high" (regardless of Steps A and B)
  • NO
    → Rely entirely on Steps A and B for your answer.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINAL RULE — When to set crisis_detected=true
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Set crisis_detected=true ONLY when:
  • Step A = YES (genuine first-person desire, confirmed NOT figurative/distortion) AND Step B = passive or active ideation, OR
  • Step C = YES (lethality specifics present, regardless of framing)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NON-CRISIS EXAMPLES — crisis_detected=false, level="low"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"I feel so lonely, nobody really understands me"        → emotional venting, no desire to die
"Everything feels really heavy lately"                  → metaphorical emotional weight
"I feel so worthless and useless at everything"         → cognitive distortion, no ideation
"I'm the only one who struggles like this"              → mind-reading distortion
"I must be perfect or I'm completely worthless"         → black-and-white thinking
"I'm so tired of fighting every single day"             → exhaustion metaphor (fighting = daily life)
"I could sleep forever after this long week"            → tiredness, figurative
"I want to disappear from social media"                 → digital detox, not ideation
"Every day is worse than the last"                      → worsening mood, no ideation
"I hate myself sometimes"                               → self-criticism, not suicidal ideation
"I feel like I'm drowning in responsibilities"          → stress metaphor, not ideation
"Nobody cares about me anyway"                          → loneliness/distortion, not ideation
"im having a panic attack"                              → acute anxiety episode, NOT suicidal ideation → low
"i think im having a panic attack, heart racing"        → physical anxiety symptoms, NOT self-harm → low
"i cant breathe im shaking"                             → panic/anxiety physical symptoms, NOT ideation → low
"I was beaten by my classmate in front of the whole class" → interpersonal violence by ANOTHER person (already past); anger/shame, no self-harm intent → low
"My father will ask me about job and I won't be able to answer" → family/social pressure, fear of judgment, NOT suicidal ideation → low
"The society judges me if I don't succeed"              → cultural/social pressure, distress, NOT self-harm → low
"I feel very low and overwhelmed about my future"       → emotional distress + worry, no active desire to die → low
"I'm scared I'll disappoint my family"                  → fear of failure, NOT self-harm ideation → low
"I got into a fight at school"                          → interpersonal conflict, not self-directed harm → low
"I feel humiliated in front of everyone"                → shame/embarrassment, NOT suicidal ideation → low
"I'm 22 and feel like I've done nothing with my life"   → cognitive distortion / achievement anxiety, NOT ideation → low
"I'm so stressed about my exams I can barely eat"       → stress + somatic symptoms, NOT self-harm → low

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRISIS EXAMPLES — crisis_detected=true
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"I want to kill myself"                                 → explicit active desire → HIGH
"I don't want to be here anymore" (hopelessness tone)   → passive ideation → MEDIUM
"I have a plan to end my life this weekend"             → lethality specifics → HIGH
"Everyone would be better off without me" + wants gone  → passive ideation → MEDIUM
"I already cut myself tonight"                          → confirmed self-harm → HIGH
"I have pills and I'm ready"                            → lethality + method → HIGH
"I've been thinking about jumping off a bridge"         → method + ideation → HIGH

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond ONLY with this exact JSON. No explanation, no preamble, no extra text:
{{"crisis_detected": true or false, "crisis_level": "high" or "medium" or "low", "reason": "one concise sentence explaining why"}}

Message to classify: "{message}"

JSON:"""

    try:
        content = await _call_gemini_async(prompt, model=MODEL_CRISIS, temperature=0.0, max_tokens=512)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "crisis_detected" in parsed:
                parsed["crisis_level"] = str(parsed.get("crisis_level") or "low").lower()
                if parsed.get("crisis_level") not in {"low", "medium", "high"}:
                    parsed["crisis_level"] = "medium" if parsed.get("crisis_detected") else "low"
                if parsed.get("crisis_level") == "low":
                    parsed["crisis_detected"] = False
                elif parsed.get("crisis_level") in {"medium", "high"}:
                    parsed["crisis_detected"] = True
                parsed["source"] = "llm"
                # Post-LLM panic attack guard: re-run deterministic check.
                # If the message is a panic attack, override any LLM crisis decision.
                _panic_recheck = deterministic_crisis_safety_net(message)
                if _panic_recheck.get("immediate_regulation_request") and parsed.get("crisis_detected"):
                    parsed["crisis_detected"] = False
                    parsed["crisis_level"] = "low"
                    parsed["reason"] = "panic attack override: acute anxiety, not suicidal ideation"
                    parsed["immediate_regulation_request"] = True
                    print("[CLASSIFIER] panic_attack override — LLM crisis result corrected to low/not-crisis")
                crisis_icon = "🚨" if parsed["crisis_detected"] else "✅"
                print(f"[CLASSIFIER] {crisis_icon} CRISIS RESULT  detected={parsed['crisis_detected']}  level={parsed.get('crisis_level','?').upper()}  reason='{parsed.get('reason', '')}'")
                return parsed
    except Exception as e:
        logger.error(f"[CLASSIFIER]  Crisis LLM call FAILED: {e}")

    print("[CLASSIFIER]   Crisis LLM unavailable; deterministic safety net found no explicit crisis pattern")
    return {
        "crisis_detected": False,
        "crisis_level": "low",
        "reason": "Crisis LLM unavailable and deterministic safety net found no explicit self-harm signal",
        "source": "fallback"
    }


# ============================================
# COGNITIVE DISTORTION CLASSIFIER  Gemini
# Stays on MODEL_LIGHT  lightweight pattern matching, not safety-critical
# ============================================

async def llm_distortion_check(message: str) -> dict:
    """
    LLM-assisted cognitive distortion detection.
    Called when keyword confidence is low (< 0.4).
    v5.3: Now truly async via _call_gemini_async.

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
Your ONLY task: identify cognitive distortions in the user message below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISTORTION TYPES — choose from these ONLY (or null):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  catastrophizing    → Expecting the worst possible outcome
  black_white        → All-or-nothing, no middle ground
  overgeneralization → "Always", "never", one event = universal pattern
  mind_reading       → Assuming what others think/feel without evidence
  personalization    → Blaming yourself for things outside your control
  should_statements  → Rigid rules: "I should", "I must", "I have to"
  emotional_reasoning→ "I feel it, therefore it must be true"
  magnification      → Blowing things out of proportion
  null               → No distortion present

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"I always mess everything up"                    → overgeneralization
"If I fail this I'm a total failure"             → black_white
"I'm sure they hate me after what I said"        → mind_reading
"I should be stronger than this"                 → should_statements
"This tiny mistake ruined my entire week"        → catastrophizing
"I feel stupid so I must be stupid"              → emotional_reasoning
"It's all my fault my friend is upset"           → personalization
"This is the absolute worst thing ever"          → magnification
"I'm the only one who can't handle this"         → overgeneralization
"I had a good day today and felt proud"          → null (no distortion)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond ONLY with valid JSON — no explanation, no extra text:
{{"distortion_type": string or null, "confidence": float 0.0-1.0, "all_distortions": [list of strings], "explanation": "brief explanation"}}

Message: "{message}"

JSON:"""

        print(f"[CLASSIFIER]  DISTORTION CHECK  {MODEL_LIGHT}")
        content = await _call_gemini_async(prompt, model=MODEL_LIGHT, temperature=0.0, max_tokens=512)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "distortion_type" in parsed:
                dtype = parsed.get('distortion_type') or 'none'
                conf  = parsed.get('confidence', 0)
                print(f"[CLASSIFIER]  DISTORTION RESULT  type={dtype}  confidence={conf:.0%}")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER]  Distortion check FAILED: {e}")

    return {
        "distortion_type": None,
        "confidence": 0.0,
        "all_distortions": [],
        "explanation": "Classification unavailable"
    }


# ============================================
# v9.0: CLINICAL SEVERITY CHECK  PHQ-9 + GAD-7
# Uses MODEL_HEAVY  clinical assessment is safety-adjacent
# ============================================

async def clinical_severity_check(
    message: str,
    recent_context: str = "",
    emotion: str = "neutral",
    intensity: float = 0.5,
    emotional_trend: str = "stable",
) -> dict:
    """
    Clinical severity assessment using PHQ-9 and GAD-7 criteria.

    The LLM evaluates conversational cues against standardized clinical
    instrument criteria to estimate severity level.

    Returns:
      {
        "severity": "minimal" | "mild" | "moderate" | "moderately_severe" | "severe",
        "phq9_scores": {"q1":0,...,"q9":0},
        "gad7_scores": {"g1":0,...,"g7":0},
        "phq9_total": int (0-27),
        "gad7_total": int (0-21),
        "clinical_indicators": ["anhedonia", "sleep_disturbance", ...],
        "confidence": float (0.0-1.0),
        "reasoning": str
      }
    """
    try:
        prompt = f"""You are a clinical screening assistant. Evaluate conversational cues against PHQ-9 and GAD-7.

IMPORTANT: This is NOT a formal questionnaire unless the user explicitly answers
PHQ-9/GAD-7 frequency questions. Treat normal chat as clinical EVIDENCE for the
current turn. The system will aggregate this result with prior sessions.

━━━ PHQ-9: PATIENT HEALTH QUESTIONNAIRE (Depression) ━━━
Score each item 0-3 based on evidence in the conversation:
  0=Not at all  1=Several days  2=More than half the days  3=Nearly every day

Q1. Little interest or pleasure in doing things (anhedonia)
Q2. Feeling down, depressed, or hopeless (depressed_mood)
Q3. Trouble falling/staying asleep, or sleeping too much (sleep_disturbance)
Q4. Feeling tired or having little energy (fatigue)
Q5. Poor appetite or overeating (appetite_change)
Q6. Feeling bad about yourself — failure, let family down (worthlessness)
Q7. Trouble concentrating on things (concentration)
Q8. Moving/speaking slowly OR being fidgety/restless (psychomotor)
Q9. Thoughts of being better off dead or hurting yourself (suicidal_ideation)

PHQ-9 TOTAL → SEVERITY:
  0-4=MINIMAL  5-9=MILD  10-14=MODERATE  15-19=MODERATELY_SEVERE  20-27=SEVERE

━━━ GAD-7: GENERALIZED ANXIETY DISORDER SCALE ━━━
G1. Feeling nervous, anxious, or on edge (nervousness)
G2. Not being able to stop or control worrying (uncontrollable_worry)
G3. Worrying too much about different things (excessive_worry)
G4. Trouble relaxing (restlessness)
G5. Being so restless it's hard to sit still (motor_restlessness)
G6. Becoming easily annoyed or irritable (irritability)
G7. Feeling afraid, as if something awful might happen (dread)

GAD-7 TOTAL → SEVERITY:
  0-4=MINIMAL  5-9=MILD  10-14=MODERATE  15-21=SEVERE

━━━ RULES ━━━
1. Score ONLY items with DIRECT evidence in the current message or immediately recent context. No evidence = 0.
2. If a symptom is present but frequency/duration is unstated, score 1 ("several days") — never assume 2 or 3.
3. Use score 2 ONLY when the user explicitly states "most days", "more than half the days", or clear persistent wording.
4. Use score 3 ONLY when the user explicitly states "nearly every day" or clearly implies daily occurrence.
5. Overall severity = MAX(PHQ-9 severity, GAD-7 severity) for THIS TURN'S evidence only.
6. List indicators ONLY for items scoring >= 2 in this turn.
7. If Q9 >= 2 → flag suicidal_ideation regardless of total.
8. NEVER inflate scores to match emotional intensity. Distressed tone without explicit frequency = score 1, not 2/3.
9. If the user reports a technique helped, feeling better, or calmer, reduce scores for matching symptoms — do not carry prior distress forward.
10. Recent context is for disambiguation only. Score from THIS message's own explicit content first.
11. Most single-turn assessments should total 0–10 (PHQ) and 0–9 (GAD). Totals above 15 require explicit multi-day frequency statements from the user.

━━━ CONTEXT ━━━
Detected emotion: {emotion} at {intensity:.0%} intensity
Emotional trend: {emotional_trend}
Recent conversation:
{recent_context}
Current message: "{message}"

━━━ OUTPUT — JSON ONLY ━━━
{{"severity":"minimal|mild|moderate|moderately_severe|severe","phq9_scores":{{"q1":0,"q2":0,"q3":0,"q4":0,"q5":0,"q6":0,"q7":0,"q8":0,"q9":0}},"gad7_scores":{{"g1":0,"g2":0,"g3":0,"g4":0,"g5":0,"g6":0,"g7":0}},"phq9_total":0,"gad7_total":0,"clinical_indicators":[],"confidence":0.0,"reasoning":"one sentence justification"}}

JSON:"""

        high_risk_signal = intensity >= 0.85 or emotion in {"fear", "anger", "sadness"}
        clinical_model = MODEL_HEAVY if high_risk_signal else MODEL_MOOD
        print(f"[CLASSIFIER] 🏥 CLINICAL SEVERITY CHECK → {clinical_model}")
        content = await _call_gemini_async(prompt, model=clinical_model, temperature=0.0, max_tokens=512)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "severity" in parsed:
                severity = parsed.get("severity", "minimal")
                phq9 = parsed.get("phq9_total", 0)
                gad7 = parsed.get("gad7_total", 0)
                indicators = parsed.get("clinical_indicators", [])
                confidence = parsed.get("confidence", 0.0)
                print(f"[CLASSIFIER] CLINICAL: severity={severity.upper()} phq9={phq9} gad7={gad7} indicators={len(indicators)} confidence={confidence:.0%}")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] 🏥 Clinical severity check FAILED: {e}")

    return {
        "severity": "minimal",
        "phq9_scores": {"q1":0,"q2":0,"q3":0,"q4":0,"q5":0,"q6":0,"q7":0,"q8":0,"q9":0},
        "gad7_scores": {"g1":0,"g2":0,"g3":0,"g4":0,"g5":0,"g6":0,"g7":0},
        "phq9_total": 0,
        "gad7_total": 0,
        "clinical_indicators": [],
        "confidence": 0.0,
        "reasoning": "Assessment unavailable - using safe default"
    }


# ============================================
# CONVERSATION INTENT CLASSIFIER  Gemini
# Stays on MODEL_LIGHT  downstream from gate, lightweight classification
# ============================================

async def llm_intent_check(message: str, recent_context: str = "") -> dict:
    """
    LLM-assisted intent classification for the conversation planner.
    v5.3: Now truly async via _call_gemini_async.
    v9.1: Added positive_feedback intent for exercise feedback

    Returns:
      {
        "intent": "therapeutic" | "contextual_followup" | "technique_request" | "technique_follow_up" | "memory_query" | "advice_seeking" | "reflection" | "venting" | "chitchat" | "crisis_signal" | "positive_feedback",
        "confidence": float
      }
    """
    try:
        prompt = f"""You are a precise intent classifier for a mental health companion app. Classify the USER's LATEST message only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Choose EXACTLY ONE intent from this list:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  therapeutic | contextual_followup | technique_request | technique_follow_up | memory_query | advice_seeking | reflection | venting | chitchat | crisis_signal | positive_feedback | technique_not_helpful | technique_partial_helpful | user_initiated_exit

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFINITIONS — be strict, read each carefully:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

positive_feedback (NEW v9.1):
  User is expressing that an exercise/technique HELPED or is WORKING.
  This is FEEDBACK on something the AI already provided, not a new request.
  Key signals: 'it helped', 'it's helping', 'it's good', 'it works', 'i like this',
               'that was good', 'feeling better', 'it's working', 'that helped',
               'yes it helped', 'much better', 'calmer now', 'it is helping me'.
  Context: Usually follows right after AI provided an exercise or technique.
  IMPORTANT: This differs from 'venting' — user is NOT expressing distress,
             they are confirming a POSITIVE OUTCOME.

contextual_followup:
  The latest message is short, pronoun-based, or clearly answers the previous
  assistant question. Use recent context instead of treating it as standalone.
  Examples: "About 3 weeks", "Maths", "yes i does have", "what do you think about it?"

technique_follow_up:
  The user is accepting, rejecting, discussing, or reporting on a technique
  already offered. Examples: "yes go for it", "I didn't like that exercise".

memory_query:
  The user asks for something previously mentioned or stored. Examples:
  "what was its name?", "which technique was that?"

technique_request:
  User is EXPLICITLY asking for an exercise, breathing drill, meditation,
  or wants a DIFFERENT/ALTERNATIVE technique.
  Key signals: "try another", "different exercise", "teach me",
               "give me a technique", "breathing exercise", "want to practice".

advice_seeking:
  User asks for general guidance, direction, or next steps WITHOUT asking
  for a specific clinical exercise.
  Key signals: "what should I do?", "how do I handle this?",
               "any tips?", "I need help with", "what can I do?".
  NOTE: "I am having difficulty expressing myself, what should I do?"
        = advice_seeking, NOT technique_request.

reflection:
  User demonstrates self-awareness, insight, or asks introspective questions.
  Key signals: "I think I", "I realize", "maybe it's because",
               "why do I feel", "I wonder if".

venting:
  User expresses strong emotion, complains, shares hardship, but is NOT
  asking for help yet. Just needs to be heard.
  IMPORTANT: Do NOT classify positive_feedback as venting.
  If user is saying exercise/technique HELPED → positive_feedback, not venting.
  Key signals: emotional statements, frustration, sadness, anger,
               "I feel...", "I can't...", "it's so hard".

chitchat:
  Casual, social, or off-topic message with no emotional distress.
  Key signals: greetings, jokes, questions about weather, tech, facts.
  ALWAYS chitchat: name/identity corrections ("im not X im Y",
  "my name is not X", "call me Y not X"), even if wording sounds frustrated.

crisis_signal:
  User implies hopelessness, wishes to disappear, self-harm, or suicidal ideation.
  Key signals: "I want to die", "nobody cares", "disappear", "end it all".

technique_not_helpful:
  User reports that a technique/exercise did NOT help or made no difference after trying it.
  This differs from rejection (refusing before trying) — this user TRIED it and it did not work.
  Key signals: "that didn't help", "didn't work", "still feel the same", "it did nothing",
               "that wasn't helpful", "i still feel bad", "no change", "made no difference",
               "felt worse after", "it didn't do anything for me".
  Context: Always follows a technique offer/delivery. Do NOT use for "I don't want to try it"
           (that is technique_follow_up/rejection).

technique_partial_helpful:
  User reports the technique helped PARTIALLY or a little bit, but not fully resolved.
  This is between positive_feedback (fully helped) and technique_not_helpful (didn't help).
  Key signals: "helped a little", "kind of helped", "somewhat better", "a bit calmer but still",
               "slightly better", "it helped but i'm still anxious", "partially worked",
               "a bit better", "helped somewhat", "not fully but a little better".
  Context: Improvement is acknowledged but the issue is not fully resolved.
  IMPORTANT: Do NOT use positive_feedback for partial — only positive_feedback when user is
             clearly stating it FULLY helped or they feel much better.

user_initiated_exit:
  User explicitly signals they are ending the session right now — on their own terms,
  NOT because the issue is resolved. The focus is on leaving, not on outcomes.
  Key signals: "I have to go", "gotta run", "thanks bye", "I'm done for today",
               "I need to stop", "goodbye", "talk later", "I'll try again later",
               "signing off", "I need to leave", "I'll come back another time".
  IMPORTANT: Only use when the user is LEAVING, not when expressing frustration.
             "I'm done with this exercise" = technique_not_helpful, NOT user_initiated_exit.
             "I can't do this" = venting or crisis_signal, NOT user_initiated_exit.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES FOR POSITIVE_FEEDBACK v9.1:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. If user says exercise/technique HELPED or is HELPING → positive_feedback
2. If user confirms exercise WORKED or is WORKING → positive_feedback
3. If user expresses IMPROVEMENT after exercise → positive_feedback
4. If user likes an exercise they already tried → positive_feedback
5. Do NOT confuse with venting (that's distress/emotional expression)
6. Do NOT confuse with technique_request (that's asking for a new exercise)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES — read context carefully:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"i like this one exercise its good"                                 → positive_feedback
"yes it helped me"                                                  → positive_feedback
"it is helping"                                                     → positive_feedback
"feeling a bit better now"                                          → positive_feedback
"that actually worked"                                              → positive_feedback
"i feel calmer after doing that"                                    → positive_feedback
"this exercise is good"                                             → positive_feedback
"yeah that helped"                                                  → positive_feedback

"I'm so stressed about my exams"                                    → venting
"It didn't help me" [previous AI had NO technique]                  → venting
"It didn't help me" [previous AI HAD suggested a technique]         → technique_not_helpful
"that exercise did nothing for me"                                  → technique_not_helpful
"i still feel the same after doing it"                              → technique_not_helpful
"it helped a little but i'm still anxious"                          → technique_partial_helpful
"somewhat better, not fully though"                                 → technique_partial_helpful
"kind of worked but I still feel some stress"                       → technique_partial_helpful
"I have to go now, thanks"                                          → user_initiated_exit
"Gotta run, talk later"                                             → user_initiated_exit
"I'm done for today, bye"                                           → user_initiated_exit
"Thanks for the help, goodbye"                                      → user_initiated_exit
"I'll try again another time"                                       → user_initiated_exit
"I need to stop here, I have things to do"                          → user_initiated_exit
"What should I do to feel better?" [no specific exercise asked]     → advice_seeking
"Can you give me a breathing exercise?"                             → technique_request
"Maybe my anxiety comes from my childhood"                          → reflection
"Hey, how's it going?"                                              → chitchat
"im not taram im taha mehmood"                                      → chitchat (name correction)
"I don't want to exist anymore"                                     → crisis_signal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond ONLY with valid JSON — no extra text, no explanation:
{{"intent": "<chosen_intent>", "confidence": <float 0.0-1.0>}}

Previous Conversation Context (use for disambiguation only):
{recent_context}

User's Latest Message: "{message}"

JSON:"""

        print(f"[CLASSIFIER] 💬 INTENT CHECK → {MODEL_LIGHT}")
        content = await _call_gemini_async(prompt, model=MODEL_LIGHT, temperature=0.0, max_tokens=512)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "intent" in parsed:
                print(f"[CLASSIFIER] 💬 INTENT RESULT | intent={parsed.get('intent')} | confidence={parsed.get('confidence', 0):.0%}")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] Intent check FAILED: {e}")

    print("[CLASSIFIER] Intent check failed - defaulting to venting")
    return {"intent": "venting", "confidence": 0.0}


async def llm_intent_pre_check(message: str, recent_context: str = "") -> dict:
    """
    v5.3 NEW: Lightweight intent pre-check for parallel_intake.

    Identical to llm_intent_check but named separately so parallel_intake
    can import and launch it as a 4th concurrent task alongside crisis screening,
    intake loading, and mood analysis.

    The result is stored as state["prefetched_intent"] and consumed by
    conversation_planner_node which skips its own LLM call when available.

    This removes the intent LLM call from the serial critical path entirely.
    """
    print("[CLASSIFIER] PREFETCH | Intent check starting concurrently with intake...")
    result = await llm_intent_check(message, recent_context)
    print(f"[CLASSIFIER] PREFETCH | Intent done -> {result.get('intent')} ({result.get('confidence', 0):.0%}) - stored for planner")
    return result


# ============================================================
# SMART PIPELINE GATE - Pre-graph LLM Decision Router
# ============================================================

_CORE_GATE_ROUTES = {
    "chitchat",
    "therapeutic",
    "contextual_followup",
    "technique_request",
    "technique_follow_up",
    "memory_query",
    "crisis",
    "positive_feedback",
}

_MOOD_SKIP_ROUTES = {
    "chitchat",
    "contextual_followup",
    "technique_follow_up",
    "memory_query",
    "positive_feedback",
}


def _as_float(value, default: float = 0.0, *, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = default
    return max(lo, min(hi, numeric))


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return default


def _normalize_context_flags(flags) -> list[str]:
    if not isinstance(flags, list):
        return []
    normalized: list[str] = []
    for flag in flags:
        if not flag:
            continue
        clean = str(flag).strip().lower().replace(" ", "_")
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized




def _message_says_no_more_details(message: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", (message or "").lower()).strip()
    if clean in {
        "no nothing more",
        "nothing more",
        "nothing else",
        "no more",
        "nope nothing else",
        "nah nothing else",
        "thats all",
        "that is all",
        "thats it",
        "that is it",
        "no thats all",
        "no that is all",
        "no thats it",
        "no that is it",
        "i shared everything",
        "i have shared everything",
        "ive shared everything",
        "i told you everything",
        "i dont know what else",
        "i do not know what else",
        "nothing specific",
    }:
        return True
    return any(
        marker in clean
        for marker in (
            "shared everything with you",
            "shared everything with u",
            "told you everything",
            "dont have any other details",
            "do not have any other details",
            "no other details",
            "nothing else to add",
            "nothing more to add",
        )
    )


def _build_smart_gate_prompt(
    *,
    message: str,
    recent_context: str,
    user_context: str,
    session_context: dict,
) -> str:
    session_formatted = (session_context or {}).get("formatted_context", "")
    return f"""You are SentiMind's strict, context-aware routing gate.

Your job is to classify ONLY the latest user message while using recent session context.
Return strict JSON only. Do not include markdown, commentary, or extra keys.

Core principle:
UNDERSTAND FIRST -> CLARIFY -> FORMULATE -> INTERVENE -> FOLLOW UP

Allowed routes:
- chitchat
- therapeutic
- contextual_followup
- technique_request
- technique_follow_up
- memory_query
- crisis
- positive_feedback

Routing rules:
1. Crisis overrides everything — BUT ONLY for genuine self-harm or suicidal content.
   Route crisis ONLY when the user expresses:
     a) An explicit first-person desire or plan to die or end their own life ("I want to kill myself", "I am going to end it")
     b) Active self-harm they are doing or have just done ("I cut myself tonight", "I already hurt myself")
     c) A specific method, means, or timeline for suicide ("I have pills ready", "I plan to jump tonight")

   These are NOT crisis — route therapeutic instead:
     • "I feel worthless" or "I feel like nothing"             → cognitive distortion, not suicidal ideation
     • Being harassed, bullied, beaten, or discriminated against by others  → harm FROM others, not self-harm
     • Racism, sexism, or social discrimination                → social harm, not self-harm
     • "I feel humiliated", "they make me feel like I don't matter"  → shame/distress, not ideation
     • "I don't know what to do", "I feel hopeless about my situation" → emotional distress without ideation
     • Any situation where the HARM comes from another person or society, not from the user themselves

   The distinction: crisis = user intends harm TO THEMSELVES. Therapeutic = user is suffering BECAUSE OF others or circumstances.

2. If the message is short and depends on the previous assistant question, route contextual_followup.
3. If it answers the previous assistant question, route contextual_followup.
4. If it contains "it", "that", "that one", "that exercise", or "what do you think about it?", use recent context.
5. If the user says there are no more details ("nothing else", "I shared everything", "that's all"), route contextual_followup with flags no_more_details and context_complete.
6. Technique rejection ("I didn't like that exercise", "that didn't help") -> technique_follow_up, flags include reject_technique and technique_rejection. Do not treat as anger/crisis.
7. Ambiguous affirmations are context-dependent. Do not classify by the word alone.
   - If the assistant's immediately previous question asked whether the user wants to try a specific technique/exercise, an affirmation means technique_follow_up with accept_technique.
   - If the assistant's immediately previous question asked for context/details, an affirmation means contextual_followup with answering_previous_question.
   - If the user says the prior technique helped/worked/calmed them, route positive_feedback, not accept_technique.
   - "thanks", "thank you", "ok thanks", or "thanks for it" alone are polite acknowledgement, not acceptance and not positive outcome feedback.
   - "yes thanks" only means acceptance when the immediately previous assistant turn was a technique consent offer.
   - "no thanks" after a technique offer means the user declined the exercise for now; set exercise_consent="denied_soft" and solution_preference="listen_only".
   - A stored older technique is not enough for accept_technique; the immediately previous assistant turn must be a technique consent offer.
8. Positive result after a technique -> positive_feedback.
9. Asking for a previously mentioned item/name ("what was its name?", "which technique was that?") -> memory_query.
10. New emotional disclosure ("I feel anxious about exams") -> therapeutic, not technique_request.
11. User explicitly asks for an exercise, technique, or practical coping tool -> technique_request.
12. Casual greeting or small talk without distress -> chitchat.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONSENT & CORRECTION DETECTION RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You MUST analyze if the user's latest message contains a change or expression of exercise consent, solution preferences, or memory corrections/suppressions:

1. Exercise Consent (`exercise_consent`):
   - "denied": User explicitly refuses exercises, meditation, breathing drills, or says they don't want any techniques right now. E.g., "no exercises", "I don't want exercises".
   - "allowed": User explicitly accepts an exercise offered or wants to do one. E.g., "sure, let's try", "yes please".
   - "unknown": Default if no clear consent or denial is expressed in this turn.

2. Solution Preference (`solution_preference`):
   - "listen_only": User explicitly states they just want to talk, vent, be heard, or don't want advice/solutions/exercises. E.g., "just listen to me", "just need to vent".
   - "advice_allowed": User asks for general advice, suggestions, or what to do, without explicitly asking for a clinical exercise/technique. E.g., "what should I do?", "any suggestions?".
   - "exercise_requested": User explicitly asks for an exercise, technique, breathing drill, or accepts an offered one.
   - "unknown": Default if no preference is expressed in this turn.

3. Topic Suppression & Corrections (`suppressed_topics` and `active_issue_source`):
   - If the user explicitly corrects a past topic or reason (e.g., "that has nothing to do with my teacher", "stop talking about my brother", "I already told you that's not the reason"):
     * Set `suppression_signal` to "corrects_history".
     * Set `suppressed_topic` to the specific label/person/subject they are correcting (e.g. "teacher", "brother", "uncle").
     * Set `active_issue_source` to the new correct reason they state (e.g., if they say "it is actually about my exam stress", set active_issue_source to "exam stress"). Otherwise, set to null.
   - Otherwise, set `suppression_signal` to "none", `suppressed_topic` to null, and `active_issue_source` to null.

Context flag examples:
- "About 3 weeks" -> route contextual_followup, flags ["duration_answer", "answering_previous_question"]
- "Maths" -> route contextual_followup, flags ["subject_answer", "answering_previous_question"]
- "What do you think about it?" -> route contextual_followup, flags ["asking_opinion", "refers_to_previous_topic"]
- Short affirmation answering a context question -> route contextual_followup, flags ["answering_previous_question"]
- "No, I shared everything" -> route contextual_followup, flags ["answering_previous_question", "no_more_details", "context_complete"]
- Short affirmation after a technique consent offer -> route technique_follow_up, flags ["accept_technique"]
- "I didn't like that exercise." -> route technique_follow_up, flags ["reject_technique", "technique_rejection"]
- "What was its name?" -> route memory_query, flags ["technique_name_query", "refers_to_previous_technique"]
- "I have been feeling anxious about exams." -> route therapeutic, flags ["new_emotional_disclosure"]
- "I want to die." -> route crisis, flags ["self_harm_risk"]
- "I feel worthless because of the racism I face." -> route therapeutic, flags ["new_emotional_disclosure", "distress_signal"] — worthlessness from discrimination is distress, NOT suicidal ideation
- "They harass me and make me feel like I am nothing." -> route therapeutic, flags ["new_emotional_disclosure", "distress_signal"] — harm by others, not self-harm
- "I was beaten and humiliated in front of everyone." -> route therapeutic, flags ["new_emotional_disclosure"] — past assault by another person, no self-harm intent
- "I feel so low and worthless, I don't know what to do." -> route therapeutic, flags ["new_emotional_disclosure", "distress_signal"] — distress without ideation

Therapeutic pacing:
- Do not classify first emotional disclosures as technique_request unless the user explicitly asks for a technique/help.
- Technique suggestions are allowed later only when the planner has enough context.
- Disapproval/rejection is a mild negative complaint unless the wording contains strong distress.

Recent conversation:
{recent_context[-1200:] if recent_context else "None"}

Stored user context:
{user_context[:1200] if user_context else "None"}

Current session summary/context:
{session_formatted[:1000] if session_formatted else "None"}

Latest user message:
"{message}"

Return exactly this JSON shape:
{{
  "route": "chitchat | therapeutic | contextual_followup | technique_request | technique_follow_up | memory_query | crisis | positive_feedback",
  "confidence": 0.0,
  "reasoning": "short explanation",
  "emotional_register": "neutral | concern | complaint | distress | crisis | positive",
  "context_flags": [],
  "intensity_hint": 0.0,
  "needs_full_pipeline": true,
  "should_skip_mood_analysis": false,
  "exercise_consent": "unknown | denied_soft | denied_hard | allowed",
  "solution_preference": "unknown | listen_only | advice_allowed | exercise_requested",
  "suppression_signal": "none | corrects_history",
  "suppressed_topic": null,
  "active_issue_source": null,
  "metadata": {{
    "accepted_technique": null,
    "technique_category": null,
    "feedback_sentiment": null
  }}
}}

JSON:"""


def _normalize_smart_gate_result(parsed: dict, message: str, recent_context: str = "") -> dict:
    metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
    raw_route = str(parsed.get("route", "therapeutic") or "therapeutic").strip().lower()
    raw_route = raw_route.replace("-", "_").replace(" ", "_")
    flags = _normalize_context_flags(parsed.get("context_flags"))
    last_ai = last_ai_from_recent_context(recent_context)
    technique_offer_pending = assistant_offered_technique(last_ai)

    # Backward compatibility for older route labels that may still appear in
    # logs, tests, or cached prompts while the new gate prompt rolls out.
    if raw_route == "accept_technique":
        raw_route = "technique_follow_up"
        flags.append("accept_technique")
    elif raw_route == "rejection":
        raw_route = "technique_follow_up"
        flags.extend(["reject_technique", "technique_rejection"])
    elif raw_route == "list_techniques":
        raw_route = "technique_request"
        flags.append("list_techniques")

    if raw_route not in _CORE_GATE_ROUTES:
        raw_route = "therapeutic"

    lower = (message or "").lower()
    # Deterministic short-turn guardrail. LLMs often over-read "yes/thanks" as
    # acceptance or recovery. In this app those meanings require context.
    if raw_route != "crisis":
        if is_no_thanks(message) and technique_offer_pending:
            raw_route = "contextual_followup"
            flags.extend(["decline_technique_offer", "technique_declined"])
            metadata["feedback_sentiment"] = "declined"
            parsed["exercise_consent"] = "denied_soft"
            parsed["solution_preference"] = "listen_only"
        elif has_negative_feedback_signal(message):
            raw_route = "technique_follow_up"
            flags.extend(["reject_technique", "technique_rejection"])
            metadata["feedback_sentiment"] = "ineffective"
            metadata["feedback_type"] = "negative"
        elif has_positive_outcome_signal(message):
            raw_route = "positive_feedback"
            flags.extend(["positive_feedback", "outcome_feedback"])
            metadata["feedback_sentiment"] = metadata.get("feedback_sentiment") or "helpful"
            metadata["feedback_type"] = "positive"
            parsed["exercise_consent"] = "unknown"
        elif technique_offer_pending and is_technique_acceptance_reply(message):
            raw_route = "technique_follow_up"
            flags.extend(["accept_technique", "technique_acceptance_answer"])
            parsed["exercise_consent"] = "allowed"
            parsed["solution_preference"] = "exercise_requested"
        elif "?" in last_ai and bool({"yes", "yeah", "yep", "yup"} & set(plain_text(message).split())):
            raw_route = "contextual_followup"
            flags.extend(["answering_previous_question"])
            parsed["exercise_consent"] = "unknown"
            parsed["solution_preference"] = "unknown"
        elif is_polite_acknowledgement(message):
            raw_route = "chitchat"
            flags.extend(["acknowledgement", "gratitude_acknowledgement"])
            metadata["feedback_sentiment"] = None
            metadata["feedback_type"] = None
            parsed["exercise_consent"] = "unknown"
            parsed["solution_preference"] = "unknown"

        if "gratitude_acknowledgement" in flags or "low_signal_affirmation" in flags:
            flags = [
                flag for flag in flags
                if flag not in {"accept_technique", "positive_feedback", "outcome_feedback"}
            ]
        if "decline_technique_offer" in flags or (
            raw_route == "contextual_followup" and "answering_previous_question" in flags
        ):
            flags = [flag for flag in flags if flag != "accept_technique"]
        if raw_route == "positive_feedback":
            flags = [flag for flag in flags if flag != "accept_technique"]
        # If the previous response already delivered steps inline, "yes" is not
        # technique acceptance — strip any LLM-generated accept_technique flag.
        if assistant_likely_gave_steps(last_ai) and "accept_technique" in flags:
            flags = [f for f in flags if f != "accept_technique"]
            if raw_route == "technique_follow_up":
                raw_route = "contextual_followup"
                flags.append("technique_following_up")
        if is_explicit_exercise_request(message):
            raw_route = "technique_request"
            flags.extend(["explicit_technique_request", "help_request"])
            parsed["exercise_consent"] = "allowed"
            parsed["solution_preference"] = "exercise_requested"

    if raw_route != "crisis" and _message_says_no_more_details(message):
        raw_route = "contextual_followup"
        flags.extend(["answering_previous_question", "no_more_details", "context_complete"])

    if raw_route == "technique_follow_up":
        if any(s in lower for s in ("didn't like", "did not like", "didn't help", "did not help", "not helpful", "not useful", "not working", "doesn't suit me", "does not suit me", "style suits me", "not for me", "didn't land", "did not land", "my mind argued with it")):
            flags.extend(["reject_technique", "technique_rejection"])

    if raw_route == "memory_query" and any(s in lower for s in ("what was", "its name", "which technique", "which exercise", "what was that called", "what was it called", "remind me what", "name of that")):
        flags.extend(["technique_name_query", "refers_to_previous_technique"])

    if raw_route == "positive_feedback":
        flags.append("positive_feedback")

    # Deduplicate after compatibility additions.
    flags = _normalize_context_flags(flags)

    confidence = _as_float(parsed.get("confidence"), 0.5)
    register = str(parsed.get("emotional_register") or "neutral").strip().lower()
    if register not in {"neutral", "concern", "complaint", "distress", "crisis", "positive"}:
        register = {
            "technique_follow_up": "complaint" if "reject_technique" in flags else "neutral",
            "positive_feedback": "positive",
            "crisis": "crisis",
            "therapeutic": "concern",
        }.get(raw_route, "neutral")

    default_hint = {
        "chitchat": 0.0,
        "memory_query": 0.05,
        "contextual_followup": 0.2,
        "technique_follow_up": 0.3,
        "positive_feedback": 0.1,
        "crisis": 0.95,
        "therapeutic": 0.45,
        "technique_request": 0.35,
    }.get(raw_route, 0.2)
    intensity_hint = _as_float(parsed.get("intensity_hint"), default_hint)
    if raw_route == "contextual_followup":
        intensity_hint = min(intensity_hint, 0.35)
    if "reject_technique" in flags or "technique_rejection" in flags:
        intensity_hint = min(intensity_hint, 0.45)
    if raw_route in {"memory_query", "chitchat"}:
        intensity_hint = min(intensity_hint, 0.1 if raw_route == "memory_query" else 0.0)

    needs_full = _as_bool(
        parsed.get("needs_full_pipeline"),
        raw_route in {"therapeutic", "contextual_followup", "technique_request", "crisis"},
    )
    should_skip_mood = _as_bool(
        parsed.get("should_skip_mood_analysis"),
        raw_route in _MOOD_SKIP_ROUTES,
    )

    # v11.0 Consent and Suppression fields
    ex_consent = str(parsed.get("exercise_consent") or "unknown").strip().lower()
    if ex_consent not in {"unknown", "denied", "allowed"}:
        ex_consent = "unknown"

    sol_pref = str(parsed.get("solution_preference") or "unknown").strip().lower()
    if sol_pref not in {"unknown", "listen_only", "advice_allowed", "exercise_requested"}:
        sol_pref = "unknown"

    sup_sig = str(parsed.get("suppression_signal") or "none").strip().lower()
    if sup_sig not in {"none", "corrects_history"}:
        sup_sig = "none"

    sup_topic = parsed.get("suppressed_topic")
    if sup_topic:
        sup_topic = str(sup_topic).strip()
    else:
        sup_topic = None

    act_issue = parsed.get("active_issue_source")
    if act_issue:
        act_issue = str(act_issue).strip()
    else:
        act_issue = None

    normalized = {
        "route": raw_route,
        "confidence": confidence,
        "reasoning": str(parsed.get("reasoning") or ""),
        "emotional_register": register,
        "context_flags": flags,
        "intensity_hint": intensity_hint,
        "needs_full_pipeline": bool(needs_full),
        "should_skip_mood_analysis": bool(should_skip_mood),
        "run_full_pipeline": bool(needs_full),
        "metadata": metadata,
        "exercise_consent": ex_consent,
        "solution_preference": sol_pref,
        "suppression_signal": sup_sig,
        "suppressed_topic": sup_topic,
        "active_issue_source": act_issue,
    }
    # If the LLM flagged panic_attack_reported but still returned crisis, correct it.
    # Panic attacks are acute anxiety — the LLM makes this mistake when prior session
    # context shows high distress. The flag is a contradiction with crisis route.
    if normalized["route"] == "crisis" and "panic_attack_reported" in (normalized["context_flags"] or []):
        normalized["route"] = "therapeutic"
        normalized["confidence"] = 0.9
        normalized["reasoning"] = "panic_attack_reported flag set — LLM crisis route overridden to therapeutic"
        normalized["immediate_regulation_request"] = True
        print("[GATE] panic_attack_reported override — route corrected crisis→therapeutic")
    return normalized

async def smart_pipeline_gate(message: str, recent_context: str = "", user_context: str = "", session_context: dict = None) -> dict:
    """
    v8.7 PRIORITY ROUTING: LLM decides route BEFORE therapeutic analysis.

    FIX v8.7: Uses llama-3.3-70b-instruct.
    8b was misrouting chitchat→therapeutic, accept_technique→therapeutic,
    and failing to respect the priority order consistently.

    NEW FLOW:
      Step 1: LLM classifies message into 7 routes (priority order, first match wins)
      Step 2: Check if route should skip full pipeline
      Step 3: If accept_technique/list_techniques/chitchat/memory_query/rejection -> Fetch DB data if needed, skip therapeutic
      Step 4: If therapeutic/crisis -> Run full pipeline

    Routes (priority order — first match WINS, do NOT continue checking):
      1. accept_technique  - User explicitly wants specific exercise (skip therapeutic)
      2. chitchat          - Casual message (skip pipeline)
      3. memory_query      - Asking about history (skip pipeline)
      4. list_techniques   - Wants exercise list (skip therapeutic)
      5. rejection         - Rejects exercises (skip therapeutic)
      6. crisis            - Self-harm/suicide (run full pipeline with priority)
      7. therapeutic       - Emotional distress/needs help (run full pipeline)

    Returns:
      {
        "route": "chitchat" | "memory_query" | "list_techniques" | "accept_technique" | "rejection" | "therapeutic" | "crisis",
        "confidence": float,
        "reasoning": str,
        "run_full_pipeline": bool,
        "metadata": {
          "accepted_technique": str or null,
          "technique_category": str or null,
          "feedback_category": str or null,
          "feedback_sentiment": str or null,
          "exercise_data": dict or null,
          "category_exercises": list or null
        }
      }
    """
    try:
        if session_context is None:
            session_context = {
                "description": "",
                "facts": [],
                "formatted_context": ""
            }

        deterministic = deterministic_crisis_safety_net(message)
        if deterministic.get("crisis_detected"):
            level = deterministic.get("crisis_level", "medium")
            print(f"[GATE] Safety-net crisis route | level={level} | reason={deterministic.get('reason')}")
            return {
                "route": "crisis",
                "confidence": 0.99,
                "reasoning": deterministic.get("reason", "deterministic crisis safety net"),
                "emotional_register": "crisis",
                "context_flags": ["self_harm_risk", "deterministic_safety_net"],
                "intensity_hint": 0.95,
                "needs_full_pipeline": True,
                "should_skip_mood_analysis": False,
                "run_full_pipeline": True,
                "exercise_consent": "unknown",
                "solution_preference": "unknown",
                "suppression_signal": "none",
                "suppressed_topic": None,
                "active_issue_source": None,
               
                "metadata": {"crisis_level": level, "source": deterministic.get("source")},
            }

      

        # Build context sections
        user_bg_section = ""
        if user_context and user_context.strip():
            user_bg_section = (
                f"USER BACKGROUND AND HISTORY (from database):\n"
                f"{user_context[:800]}\n\n"
            )

        session_context_section = ""
        if session_context.get("formatted_context"):
            session_context_section = (
                f"THIS SESSION CONTEXT (summary + details + topics discussed):\n"
                f"{session_context['formatted_context']}\n\n"
            )

        prompt = (
            "You are a STRICT message router for a mental health chatbot.\n"
            "Your ONLY job: read the user's latest message and pick EXACTLY ONE route.\n"
            "Follow the DECISION TREE below from top to bottom. STOP at the FIRST match.\n"
            "SAFETY OVERRIDE: If the latest message contains self-harm, suicidal intent,\n"
            "or immediate danger, route = crisis even if the user also asks for a technique.\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "DECISION TREE — follow top to bottom, stop at first match\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "STEP 1 → accept_technique (HIGHEST NON-CRISIS PRIORITY — check after the safety override)\n"
            "  Does the user EXPLICITLY request/name a specific exercise, OR accept a technique the assistant already offered?\n"
            "  Two cases:\n"
            "    Case A: User names a specific exercise ('can i try box breathing', 'give me timeline journal')\n"
            "            → route = accept_technique, accepted_technique = exercise name from user\n"
            "    Case B: User explicitly asks for an exercise recommendation ('give me an exercise', 'what exercise should i try?')\n"
            "            → route = accept_technique, BUT you MUST also recommend ONE specific exercise\n"
            "            → REQUIRED: Populate accepted_technique with YOUR recommended exercise name\n"
            "            → Pick the BEST exercise for their current emotional state/needs\n"
            "            → Examples: if user is anxious → recommend 'Box Breathing'\n"
            "                        if user wants journaling → recommend 'Timeline Journal'\n"
            "                        if user is stressed → recommend '4-7-8 Breathing'\n\n"
            "  → YES to either case: route = accept_technique. STOP. Ignore mood, sadness, everything else.\n"
            "  Key signals: exercise name mentioned, 'can I try X', 'I want X',\n"
            "               'show me X', 'give me X exercise', 'yes' ONLY when AI just named a specific technique,\n"
            "               'recommend an exercise', 'what exercise should i try', 'give me something to try'.\n"
            "  Generic agreement after advice/reframing/exploring an idea is NOT accept_technique.\n\n"
            "  ✅ MUST be accept_technique:\n"
            "    'can i try timeline journal'                 → accept_technique (user chose it)\n"
            "    'i want breathing exercise'                  → accept_technique (user asked for it)\n"
            "    'show me box breathing'                      → accept_technique (explicit request)\n"
            "    'yes, timeline journal' [AI suggested it]   → accept_technique (user agreed)\n"
            "    'timeline journal please'                    → accept_technique\n"
            "    'give me breathing exercise'                 → accept_technique\n"
            "    'im sad but can i try timeline journal'      → accept_technique (exercise named overrides mood)\n"
            "    'ok let me try the body scan'                → accept_technique\n"
            "    'start the progressive muscle relaxation'    → accept_technique\n"
            "    'can you recommend an exercise?'             → accept_technique (YOU recommend ONE — MUST populate accepted_technique)\n"
            "    'i want to try an exercise'                  → accept_technique (YOU recommend ONE — MUST populate accepted_technique)\n"
            "    'give me something to help'                  → accept_technique (YOU recommend ONE — MUST populate accepted_technique)\n"
            "    'what exercise should i do?'                 → accept_technique (YOU recommend ONE — MUST populate accepted_technique)\n"
            "    'im not sad but just want an exercise to try' → accept_technique (YOU recommend ONE — MUST populate accepted_technique)\n"
            "    'give me an exercise'                        → accept_technique (YOU recommend ONE — MUST populate accepted_technique)\n\n"
            "  ❌ NOT accept_technique — these are FEEDBACK (route = therapeutic):\n"
            "  ★★★ CRITICAL RULE v9.0 ★★★ (STRICT — violating this breaks the pipeline)\n"
            "  After AI gave exercise steps or explained a technique:\n"
            "    'yes it is helping me'                       → MUST be therapeutic (positive feedback)\n"
            "    'yes it helped'                              → MUST be therapeutic (positive feedback)\n"
            "    'it is helping'                              → MUST be therapeutic (positive feedback)\n"
            "    'this is helping'                            → MUST be therapeutic (positive feedback)\n"
            "    'yes it's good'                              → MUST be therapeutic (positive feedback)\n"
            "    'yes its good'                               → MUST be therapeutic (positive feedback)\n"
            "    'yes that's good'                            → MUST be therapeutic (positive feedback)\n"
            "    'yes, that's good'                           → MUST be therapeutic (positive feedback)\n"
            "    'yeah it worked'                             → MUST be therapeutic (positive feedback)\n"
            "    'feeling a bit better'                       → MUST be therapeutic (improvement feedback)\n"
            "    'it helped a little'                         → MUST be therapeutic (partial positive)\n"
            "    'that was good'                              → MUST be therapeutic (positive feedback)\n"
            "    'i feel calmer now'                          → MUST be therapeutic (outcome feedback)\n"
            "    'yes that helped'                            → MUST be therapeutic (positive feedback)\n"
            "    'much better thank you'                      → MUST be therapeutic (positive outcome)\n"
            "    'ok that actually worked'                    → MUST be therapeutic (positive feedback)\n"
            "    'yes it's working'                           → MUST be therapeutic (positive feedback)\n"
            "    'feeling better'                             → MUST be therapeutic (positive feedback)\n\n"
            "    WHY: These ALL indicate the EXERCISE ALREADY WORKED. The user is not requesting a new exercise.\n"
            "    They are giving FEEDBACK on the exercise the AI ALREADY PROVIDED.\n"
            "    Misrouting to accept_technique causes the system to try fetching the same exercise again (pipeline error).\n"
            "    Route to therapeutic so the system can LOG this feedback as a positive outcome.\n\n"
            "  KEY DISTINCTION:\n"
            "    'yes' AFTER AI named a specific technique not yet given steps    → accept_technique (new request)\n"
            "    'yes' AFTER AI already gave the exercise steps                  → therapeutic (feedback)\n"
            "    'yes it helped' in ANY form, ANY timing                         → ALWAYS therapeutic (feedback)\n"
            "    'can i try X' or 'give me X' (NEW exercise name)              → ALWAYS accept_technique\n"
            "    'yes it's good' after AI provided steps                         → ALWAYS therapeutic (feedback)\n\n"
            "  Other NOT accept_technique cases:\n"
            "    'im sad' alone                               → therapeutic (no exercise mentioned, no recommendation requested)\n"
            "    'show me exercises' (general/plural)         → list_techniques (user wants to browse, not single recommendation)\n"
            "    'what exercises help anxiety?' (browsing)    → list_techniques or therapeutic (user exploring options, not requesting one)\n"
            "    'the exercise helped a little'               → therapeutic (positive feedback)\n"
            "    'yes i do' after AI said 'explore this idea' → therapeutic (not a named DB technique)\n"
            "    'yes' after AI offered a reframe/perspective → therapeutic (not a technique acceptance)\n\n"
            "  Metadata: accepted_technique = MUST BE POPULATED with exact exercise name from user OR your recommended exercise name.\n"
            "  CRITICAL: If user asks for a recommendation, you MUST choose ONE best-fit exercise and put its name here.\n"
            "  Do NOT leave accepted_technique as null for accept_technique route.\n"
            "  If no exact technique name exists AND user didn't ask for recommendation, do NOT use accept_technique.\n\n"
            "STEP 2 → crisis (OVERRIDES all non-technique routes)\n"
            "  Does the message contain self-harm, suicidal ideation, or immediate danger?\n"
            "  → YES: route = crisis. STOP.\n"
            "  Key signals: 'i want to die', 'kill myself', 'hurt myself', 'end it all',\n"
            "               'i have a plan', 'i already hurt myself tonight',\n"
            "               'everyone would be better off without me' + hopelessness.\n\n"
            "  IMPORTANT: Panic attacks are NEVER crisis. A panic attack is an acute anxiety\n"
            "  episode with physical symptoms (racing heart, can't breathe, shaking). It is\n"
            "  NOT suicidal ideation. Route panic attacks as therapeutic ALWAYS.\n\n"
            "  BINDING RULE: If you include 'panic_attack_reported' in context_flags, you MUST\n"
            "  set route = 'therapeutic'. Setting route = 'crisis' AND panic_attack_reported\n"
            "  simultaneously is a contradiction. Panic attacks are ALWAYS therapeutic.\n\n"
            "  ✅ MUST be crisis:\n"
            "    'i want to kill myself'                      → crisis\n"
            "    'i have pills ready'                         → crisis\n"
            "    'i dont want to be here anymore'             → crisis\n"
            "    'ive been cutting again'                     → crisis\n\n"
            "  ❌ NOT crisis (these are therapeutic):\n"
            "    'im having a panic attack'                   → therapeutic (acute anxiety, NOT suicidal ideation)\n"
            "    'i think im having a panic attack'           → therapeutic (physical anxiety symptoms)\n"
            "    'my heart is racing i cant breathe'          → therapeutic (panic/anxiety symptoms)\n"
            "    'im so tired of fighting every day'          → therapeutic (figurative language)\n"
            "    'i feel worthless'                           → therapeutic (cognitive distortion)\n"
            "    'i want to disappear from social media'      → therapeutic or chitchat\n"
            "    'i hate myself sometimes'                    → therapeutic (self-criticism)\n\n"

            "STEP 3 → list_techniques\n"
            "  IMPORTANT NEW RULE v9.0: This route is NOW for explicit list/browse requests ONLY.\n"
            "  Does the user explicitly ask for a LIST or BROWSE multiple exercises?\n"
            "  → YES: route = list_techniques. STOP. Metadata will include category list.\n"
            "  Key signals: 'list exercises', 'show me all techniques', 'what exercises do you have',\n"
            "               'show me all breathing techniques', 'browse exercises', 'what options?'\n\n"
            "  CRITICAL: If user says 'can you recommend an exercise?' or 'give me an exercise to try'\n"
            "  → This is STILL accept_technique with metadata.accepted_technique = null initially.\n"
            "  The AI will select ONE best-fit exercise and populate metadata.accepted_technique.\n"
            "  Do NOT route to list_techniques for single recommendations.\n\n"
            "  ❌ NOT list_techniques:\n"
            "    'can you recommend an exercise?'             → accept_technique (AI picks ONE)\n"
            "    'i want to try an exercise'                  → accept_technique (AI recommends ONE)\n"
            "    'give me something to help'                  → accept_technique (AI picks ONE)\n"
            "    'what exercise should i do?'                 → accept_technique (AI recommends ONE)\n\n"
            "  ✅ MUST be list_techniques:\n"
            "    'what exercises do you have?'                → list_techniques (user wants to browse)\n"
            "    'show me all breathing techniques'           → list_techniques (user wants options)\n"
            "    'list all the exercises'                     → list_techniques (user wants full list)\n"
            "    'what are my options?'                       → list_techniques (browsing)\n\n"
            "  Metadata: technique_category = the category they asked about (Breathing/Mindfulness/CBT/DBT/Journaling/Behavioral Activation) or null if general\n\n"

            "STEP 4 → chitchat\n"
            "  Is this casual/social with NO emotional distress and NO significant life event?\n"
            "  → YES: route = chitchat. STOP.\n"
            "  Key signals: greetings, thanks, bye, lol, jokes, name corrections, small talk.\n\n"
            "  ✅ MUST be chitchat:\n"
            "    'hey how are you'                            → chitchat\n"
            "    'thanks!'                                    → chitchat\n"
            "    'lol ok'                                     → chitchat\n"
            "    'im not sara im samira'                      → chitchat (name correction — ALWAYS chitchat)\n"
            "    'call me Ali not Ahmed'                      → chitchat (name correction — ALWAYS chitchat)\n"
            "    'good morning'                               → chitchat\n"
            "    'haha yeah'                                  → chitchat\n\n"
            "  ❌ NEVER chitchat — ALWAYS route to therapeutic:\n"
            "    'my friend was killed'                       → therapeutic (death/trauma — never chitchat)\n"
            "    'someone close to me passed away'            → therapeutic (grief — never chitchat)\n"
            "    'i was attacked / assaulted'                 → therapeutic (trauma — never chitchat)\n"
            "    ANY disclosure of death, loss, violence, abuse, or trauma → therapeutic, no exceptions\n"
            "    'im feeling a bit low today'                 → therapeutic\n"
            "    'that didnt really help me'                  → therapeutic (emotional weight)\n"
            "    'im ok i guess' (uncertain/hesitant)         → therapeutic\n\n"

            "STEP 5 → memory_query\n"
            "  Is the user asking about PAST sessions, their stored profile, or what was discussed before?\n"
            "  → YES: route = memory_query. STOP.\n"
            "  Key signals: 'do you remember me?', 'what did we talk about last time?',\n"
            "               'do you have my info?', 'what have we covered?', 'last session'\n\n"
            "  ✅ MUST be memory_query:\n"
            "    'do you remember what we discussed?'         → memory_query\n"
            "    'what did we talk about last time?'          → memory_query\n"
            "    'do you have my information?'                → memory_query\n"
            "    'what was the exercise we did before?'       → memory_query\n\n"

            "STEP 6 → rejection\n"
            "  Does the user EXPLICITLY reject ALL exercises or ALL help?\n"
            "  → YES: route = rejection. STOP.\n"
            "  Key signals: 'i dont want exercises', 'stop suggesting techniques',\n"
            "               'i dont want any help', 'leave me alone', 'no thanks'\n\n"
            "  ✅ MUST be rejection:\n"
            "    'i dont want to do any exercises'            → rejection\n"
            "    'please stop suggesting things'              → rejection\n"
            "    'i just want to vent, no exercises'          → rejection\n\n"
            "  ❌ NOT rejection:\n"
            "    'give me a DIFFERENT exercise'               → accept_technique (still wants exercises)\n"
            "    'that one didnt work'                        → therapeutic (feedback, not rejection)\n"
            "    'not that one, something else'               → accept_technique\n\n"

            "STEP 7 → therapeutic (DEFAULT — everything else)\n"
            "  User is experiencing emotional distress, venting, giving feedback, or needs support.\n"
            "  No specific exercise was named (if it was, use accept_technique).\n\n"
            "  ✅ MUST be therapeutic:\n"
            "    'i feel sad'                                 → therapeutic\n"
            "    'im struggling with anxiety'                 → therapeutic\n"
            "    'i need help'                                → therapeutic\n"
            "    'that exercise helped a little but im still anxious' → therapeutic (post-exercise feedback)\n"
            "    'i feel stuck in negative thinking'          → therapeutic\n"
            "    'im having a really hard day'                → therapeutic\n\n"
            "  ★★★ FEEDBACK RESPONSES (v9.0) ★★★\n"
            "  These indicate an exercise ALREADY WORKED. Log as positive feedback (NOT new exercise request):\n"
            "    'yes it is helping me' [AI gave exercise]    → therapeutic (positive feedback)\n"
            "    'yes it helped' [AI gave exercise]           → therapeutic (exercise worked feedback)\n"
            "    'yes it's good' [AI gave exercise steps]     → therapeutic (positive feedback)\n"
            "    'yes its good' [AI gave exercise steps]      → therapeutic (positive feedback)\n"
            "    'feeling better after that'                  → therapeutic (positive outcome feedback)\n"
            "    'that actually worked'                       → therapeutic (positive feedback)\n"
            "    'yes it's working'                           → therapeutic (positive feedback)\n"
            "    'feeling calmer now'                         → therapeutic (positive feedback)\n"
            "    'feeling a bit better'                       → therapeutic (positive feedback)\n\n"

            + user_bg_section
            + session_context_section

            + "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "EXERCISE CATEGORIES (for metadata only):\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  Breathing | Mindfulness | CBT | DBT | Journaling | Behavioral Activation\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "CONTEXT\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Recent conversation:\n{recent_context[-600:] if recent_context else 'None'}\n\n"
            f"User's latest message: \"{message}\"\n\n"

            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "OUTPUT FORMAT\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Respond ONLY with valid JSON — no explanation, no preamble, no extra text:\n"
            "{\n"
            "  \"route\": \"<accept_technique|chitchat|memory_query|list_techniques|rejection|crisis|therapeutic>\",\n"
            "  \"confidence\": <0.0-1.0>,\n"
            "  \"reasoning\": \"<one short sentence explaining why>\",\n"
            "  \"metadata\": {\n"
            "    \"accepted_technique\": \"<exact exercise name or null>\",\n"
            "    \"technique_category\": \"<Breathing|Mindfulness|CBT|DBT|Journaling|Behavioral Activation or null>\",\n"
            "    \"feedback_category\": \"<category if post-exercise feedback, or null>\",\n"
"    \"feedback_sentiment\": \"<helpful|partially_helpful|ineffective|not_suitable or null>\"\n"
"    \"feedback_type\": \"<positive|negative|neutral or null>  — set positive when user confirms exercise helped\"\n"            "  }\n"
            "}\n\n"
            "JSON:"
        )

        # v10.1: use the compact context-aware therapeutic gate prompt. The
        # older long prompt above is kept only as historical fallback text; this
        # assignment is what the LLM actually receives.
        prompt = _build_smart_gate_prompt(
            message=message,
            recent_context=recent_context,
            user_context=user_context,
            session_context=session_context,
        )

        # FIX v8.7: Was calling MODEL_LIGHT (8b) — 7-route classification needs MODEL_HEAVY (70b)
        print(f"[GATE v8.7] LLM-based priority routing starting ({MODEL_HEAVY})...")
        content = await _call_gemini_async(
            prompt,
            model=MODEL_HEAVY,
            temperature=0.0,
            max_tokens=1024,
        )

        if not content:
            logger.error(f"[GATE] LLM returned empty content")
            print("[GATE] ⚠️  Empty response from LLM")
            raise ValueError("LLM returned no content")

        parsed = _parse_json_from_llm(content)
        if not parsed:
            logger.error(f"[GATE] Failed to parse JSON from LLM response: {content[:200]}")
            print(f"[GATE] ⚠️  Invalid JSON from LLM")
            raise ValueError("Could not parse JSON from LLM response")

        if "route" not in parsed:
            logger.error(f"[GATE] Parsed JSON missing 'route' key: {parsed}")
            print(f"[GATE] ⚠️  Missing 'route' in LLM response")
            raise KeyError("LLM response missing 'route' key")

        normalized = _normalize_smart_gate_result(parsed, message, recent_context)
        
        
        route = normalized["route"]
        confidence = normalized["confidence"]
        reasoning = normalized["reasoning"]
        metadata = normalized["metadata"]
        flags = normalized["context_flags"]

        if (
            route in {"technique_follow_up", "technique_request"}
            and metadata.get("accepted_technique")
        ):
            accepted_tech = metadata["accepted_technique"]
            
            # Reject invalid values (boolean "true" from LLM, or string "true"/"false")
            # If accepted_technique is a boolean or string boolean, skip DB lookup
            # (technique should already be in state from prior semantic search selection)
            if isinstance(accepted_tech, bool) or (isinstance(accepted_tech, str) and accepted_tech.lower() in {"true", "false"}):
                print(f"[GATE] Skipping DB lookup for invalid accepted_technique: {accepted_tech} (type={type(accepted_tech).__name__})")
                metadata["accepted_technique"] = None
            elif isinstance(accepted_tech, str):
                # Valid string technique name — fetch full data from DB
                exercise_data = await _get_technique_from_db(accepted_tech.strip())
                if exercise_data:
                    metadata["exercise_data"] = exercise_data
                    print(f"[GATE] Exercise context loaded | name={exercise_data['name']} | category={exercise_data['category']}")
                else:
                    print(f"[GATE] Exercise not found in DB: {accepted_tech}")
        elif "list_techniques" in flags and metadata.get("technique_category"):
            category_exercises = await _get_techniques_by_category(metadata["technique_category"])
            if category_exercises:
                metadata["category_exercises"] = category_exercises
                print(f"[GATE] Category list context | category={metadata['technique_category']} | count={len(category_exercises)}")

        normalized["metadata"] = metadata
        print(
            f"[GATE] Route: {route.upper()} ({confidence:.0%}) | "
            f"Full pipeline: {'YES' if normalized['needs_full_pipeline'] else 'SKIP'} | "
            f"Mood skip: {'YES' if normalized['should_skip_mood_analysis'] else 'NO'} | "
            f"Flags: {flags} | Reason: {reasoning}"
        )
        return normalized

    except Exception as e:
        logger.error(f"[GATE] LLM routing FAILED with exception: {type(e).__name__}: {e}", exc_info=True)
        print(f"[GATE] ❌ Error - exception during routing: {e}")

    print("[GATE] ⚠️  Error - defaulting to therapeutic pipeline")
    return {
        "route": "therapeutic",
        "confidence": 0.0,
        "reasoning": "gate_error",
        "emotional_register": "concern",
        "context_flags": ["gate_error"],
        "intensity_hint": 0.45,
        "needs_full_pipeline": True,
        "should_skip_mood_analysis": False,
        "run_full_pipeline": True,
        "metadata": {},
    }


def _get_exercise_from_session_facts(session_context: dict, category: str) -> Optional[str]:
    """
    Extract exercise name from session facts by category.

    Session facts structure:
      [
        {"name": "Timeline Journal", "category": "Journaling", ...},
        {"name": "Box Breathing", "category": "Breathing", ...}
      ]

    Args:
      session_context: dict with 'facts' key containing exercise list
      category: Exercise category to match (e.g., "Journaling")

    Returns:
      Exercise name (str) or None if not found

    Example:
      _get_exercise_from_session_facts(ctx, "Journaling") -> "Timeline Journal"
    """
    try:
        facts = session_context.get("facts", [])
        if not facts:
            print(f"[GATE] No facts found in session context")
            return None

        for fact in facts:
            if isinstance(fact, dict) and fact.get("category") == category:
                exercise_name = fact.get("name")
                print(f"[GATE] Found exercise in facts: {exercise_name}")
                return exercise_name

        print(f"[GATE] No exercise found in facts for category: {category}")
        return None
    except Exception as e:
        logger.warning(f"[GATE] Could not extract exercise from session facts: {e}")
        return None
