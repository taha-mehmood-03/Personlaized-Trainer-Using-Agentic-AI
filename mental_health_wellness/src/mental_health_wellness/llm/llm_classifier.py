"""
LLM-Assisted Classifier Module  SentiMind v8.7 FIXED

Provides structured JSON classification helpers for sensitive pipeline nodes.
Each function:
  - Sends a minimal, focused prompt to OpenRouter using the single working model:
    meta-llama/llama-3.3-70b-instruct
  - Expects ONLY a valid JSON response
  - Returns a safe fallback dict on any failure (never crashes the pipeline)

CRISIS NODE: OpenRouter meta-llama/llama-3.3-70b-instruct is the SOLE authoritative decision maker.
             Local ELECTRA model disabled  LLM-only path active.

GATE NODE: OpenRouter meta-llama/llama-3.3-70b-instruct (FIXED from 8b - 7-route classification needs 70b power)

v8.7 FIXES vs v6.1:
  - smart_pipeline_gate  : uses llama-3.3-70b-instruct for stable routing
  - llm_crisis_check     : FIXED model mismatch - prompt said 70b but code called 8b (safety-critical bug)
  - Gate prompt          : Fully rewritten with numbered steps, expanded examples, ambiguous edge cases covered
  - Crisis prompt        : Sharpened 3-step dimensional reasoning, added more non-crisis examples
  - Distortion prompt    : Added concrete examples for every distortion type
  - Intent prompt        : Unchanged (was already solid)
  - All prompts          : temperature=0.0 enforced everywhere, JSON-only output enforced
  - LLM_PROVIDER=openrouter: All calls routed through OpenRouter.
  - Local ELECTRA (sentinet/suicidality) model DISABLED (commented out).
"""

import json
import re
import os
import logging
from typing import Optional

from .groq_llm import get_llm_manager

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  MODEL CONSTANTS  change once here, applies everywhere below
# ─────────────────────────────────────────────────────────────
MODEL_HEAVY = os.getenv("SENTIMIND_LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")
MODEL_CRISIS = MODEL_HEAVY
MODEL_LIGHT = MODEL_HEAVY


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
# LLM_PROVIDER=openrouter: OpenRouter LLM is now the sole decision maker.
# The local sentinet/suicidality model is commented out for performance.
# ============================================

_crisis_classifier = None  # Always returns "unavailable" (local model disabled)


def _get_crisis_classifier():
    """
    Local ELECTRA crisis classifier  DISABLED.
    Returns 'unavailable' immediately so llm_crisis_check falls through
    to the LLM-only path (OpenRouter llama-3.3-70b-instruct).
    """
    global _crisis_classifier
    if _crisis_classifier is not None:
        return _crisis_classifier

    #  LOCAL MODEL DISABLED 
    # The sentinet/suicidality ELECTRA model is commented out.
    # OpenRouter Llama 3.3 70B handles crisis detection as sole authoritative decision maker.
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
    print(f"[CLASSIFIER]   Crisis detection: OpenRouter {MODEL_CRISIS} ")
    print("[CLASSIFIER] ")
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


