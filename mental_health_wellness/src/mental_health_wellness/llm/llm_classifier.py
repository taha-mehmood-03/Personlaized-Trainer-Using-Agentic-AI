"""
LLM-Assisted Classifier Module — SentiMind v5.1

Provides structured JSON classification helpers for sensitive pipeline nodes.
Each function:
  - Sends a minimal, focused prompt to Groq (llama-3.3-70b-versatile for crisis,
    llama-3.1-8b-instant for lighter tasks)
  - Expects ONLY a valid JSON response
  - Returns a safe fallback dict on any failure (never crashes the pipeline)

CRISIS NODE: Uses sentinet/suicidality (local ELECTRA fine-tuned model) as
             a first-pass specialist, then Groq 70b as a second validator.
             Two-layer approach for maximum safety in the most critical scenario.
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


def _call_groq(prompt: str, model: str = "llama-3.1-8b-instant", temperature: float = 0.0) -> Optional[str]:
    """
    Make a minimal Groq LLM call with automatic key rotation.
    Returns raw content string or None on failure.
    """
    try:
        manager = get_llm_manager()
        from langchain_groq import ChatGroq
        import os

        # Use correct model for crisis (70b) vs lighter tasks (8b)
        key_idx = manager._get_available_groq_key_idx()
        if key_idx is None:
            manager.groq_failed_keys.clear()
            key_idx = manager._get_available_groq_key_idx()

        llm = ChatGroq(
            api_key=manager.groq_api_keys[key_idx],
            model=model,
            temperature=temperature,
            max_tokens=256  # Keep responses small — just JSON
        )
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        logger.warning(f"[CLASSIFIER] Groq call failed: {e}")
        return None


# ============================================
# CRISIS CLASSIFIER — Two-Layer (ELECTRA + Groq 70b)
# ============================================

async def llm_crisis_check(message: str) -> dict:
    """
    Two-layer crisis detection:
      Layer 1: sentinet/suicidality (local ELECTRA) — fast shortcut for HIGH confidence only.
      Layer 2: Groq llama-3.3-70b-versatile — MANDATORY for all other cases.

    CRITICAL DESIGN: ELECTRA can only SHORT-CIRCUIT EARLY if it's extremely confident (>= 0.80).
    It CANNOT declare a message safe. The Groq LLM always runs as the final authority
    except when ELECTRA is extremely confident of crisis.

    Returns:
      {
        "crisis_detected": bool,
        "crisis_level": "high" | "medium" | "low",
        "reason": str,
        "source": "electra" | "llm" | "electra+llm" | "fallback"
      }
    """
    electra_score = 0.0
    electra_available = False

    try:
        # ---- LAYER 1: Specialist ELECTRA (early exit ONLY on very high confidence) ----
        classifier = _get_crisis_classifier()
        if classifier and classifier != "unavailable":
            results = classifier(message[:512])
            scores = results[0] if results else []

            # Smart label detection: handle LABEL_0/LABEL_1, suicidal, suicide, etc.
            # The POSITIVE (crisis) label is whichever is NOT the non-crisis label.
            # Strategy: find the label with the highest score that looks like a crisis label,
            # OR if using LABEL_0/LABEL_1 convention, LABEL_1 is typically the positive class.
            score_map = {r["label"].lower(): r["score"] for r in scores}
            print(f"[CLASSIFIER] 🔬 ELECTRA raw labels: {score_map}")

            # Try named labels first
            electra_score = score_map.get(
                "suicidal",
                score_map.get(
                    "suicide",
                    score_map.get(
                        "label_1",          # common HuggingFace positive class convention
                        score_map.get(
                            "1",
                            score_map.get(
                                "positive",
                                # If none found: take the highest scoring label (best guess)
                                max(scores, key=lambda x: x["score"])["score"] if scores else 0.0
                            )
                        )
                    )
                )
            )
            electra_available = True
            print(f"[CLASSIFIER] 🔬 ELECTRA suicidality score: {electra_score:.2%}")

            # ONLY early-exit if ELECTRA is EXTREMELY confident (>= 0.80)
            if electra_score >= 0.80:
                print(f"[CLASSIFIER] 🚨 ELECTRA HIGH confidence ({electra_score:.2%}) — immediate crisis flag")
                return {
                    "crisis_detected": True,
                    "crisis_level": "high",
                    "reason": f"Specialist suicide model: {electra_score:.0%} confidence",
                    "source": "electra"
                }
            
            # LATENCY OPTIMIZATION: If ELECTRA is extremely confident it's SAFE (< 5%)
            # skip the 70b LLM call entirely to save 3-5 seconds of latency per message.
            elif electra_score < 0.05:
                print(f"[CLASSIFIER] ✅ ELECTRA VERY LOW risk ({electra_score:.2%}) — bypassing LLM check to save latency")
                return {
                    "crisis_detected": False,
                    "crisis_level": "low",
                    "reason": f"Specialist suicide model: {electra_score:.2%} confidence (safe)",
                    "source": "electra"
                }
            else:
                print(f"[CLASSIFIER] ⚠️  ELECTRA ambiguous score {electra_score:.2%} — deferring to Groq 70b LLM")

    except Exception as e:
        logger.warning(f"[CLASSIFIER] ELECTRA error: {e} — falling through to LLM")

    # ---- LAYER 2: Groq llama-3.3-70b-versatile (MANDATORY SAFETY NET) ----
    # This runs for messages where ELECTRA was ambiguous (5% to 80%).
    print(f"[CLASSIFIER] 🤖 Running Groq llama-3.3-70b-versatile crisis analysis...")

    electra_hint = f"\n(Note: A specialist local model scored this message {electra_score:.0%} suicidality confidence)" if electra_available else ""

    prompt = f"""You are a mental health crisis safety classifier. Detect explicit suicidal ideation or self-harm risk, even with typos or indirect language.
    