async def _call_groq_async(prompt: str, model: str = MODEL_LIGHT, temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """
    Make an ASYNC OpenRouter LLM call via the unified LLM manager.
    Returns raw content string or None on failure.

    v8.7: All LLM classification calls use MODEL_HEAVY (llama-3.3-70b-instruct).
    """
    try:
        manager = get_llm_manager()
        llm = manager.get_llm(model=model)
        call_llm = llm.bind(max_tokens=max_tokens, temperature=temperature)
        print(f"[CLASSIFIER]   Calling OpenRouter | model={model} | max_tokens={max_tokens}")
        response = await call_llm.ainvoke(prompt)  # NON-BLOCKING  event loop free
        print(f"[CLASSIFIER]   Response received  | model={model}")
        return response.content
    except Exception as e:
        logger.warning(f"[CLASSIFIER]  OpenRouter call FAILED | model={model} | error: {e}")
        return None


# Keep sync alias for any legacy callers (wraps async in thread executor)
def _call_groq(prompt: str, model: str = MODEL_LIGHT, temperature: float = 0.0, max_tokens: int = 128) -> Optional[str]:
    """Legacy sync wrapper  prefer _call_groq_async in async contexts."""
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
# CRISIS CLASSIFIER  OpenRouter Llama 3.3 70B (sole decision maker)
# ============================================

async def llm_crisis_check(message: str) -> dict:
    """
    Semantic crisis detection  OpenRouter llama-3.3-70b-instruct as the authoritative decision maker.

    ARCHITECTURE (v8.7  LLM-Only, Fully Async):
      Step 1: Keyword gate handled upstream (graph.py screen_for_crisis Layer 1).
      Step 2: llama-3.3-70b-instruct runs async (await ainvoke)  best empathy + clinical reasoning.
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
    # ELECTRA disabled  OpenRouter Llama 3.3 70B is the sole decision maker

    # ---- CRISIS ANALYSIS: OpenRouter Llama 3.3 70B ----
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
        content = await _call_groq_async(prompt, model=MODEL_HEAVY, temperature=0.0, max_tokens=150)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "crisis_detected" in parsed:
                if parsed.get("crisis_level") == "low":
                    parsed["crisis_detected"] = False
                parsed["source"] = "llm"
                crisis_icon = "🚨" if parsed["crisis_detected"] else "✅"
                print(f"[CLASSIFIER] {crisis_icon} CRISIS RESULT  detected={parsed['crisis_detected']}  level={parsed.get('crisis_level','?').upper()}  reason='{parsed.get('reason', '')}'")
                return parsed
    except Exception as e:
        logger.error(f"[CLASSIFIER]  Crisis LLM call FAILED: {e}")

    print("[CLASSIFIER]   ALL classifiers failed  returning safe non-crisis fallback")
    return {
        "crisis_detected": False,
        "crisis_level": "low",
        "reason": "All classifiers failed  defaulting to safe non-crisis",
        "source": "fallback"
    }


# ============================================
# COGNITIVE DISTORTION CLASSIFIER  Groq 8b
# Stays on MODEL_LIGHT  lightweight pattern matching, not safety-critical
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
        content = await _call_groq_async(prompt, model=MODEL_HEAVY, temperature=0.0, max_tokens=100)
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
1. Score ONLY items with conversational evidence. No evidence = 0.
2. If a symptom is clearly present but frequency/duration is unclear, score 1.
3. Use score 2 or 3 ONLY when the user states frequency/duration or wording strongly implies persistence.
4. Overall severity = MAX(PHQ-9 severity, GAD-7 severity) for THIS TURN'S evidence only.
5. List indicators for items scoring >= 2.
6. If Q9 >= 2 then flag suicidal_ideation regardless of total.
7. Do not inflate totals to match emotional intensity. Prefer conservative scoring.
4. If Q9 >= 2 → flag suicidal_ideation regardless of total.

━━━ CONTEXT ━━━
Detected emotion: {emotion} at {intensity:.0%} intensity
Emotional trend: {emotional_trend}
Recent conversation:
{recent_context}
Current message: "{message}"

━━━ OUTPUT — JSON ONLY ━━━
{{"severity":"minimal|mild|moderate|moderately_severe|severe","phq9_scores":{{"q1":0,"q2":0,"q3":0,"q4":0,"q5":0,"q6":0,"q7":0,"q8":0,"q9":0}},"gad7_scores":{{"g1":0,"g2":0,"g3":0,"g4":0,"g5":0,"g6":0,"g7":0}},"phq9_total":0,"gad7_total":0,"clinical_indicators":[],"confidence":0.0,"reasoning":"one sentence justification"}}

JSON:"""

        print(f"[CLASSIFIER] 🏥 CLINICAL SEVERITY CHECK → {MODEL_HEAVY}")
        content = await _call_groq_async(prompt, model=MODEL_HEAVY, temperature=0.0, max_tokens=300)
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
# CONVERSATION INTENT CLASSIFIER  Groq 8b
# Stays on MODEL_LIGHT  downstream from gate, lightweight classification
# ============================================

async def llm_intent_check(message: str, recent_context: str = "") -> dict:
    """
    LLM-assisted intent classification for the conversation planner.
    v5.3: Now truly async via _call_groq_async.

    Returns:
      {
        "intent": "technique_request" | "advice_seeking" | "reflection" | "venting" | "chitchat" | "crisis_signal",
        "confidence": float
      }
    """
    try:
        prompt = f"""You are a precise intent classifier for a mental health companion app. Classify the USER's LATEST message only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Choose EXACTLY ONE intent from this list:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  technique_request | advice_seeking | reflection | venting | chitchat | crisis_signal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFINITIONS — be strict, read each carefully:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY DISAMBIGUATION RULE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If the Previous Conversation Context shows the AI recently suggested a technique/exercise,
AND the user now says it didn't help OR asks to try something else → classify as technique_request.

IMPORTANT: Name/identity corrections are ALWAYS chitchat regardless of how frustrated the wording sounds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLES — read context carefully:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"I'm so stressed about my exams"                                           → venting
"It didn't help me" [previous AI had NO technique]                         → venting
"It didn't help me" [previous AI HAD suggested a technique]                → technique_request
"That exercise didn't work, show me another one"                           → technique_request
"Still feeling the same after trying it" [prev AI had technique]           → technique_request
"What should I do to feel better?" [no specific exercise asked]            → advice_seeking
"I am having difficulty expressing myself, what should I do?"              → advice_seeking
"Can you give me a breathing exercise?"                                    → technique_request
"That didn't help, can I try a different exercise?"                        → technique_request
"Maybe my anxiety comes from my childhood"                                 → reflection
"I realize I get anxious when I'm around my family"                        → reflection
"Hey, how's it going?"                                                     → chitchat
"im not taram im taha mehmood"                                             → chitchat (name correction)
"my name is not sara its samira"                                           → chitchat (name correction)
"call me Ali not Ahmed"                                                    → chitchat (name correction)
"I don't want to exist anymore"                                            → crisis_signal

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
        content = await _call_groq_async(prompt, model=MODEL_HEAVY, temperature=0.0, max_tokens=64)
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
# FIX v8.7: Upgraded from MODEL_LIGHT (8b) to MODEL_HEAVY (70b)
# 7-route priority classification is too complex for 8b  was causing misrouting
# ============================================================

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
            "  Does the user EXPLICITLY name/request a specific stored exercise, OR give a short yes/okay\n"
            "  immediately after the assistant named one specific exercise/technique from the database?\n"
            "  → YES: route = accept_technique. STOP. Ignore mood, sadness, everything else.\n"
            "  Key signals: exercise name mentioned, 'can I try X', 'I want X',\n"
            "               'show me X', 'give me X exercise', 'yes' ONLY when AI just named a specific technique.\n"
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
            "    'start the progressive muscle relaxation'    → accept_technique\n\n"
            "  ❌ NOT accept_technique:\n"
            "    'im sad' alone                               → therapeutic (no exercise mentioned)\n"
            "    'show me exercises' (general/plural)         → list_techniques\n"
            "    'what exercises help anxiety?' (browsing)    → list_techniques or therapeutic\n"
            "    'the exercise helped a little'               → therapeutic (feedback, not request)\n"
            "    'yes i do' after AI said 'explore this idea' → therapeutic (not a named DB technique)\n"
            "    'yes' after AI offered a reframe/perspective → therapeutic (not a technique acceptance)\n\n"
            "  Metadata: accepted_technique = exact exercise name from user OR exact technique name from AI's last message.\n"
            "  If no exact technique name exists, do NOT use accept_technique.\n\n"
            "STEP 2 → crisis (OVERRIDES all non-technique routes)\n"
            "  Does the message contain self-harm, suicidal ideation, or immediate danger?\n"
            "  → YES: route = crisis. STOP.\n"
            "  Key signals: 'i want to die', 'kill myself', 'hurt myself', 'end it all',\n"
            "               'i have a plan', 'i already hurt myself tonight',\n"
            "               'everyone would be better off without me' + hopelessness.\n\n"
            "  ✅ MUST be crisis:\n"
            "    'i want to kill myself'                      → crisis\n"
            "    'i have pills ready'                         → crisis\n"
            "    'i dont want to be here anymore'             → crisis\n"
            "    'ive been cutting again'                     → crisis\n\n"
            "  ❌ NOT crisis (these are therapeutic):\n"
            "    'im so tired of fighting every day'          → therapeutic (figurative language)\n"
            "    'i feel worthless'                           → therapeutic (cognitive distortion)\n"
            "    'i want to disappear from social media'      → therapeutic or chitchat\n"
            "    'i hate myself sometimes'                    → therapeutic (self-criticism)\n\n"

            "STEP 3 → list_techniques\n"
            "  Does the user want a LIST of multiple exercises (NOT one specific)?\n"
            "  → YES: route = list_techniques. STOP.\n"
            "  Key signals: 'list exercises', 'show me all techniques',\n"
            "               'what exercises do you have', 'show me breathing techniques',\n"
            "               'what can help me?', 'what options do I have?'\n"
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
            "    \"feedback_sentiment\": \"<ineffective|partially_helpful|not_suitable or null>\"\n"
            "  }\n"
            "}\n\n"
            "JSON:"
        )

        # FIX v8.7: Was calling MODEL_LIGHT (8b) — 7-route classification needs MODEL_HEAVY (70b)
        print(f"[GATE v8.7] LLM-based priority routing starting ({MODEL_HEAVY})...")
        content = await _call_groq_async(
            prompt,
            model=MODEL_HEAVY,
            temperature=0.0,
            max_tokens=250,
        )

        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "route" in parsed:
                route      = parsed.get("route", "therapeutic")
                confidence = parsed.get("confidence", 0.5)
                reasoning  = parsed.get("reasoning", "")
                metadata   = parsed.get("metadata") or {}
                valid_routes = {
                    "accept_technique", "chitchat", "memory_query",
                    "list_techniques", "rejection", "crisis", "therapeutic",
                }
                if route not in valid_routes:
                    print(f"[GATE] Invalid route '{route}' from LLM; defaulting to therapeutic")
                    route = "therapeutic"

                try:
                    confidence = float(confidence)
                except Exception:
                    confidence = 0.5
                confidence = max(0.0, min(1.0, confidence))

                if route == "accept_technique" and not metadata.get("accepted_technique"):
                    print("[GATE] accept_technique missing exact technique name; downgrading to therapeutic")
                    route = "therapeutic"

                # NEW v8.7: Fetch DB data based on route (BEFORE therapeutic analysis)
                if route == "accept_technique" and metadata.get("accepted_technique"):
                    # User explicitly chose exercise -> fetch from DB
                    exercise_data = await _get_technique_from_db(metadata["accepted_technique"])
                    if exercise_data:
                        metadata["exercise_data"] = exercise_data
                        print(f"[GATE] ✅ Exercise accepted | name={exercise_data['name']} | category={exercise_data['category']}")
                    else:
                        print(f"[GATE] ⚠️  Exercise not found in DB: {metadata['accepted_technique']}")

                elif route == "list_techniques" and metadata.get("technique_category"):
                    # User wants exercise list -> fetch all from category
                    category_exercises = await _get_techniques_by_category(metadata["technique_category"])
                    if category_exercises:
                        metadata["category_exercises"] = category_exercises
                        print(f"[GATE] 📋 Category list | category={metadata['technique_category']} | count={len(category_exercises)}")

                # Determine if full pipeline should run
                run_full_pipeline = route in ("therapeutic", "crisis")

                print(f"[GATE] Route: {route.upper()} ({confidence:.0%}) | Pipeline: {'YES' if run_full_pipeline else 'SKIP'} | Reason: {reasoning}")

                return {
                    "route":             route,
                    "confidence":        confidence,
                    "reasoning":         reasoning,
                    "run_full_pipeline": run_full_pipeline,
                    "metadata":          metadata,
                }

    except Exception as e:
        logger.warning(f"[GATE] LLM routing failed: {e}")

    print("[GATE] Error - defaulting to therapeutic pipeline")
    return {
        "route":             "therapeutic",
        "confidence":        0.0,
        "reasoning":         "gate_error",
        "run_full_pipeline": True,
        "metadata":          {},
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