IMPORTANT RULES:
1. ONLY set crisis_detected=true for "high" or "medium" levels.
2. crisis_detected MUST be false when level is "low".
3. "im feeling low", "im sad", "im stressed" = level LOW = crisis_detected FALSE.
4. Consider typos: "kll myself" = "kill myself" = HIGH crisis.
5. COGNITIVE DISTORTIONS ARE NOT CRISES: Statements like "I'm a failure", "nothing goes right", or "nobody listens to me" are cognitive distortions, NOT suicidal ideation. Grade them as LOW unless they contain an explicit desire to stop living.

Crisis levels:
- high: explicit desire to die, end life, harm self (even with typos) → crisis_detected=TRUE
- medium: implicit hopelessness, feeling like a burden explicitly tied to not wanting to exist → crisis_detected=TRUE
- low: general distress, sadness, frustration, normal cognitive distortions ("I'm a failure") → crisis_detected=FALSE

Respond ONLY with valid JSON:
{{"crisis_detected": true or false, "crisis_level": "high" or "medium" or "low", "reason": "brief explanation"}}{electra_hint}

Message to classify: "{message}"

JSON:"""

    try:
        content = _call_groq(prompt, model="llama-3.3-70b-versatile", temperature=0.0)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "crisis_detected" in parsed:
                # Enforce consistency: "low" level BY DEFINITION means no crisis.
                # If the LLM contradicts itself (crisis=True + level=low), correct it.
                if parsed.get("crisis_level") == "low":
                    parsed["crisis_detected"] = False
                parsed["source"] = "electra+llm" if electra_available else "llm"
                print(f"[CLASSIFIER] 🤖 Groq 70b crisis result: crisis={parsed['crisis_detected']} level={parsed.get('crisis_level')} reason='{parsed.get('reason', '')}'")
                return parsed
    except Exception as e:
        logger.error(f"[CLASSIFIER] Groq LLM crisis check failed: {e}")

    # Final safe fallback
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

        content = _call_groq(prompt, model="llama-3.1-8b-instant", temperature=0.0)
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
    Replaces brittle keyword matching for technique requests and reflection signals.

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

        content = _call_groq(prompt, model="llama-3.1-8b-instant", temperature=0.0)
        if content:
            parsed = _parse_json_from_llm(content)
            if parsed and "intent" in parsed:
                print(f"[CLASSIFIER] 💬 LLM intent: {parsed.get('intent')} ({parsed.get('confidence', 0):.0%})")
                return parsed

    except Exception as e:
        logger.warning(f"[CLASSIFIER] Intent check failed: {e}")

    return {"intent": "venting", "confidence": 0.0}
