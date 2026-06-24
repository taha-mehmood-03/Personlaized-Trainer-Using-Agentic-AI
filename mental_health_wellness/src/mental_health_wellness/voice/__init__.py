"""
Gemini-based voice helpers.

The voice path does not load any local speech-emotion or acoustic models.
Voice preprocessing uses Gemini only for transcription. Rich voice/emotion
features are extracted later, and only for therapeutic routes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
from typing import Any

from dotenv import load_dotenv

from ..techniques.emotion_metadata import (
    BEHAVIOR_TAGS,
    CANONICAL_SUB_EMOTIONS,
    PROJECT_STUDY_CONTEXTS,
    SUB_EMOTION_TO_CORE,
    SYMPTOM_TAGS,
)
from .acoustic_features import extract_acoustic_features

load_dotenv()

_logger = logging.getLogger("sentimind.voice")


CORE_EMOTIONS = {
    "anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise", "anxiety"
}
SENTIMENTS = {"positive", "negative", "neutral"}
_NEGATIVE = {"anger", "disgust", "fear", "sadness", "anxiety"}
_POSITIVE = {"joy", "surprise"}
_CORE_ORDER = ("anger", "disgust", "fear", "joy", "neutral", "sadness", "surprise", "anxiety")
_CORE_SUB_FALLBACK = {
    "anger": "frustration",
    "disgust": "resentment",
    "fear": "future_threat",
    "joy": "joy",
    "neutral": "neutral",
    "sadness": "sadness",
    "surprise": "neutral",
    "anxiety": "anxiety",
}
CONTEXT_TAGS = {
    "general_settling", "nervous_system_regulation", "sleep_onset",
    "bedtime_wind_down", "acute_worry", "acute_pressure",
    "presentation_anxiety", "pre_presentation", "pre_performance",
    "social_re_engagement", "connection_practice", "task_starting",
    "low_energy_activation", "emotion_regulation", "self_compassion",
    "relationship_repair", "practical_problem_solving", "specific_negative_thought",
    "belief_challenge", "avoidance_breaking", "thought_unloading",
    "emotional_reflection", "meaning_and_values", "routine_rebuilding",
    "social_humiliation", "school_conflict", "teacher_conflict",
    "authority_conflict", "interpersonal_conflict",
    *PROJECT_STUDY_CONTEXTS,
}


_VOICE_BASE_PROMPT = """\
You are analyzing the VOCAL DELIVERY of an audio recording for a mental-health support system.

YOUR MOST IMPORTANT INSTRUCTION:
Classify based on HOW the person sounds, not what their words mean.
If what the voice sounds like CONTRADICTS what the words mean, classify based on the VOICE.

You will receive:
1. CONVERSATION HISTORY - the last few turns of this support session, when available
2. AUDIO - the user's voice message to classify now

VOICE-FIRST ANALYSIS:
Listen specifically for these vocal signals BEFORE reading the words:
  - Pitch: Is it elevated (emotional activation) or flat (depression)?
  - Tremor: Is the voice shaking or unstable (crying, anxiety)?
  - Breathiness: Is there crying breathiness or sighing present?
  - Pauses: More silence than normal speech (hesitancy, avoidance)?
  - Energy: Does the vocal energy match the words being said?
  - Strain: Is the voice tight, constricted, or breaking?

COMMON MASKING PATTERNS YOU MUST DETECT:
  - Crying/trembling voice + positive words ("I'm fine", "I'm happy")
    -> classify as sadness/distress, set voice_text_conflict=true
  - Laughing/light tone + sad words ("I'm so sad", "I want to die")
    -> classify as joy/amusement, set voice_text_conflict=true
  - Flat/exhausted delivery + excited words ("I'm doing great!")
    -> classify as fatigue/low_mood, set voice_text_conflict=true
  - Trembling/breaking voice + calm words ("everything is okay")
    -> classify as anxiety/distress, set voice_text_conflict=true

IMPORTANT: The audio may be a short follow-up reply (e.g. "mostly around my family").
Use the conversation history to understand the full emotional picture before classifying.
Do not diagnose. Only infer emotional state from the available evidence.

Return a JSON object with EXACTLY these fields:

{
  "transcription": <verbatim transcript of the audio, or empty string if unintelligible>,
  "emotion": <one of: anger|disgust|fear|joy|neutral|sadness|surprise|anxiety — based on VOICE tone, NOT word meaning>,
  "primary_sub_emotion": <one canonical sub-emotion from the allowed taxonomy>,
  "secondary_sub_emotions": [<up to 3 additional canonical sub-emotions>],
  "sentiment": <one of: positive|negative|neutral — based on VOICE tone>,
  "intensity": <float 0.0-1.0 reflecting overall distress level across the conversation>,
  "confidence": <float 0.0-1.0, your confidence in this classification>,
  "arousal": <float 0.0-1.0, vocal activation/energy: 0=very calm, 1=highly activated>,
  "valence": <float 0.0-1.0, emotional positivity of the VOICE: 0=very negative, 1=very positive>,
  "distress_index": <float 0.0-1.0, clinical composite vocal distress: 0=low, 1=high — based on vocal strain, NOT word content>,
  "pause_density": <float 0.0-1.0, hesitancy/silence proportion: 0=fluent, 1=very hesitant>,
  "voice_text_conflict": <true if vocal delivery contradicts word meaning, false otherwise>,
  "conflict_description": <describe the conflict if voice_text_conflict is true, else null>,
  "detected_symptoms": [<physical/cognitive signals from the allowed taxonomy>],
  "detected_behaviors": [<behavioral patterns from the allowed taxonomy>],
  "detected_contexts": [<situational contexts from the allowed taxonomy>],
  "emotion_scores": {"anger": 0.0, "disgust": 0.0, "fear": 0.0, "joy": 0.0, "neutral": 0.0, "sadness": 0.0, "surprise": 0.0, "anxiety": 0.0},
  "reasoning": <one sentence explaining your classification — when voice and words conflict, explain WHY you chose the voice signal>
}

Rules:
- emotion MUST be one of the 8 core emotions exactly as listed.
- CRITICAL: emotion must reflect the VOICE, not the words. A crying voice saying "I'm happy" = sadness.
- primary_sub_emotion MUST be exactly one value from ALLOWED PRIMARY/SUB-EMOTIONS.
- Prefer the most specific sub-emotion supported by evidence (for example performance_anxiety,
  rejection, shame, burnout, bedtime_rumination) instead of a generic label when possible.
- secondary_sub_emotions MUST contain only allowed sub-emotions, no duplicates, and no
  repeat of primary_sub_emotion.
- detected_symptoms, detected_behaviors, and detected_contexts MUST contain only allowed
  labels from the taxonomy below.
- Do not invent symptoms, behaviors, or contexts. Include them only when clearly supported
  by transcript, conversation history, or vocal delivery.
- distress_index MUST reflect vocal strain signals (tremor, breathiness, pitch instability,
  pauses). Do NOT lower distress_index just because the words sound positive.
- intensity for neutral/joy must be <= 0.45. For negative emotions usually use 0.50-0.95.
- If the user is masking distress with positive language OR a calm tone, detect the underlying emotion.
- If words and tone disagree, ALWAYS choose the voice signal and set voice_text_conflict=true.
- Respond ONLY with valid JSON. No markdown, no explanation outside the JSON.
"""


_TRANSCRIPTION_PROMPT = """\
You are a speech-to-text transcription system.

Transcribe the user's audio verbatim. Do not analyze emotion, tone, distress,
intent, symptoms, or acoustic features.

Return a JSON object with EXACTLY this field:
{
  "transcription": <verbatim transcript of the audio, or empty string if unintelligible>
}

Respond ONLY with valid JSON. No markdown, no explanation outside the JSON.
"""


def _format_allowed_values(values: set[str] | frozenset[str], per_line: int = 8) -> str:
    labels = sorted(str(item).strip() for item in values if str(item).strip())
    rows = []
    for index in range(0, len(labels), per_line):
        rows.append("  - " + ", ".join(labels[index:index + per_line]))
    return "\n".join(rows)


def _allowed_taxonomy_block() -> str:
    return "\n".join([
        "ALLOWED PRIMARY/SUB-EMOTIONS:",
        _format_allowed_values(CANONICAL_SUB_EMOTIONS),
        "",
        "ALLOWED SYMPTOMS:",
        _format_allowed_values(SYMPTOM_TAGS),
        "",
        "ALLOWED BEHAVIORS:",
        _format_allowed_values(BEHAVIOR_TAGS),
        "",
        "ALLOWED CONTEXTS:",
        _format_allowed_values(CONTEXT_TAGS),
        "",
    ])


def _build_voice_prompt(conversation_context: str = "") -> str:
    """Build the voice analysis prompt, optionally injecting conversation history.

    Mirrors the context injection in mood_tools._gemini_analyze_mood:
      - If context exists: prepend it as CONVERSATION HISTORY before the audio
      - The base prompt already instructs Gemini to use it for follow-up clips
    """
    prompt = _VOICE_BASE_PROMPT + "\n" + _allowed_taxonomy_block()
    if conversation_context and conversation_context.strip():
        return (
            prompt
            + "\nCONVERSATION HISTORY (last few turns - use this to classify short "
            "or follow-up audio correctly):\n"
            + conversation_context.strip()
            + "\n"
        )
    return prompt


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


def _clean_json_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return match.group(0) if match else text


def _normalize_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _fallback_sub_for_emotion(emotion: str) -> str:
    fallback = _CORE_SUB_FALLBACK.get(emotion, "neutral")
    return fallback if fallback in CANONICAL_SUB_EMOTIONS else emotion


def _core_for_sub_emotion(sub_emotion: str) -> str | None:
    mapped = SUB_EMOTION_TO_CORE.get(sub_emotion)
    if not mapped:
        return None
    core = str(mapped).strip().lower()
    return core if core in CORE_EMOTIONS else None


def _safe_primary_sub_emotion(value: Any, emotion: str) -> str:
    label = _normalize_label(value)
    if label in CANONICAL_SUB_EMOTIONS:
        return label
    return _fallback_sub_for_emotion(emotion)


def _safe_secondary_sub_emotions(value: Any, primary: str, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []

    results: list[str] = []
    seen = {primary}
    for item in value:
        label = _normalize_label(item)
        if label not in CANONICAL_SUB_EMOTIONS or label in seen:
            continue
        seen.add(label)
        results.append(label)
        if len(results) >= limit:
            break
    return results


def _safe_list(value: Any, allowed: set[str] | frozenset[str], limit: int = 4) -> list[str]:
    if not isinstance(value, list):
        return []

    results: list[str] = []
    seen: set[str] = set()
    for item in value:
        label = _normalize_label(item)
        if label not in allowed or label in seen:
            continue
        seen.add(label)
        results.append(label)
        if len(results) >= limit:
            break
    return results


def _mime_type_for_path(audio_path: str, audio_bytes: bytes) -> str:
    guessed, _ = mimetypes.guess_type(audio_path)
    if guessed and guessed.startswith("audio/"):
        return guessed
    if audio_bytes[:4] == b"RIFF":
        return "audio/wav"
    if audio_bytes[:4] == b"OggS":
        return "audio/ogg"
    if audio_bytes[:3] == b"ID3" or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xfa"):
        return "audio/mpeg"
    if b"\x1a\x45\xdf\xa3" in audio_bytes[:100]:
        return "audio/webm"
    if len(audio_bytes) > 12 and audio_bytes[4:8] == b"ftyp":
        return "audio/mp4"
    return "audio/wav"


def _neutral_result(reason: str = "fallback neutral") -> dict[str, Any]:
    return {
        "acoustic_features": {
            "pitch_mean": 0.0,
            "pitch_std": 0.0,
            "loudness_mean": 0.0,
            "jitter": 0.0,
            "shimmer": 0.0,
            "hnr": 0.0,
            "speech_rate": 0.0,
            "spectral_flux": 0.0,
        },
        "emotion": "neutral",
        "confidence": 0.0,
        "arousal": 0.5,
        "valence": 0.5,
        "distress_index": 0.0,
        "pause_density": 0.25,
        "mfcc_vector": [0.0] * 13,
        "all_scores": {"neutral": 1.0},
        "emotion_scores": {"neutral": 1.0},
        "primary_sub_emotion": "neutral",
        "secondary_sub_emotions": [],
        "detected_symptoms": [],
        "detected_behaviors": [],
        "detected_contexts": [],
        "sentiment": "neutral",
        "intensity": 0.5,
        "emotion_reasoning": reason,
        "extraction_method": "gemini_audio_fallback",
        "transcription": "",
    }


def _validate_gemini_voice(parsed: dict[str, Any]) -> dict[str, Any]:
    emotion = _normalize_label(parsed.get("emotion", "neutral"))
    if emotion not in CORE_EMOTIONS:
        emotion = "neutral"

    primary_sub = _safe_primary_sub_emotion(parsed.get("primary_sub_emotion", emotion), emotion)
    mapped_core = _core_for_sub_emotion(primary_sub)
    if mapped_core == "neutral" and emotion in _NEGATIVE:
        primary_sub = _fallback_sub_for_emotion(emotion)
        mapped_core = _core_for_sub_emotion(primary_sub)
    if mapped_core and mapped_core != emotion:
        emotion = mapped_core

    sentiment = _normalize_label(parsed.get("sentiment", ""))
    derived_sentiment = (
        "negative" if emotion in _NEGATIVE
        else "positive" if emotion in _POSITIVE
        else "neutral"
    )
    if (
        sentiment not in SENTIMENTS
        or (emotion in _NEGATIVE and sentiment != "negative")
        or (emotion in _POSITIVE and sentiment == "negative")
        or (emotion == "neutral" and sentiment not in {"neutral", "positive"})
    ):
        sentiment = derived_sentiment

    confidence = _clamp(parsed.get("confidence", 0.0), 0.0)
    intensity = _clamp(parsed.get("intensity", 0.5), 0.5)
    if emotion in {"neutral", "joy"}:
        intensity = min(intensity, 0.45)

    arousal = _clamp(parsed.get("arousal", intensity), intensity)
    valence = _clamp(parsed.get("valence", 0.5), 0.5)
    if emotion in _NEGATIVE:
        valence = min(valence, 0.45)
    elif emotion in _POSITIVE:
        valence = max(valence, 0.55)

    distress_default = intensity if emotion in _NEGATIVE else min(intensity, 0.35)
    distress_index = _clamp(parsed.get("distress_index", distress_default), distress_default)
    if emotion in {"neutral", "joy"}:
        distress_index = min(distress_index, 0.45)
    pause_density = _clamp(parsed.get("pause_density", 0.25), 0.25)

    secondary = _safe_secondary_sub_emotions(
        parsed.get("secondary_sub_emotions"),
        primary=primary_sub,
    )

    raw_scores = parsed.get("emotion_scores") or {}
    emotion_scores = {name: _clamp(raw_scores.get(name, 0.0), 0.0) for name in _CORE_ORDER}
    if not any(emotion_scores.values()):
        emotion_scores[emotion] = confidence or 0.75
    else:
        emotion_scores[emotion] = max(emotion_scores.get(emotion, 0.0), confidence or 0.0)

    detected_symptoms = _safe_list(parsed.get("detected_symptoms"), SYMPTOM_TAGS)
    detected_behaviors = _safe_list(parsed.get("detected_behaviors"), BEHAVIOR_TAGS)
    detected_contexts = _safe_list(parsed.get("detected_contexts"), CONTEXT_TAGS)

    return {
        "acoustic_features": {
            "pitch_mean": 0.0,
            "pitch_std": 0.0,
            "loudness_mean": 0.0,
            "jitter": 0.0,
            "shimmer": 0.0,
            "hnr": 0.0,
            "speech_rate": 0.0,
            "spectral_flux": 0.0,
        },
        "emotion": emotion,
        "confidence": round(confidence, 3),
        "arousal": round(arousal, 3),
        "valence": round(valence, 3),
        "distress_index": round(distress_index, 3),
        "pause_density": round(pause_density, 3),
        "mfcc_vector": [0.0] * 13,
        "all_scores": emotion_scores,
        "emotion_scores": emotion_scores,
        "primary_sub_emotion": primary_sub,
        "secondary_sub_emotions": secondary,
        "detected_symptoms": detected_symptoms,
        "detected_behaviors": detected_behaviors,
        "detected_contexts": detected_contexts,
        "sentiment": sentiment,
        "intensity": round(intensity, 3),
        "voice_text_conflict": bool(parsed.get("voice_text_conflict", False)),
        "conflict_description": str(parsed.get("conflict_description") or "") or None,
        "emotion_reasoning": f"Gemini audio: {str(parsed.get('reasoning', ''))[:160]}",
        "extraction_method": "gemini_audio",
        "transcription": str(parsed.get("transcription", "") or "").strip(),
    }


def _merge_dsp_features(result: dict[str, Any], dsp: dict[str, Any]) -> dict[str, Any]:
    """Merge real (librosa + parselmouth) acoustic measurements into Gemini's
    semantic/holistic voice result.

    Only `acoustic_features`, `mfcc_vector`, `pause_density`, and the new
    `acoustic_distress_proxy` are touched -- Gemini's own `arousal`,
    `valence`, and `distress_index` judgments are intentionally left as-is.
    See voice/acoustic_features.py module docstring for the rationale.
    """
    merged = dict(result)
    if dsp.get("extraction_method") == "dsp":
        merged["acoustic_features"] = dsp["acoustic_features"]
        merged["mfcc_vector"] = dsp["mfcc_vector"]
        if dsp.get("pause_density") is not None:
            merged["pause_density"] = dsp["pause_density"]
        merged["acoustic_distress_proxy"] = dsp.get("acoustic_distress_proxy")
        merged["dsp_extraction_method"] = "dsp"
        _logger.info(
            "Voice DSP merged | gemini_distress=%.2f acoustic_distress_proxy=%s "
            "gemini_pause=%.2f real_pause=%s",
            merged.get("distress_index", 0.0),
            dsp.get("acoustic_distress_proxy"),
            result.get("pause_density", 0.0),
            dsp.get("pause_density"),
        )
    else:
        merged["acoustic_distress_proxy"] = None
        merged["dsp_extraction_method"] = dsp.get("extraction_method", "dsp_failed")
        if dsp.get("error"):
            _logger.info("Voice DSP extraction unavailable (%s) -- using Gemini-only fields", dsp["error"])
    return merged


def _gemini_config():
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=1200,
        response_mime_type="application/json",
    )


def _gemini_transcription_config():
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=0.0,
        max_output_tokens=300,
        response_mime_type="application/json",
    )


def _gemini_contents(audio_path: str, conversation_context: str = "") -> tuple[list[Any], str]:
    from google.genai import types

    with open(audio_path, "rb") as file:
        audio_bytes = file.read()
    mime_type = _mime_type_for_path(audio_path, audio_bytes)
    prompt = _build_voice_prompt(conversation_context)
    contents = [
        types.Part.from_text(text=prompt),
        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
    ]
    return contents, mime_type


def _gemini_transcription_contents(audio_path: str) -> tuple[list[Any], str]:
    from google.genai import types

    with open(audio_path, "rb") as file:
        audio_bytes = file.read()
    mime_type = _mime_type_for_path(audio_path, audio_bytes)
    contents = [
        types.Part.from_text(text=_TRANSCRIPTION_PROMPT),
        types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
    ]
    return contents, mime_type


def _model_and_keys() -> tuple[str, list[str]]:
    from ..llm.groq_llm import get_llm_manager

    manager = get_llm_manager()
    model = getattr(manager, "model_mood", None) or "gemini-3.1-flash-lite"
    keys = list(getattr(manager, "gemini_keys", []) or [])
    if not keys:
        for env_name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
            key = os.getenv(env_name)
            if key and key not in keys:
                keys.append(key)
    return model, keys


def analyze_voice_full(audio_path: str, conversation_context: str = "") -> dict[str, Any]:
    """
    Analyze uploaded speech audio with Gemini.

    Gemini handles transcription, core emotion, sub-emotions, and vocal cue
    estimation in one multimodal call.

    Args:
        audio_path: Absolute path to the audio file.
        conversation_context: Optional recent conversation history string
            (e.g. last 6 turns). Injected into the prompt so Gemini can
            correctly classify short or follow-up audio clips in context.
    """
    try:
        from google import genai

        if not audio_path or not os.path.exists(audio_path):
            return _neutral_result("audio file missing")

        contents, mime_type = _gemini_contents(audio_path, conversation_context)
        model, keys = _model_and_keys()
        if not keys:
            return _neutral_result("GEMINI_API_KEY not configured")

        has_context = bool(conversation_context and conversation_context.strip())
        last_error: Exception | None = None
        for key in keys:
            try:
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=_gemini_config(),
                )
                raw_text = getattr(response, "text", "") or str(response)
                parsed = json.loads(_clean_json_text(raw_text))
                result = _validate_gemini_voice(parsed)
                try:
                    dsp = extract_acoustic_features(audio_path)
                except Exception as dsp_exc:
                    dsp = {"extraction_method": "dsp_failed", "error": str(dsp_exc)[:160]}
                result = _merge_dsp_features(result, dsp)
                print(
                    "[VOICE] Gemini audio complete | "
                    f"model={model} mime={mime_type} emotion={result['emotion']} "
                    f"sub={result['primary_sub_emotion']} conf={result['confidence']:.0%} "
                    f"ctx={'yes' if has_context else 'none'} dsp={result['dsp_extraction_method']}"
                )
                return result
            except Exception as exc:
                last_error = exc
                print(f"[VOICE] Gemini audio call failed: {str(exc)[:120]}")

        return _neutral_result(f"Gemini audio failed: {str(last_error)[:120] if last_error else 'unknown'}")
    except Exception as exc:
        print(f"[VOICE] Gemini audio analysis failed: {str(exc)[:120]}")
        return _neutral_result(f"Gemini audio exception: {str(exc)[:120]}")


def transcribe_voice(audio_path: str) -> dict[str, Any]:
    """
    Transcribe uploaded speech audio with Gemini without emotion analysis.
    """
    try:
        from google import genai

        if not audio_path or not os.path.exists(audio_path):
            return {
                "transcription": "",
                "extraction_method": "gemini_audio_transcription_fallback",
                "error": "audio file missing",
            }

        contents, mime_type = _gemini_transcription_contents(audio_path)
        model, keys = _model_and_keys()
        if not keys:
            return {
                "transcription": "",
                "extraction_method": "gemini_audio_transcription_fallback",
                "error": "GEMINI_API_KEY not configured",
            }

        last_error: Exception | None = None
        for key in keys:
            try:
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=_gemini_transcription_config(),
                )
                raw_text = getattr(response, "text", "") or str(response)
                parsed = json.loads(_clean_json_text(raw_text))
                transcription = str(parsed.get("transcription", "") or "").strip()
                print(
                    "[VOICE] Gemini transcription complete | "
                    f"model={model} mime={mime_type} chars={len(transcription)}"
                )
                return {
                    "transcription": transcription,
                    "extraction_method": "gemini_audio_transcription",
                }
            except Exception as exc:
                last_error = exc
                print(f"[VOICE] Gemini transcription call failed: {str(exc)[:120]}")

        return {
            "transcription": "",
            "extraction_method": "gemini_audio_transcription_fallback",
            "error": f"Gemini transcription failed: {str(last_error)[:120] if last_error else 'unknown'}",
        }
    except Exception as exc:
        print(f"[VOICE] Gemini transcription failed: {str(exc)[:120]}")
        return {
            "transcription": "",
            "extraction_method": "gemini_audio_transcription_fallback",
            "error": f"Gemini transcription exception: {str(exc)[:120]}",
        }


async def analyze_voice_full_async(audio_path: str, conversation_context: str = "") -> dict[str, Any]:
    """
    Async Gemini audio analysis for FastAPI request paths.

    Args:
        audio_path: Absolute path to the audio file.
        conversation_context: Optional recent conversation history string
            (e.g. last 6 turns). Injected into the prompt so Gemini can
            correctly classify short or follow-up audio clips in context.
    """
    try:
        from google import genai

        if not audio_path or not os.path.exists(audio_path):
            return _neutral_result("audio file missing")

        contents, mime_type = _gemini_contents(audio_path, conversation_context)
        model, keys = _model_and_keys()
        if not keys:
            return _neutral_result("GEMINI_API_KEY not configured")

        has_context = bool(conversation_context and conversation_context.strip())
        last_error: Exception | None = None
        for key in keys:
            try:
                client = genai.Client(api_key=key)
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=_gemini_config(),
                )
                raw_text = getattr(response, "text", "") or str(response)
                parsed = json.loads(_clean_json_text(raw_text))
                result = _validate_gemini_voice(parsed)
                try:
                    # CPU-bound DSP work -- run off the event loop so a slow
                    # extraction never blocks other concurrent requests.
                    dsp = await asyncio.to_thread(extract_acoustic_features, audio_path)
                except Exception as dsp_exc:
                    dsp = {"extraction_method": "dsp_failed", "error": str(dsp_exc)[:160]}
                result = _merge_dsp_features(result, dsp)
                print(
                    "[VOICE] Gemini audio complete | "
                    f"model={model} mime={mime_type} emotion={result['emotion']} "
                    f"sub={result['primary_sub_emotion']} conf={result['confidence']:.0%} "
                    f"ctx={'yes' if has_context else 'none'} dsp={result['dsp_extraction_method']}"
                )
                return result
            except Exception as exc:
                last_error = exc
                print(f"[VOICE] Gemini audio async call failed: {str(exc)[:120]}")

        return _neutral_result(f"Gemini audio failed: {str(last_error)[:120] if last_error else 'unknown'}")
    except Exception as exc:
        print(f"[VOICE] Gemini audio async analysis failed: {str(exc)[:120]}")
        return _neutral_result(f"Gemini audio exception: {str(exc)[:120]}")


async def transcribe_voice_async(audio_path: str) -> dict[str, Any]:
    """
    Async Gemini transcription for FastAPI request paths.
    """
    try:
        from google import genai

        if not audio_path or not os.path.exists(audio_path):
            return {
                "transcription": "",
                "extraction_method": "gemini_audio_transcription_fallback",
                "error": "audio file missing",
            }

        contents, mime_type = _gemini_transcription_contents(audio_path)
        model, keys = _model_and_keys()
        if not keys:
            return {
                "transcription": "",
                "extraction_method": "gemini_audio_transcription_fallback",
                "error": "GEMINI_API_KEY not configured",
            }

        last_error: Exception | None = None
        for key in keys:
            try:
                client = genai.Client(api_key=key)
                response = await client.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=_gemini_transcription_config(),
                )
                raw_text = getattr(response, "text", "") or str(response)
                parsed = json.loads(_clean_json_text(raw_text))
                transcription = str(parsed.get("transcription", "") or "").strip()
                print(
                    "[VOICE] Gemini transcription complete | "
                    f"model={model} mime={mime_type} chars={len(transcription)}"
                )
                return {
                    "transcription": transcription,
                    "extraction_method": "gemini_audio_transcription",
                }
            except Exception as exc:
                last_error = exc
                print(f"[VOICE] Gemini transcription async call failed: {str(exc)[:120]}")

        return {
            "transcription": "",
            "extraction_method": "gemini_audio_transcription_fallback",
            "error": f"Gemini transcription failed: {str(last_error)[:120] if last_error else 'unknown'}",
        }
    except Exception as exc:
        print(f"[VOICE] Gemini transcription async failed: {str(exc)[:120]}")
        return {
            "transcription": "",
            "extraction_method": "gemini_audio_transcription_fallback",
            "error": f"Gemini transcription exception: {str(exc)[:120]}",
        }


def preload_all_voice_models() -> dict[str, Any]:
    """
    Eagerly import and warm up DSP libraries (librosa + parselmouth/Praat) so
    the first voice request does not pay a cold-import penalty (~2-5s on Windows).
    Called by organized_lifespan at server startup.
    """
    model, keys = _model_and_keys()
    status: dict[str, Any] = {
        "provider": "gemini_audio",
        "model": model,
        "gemini_key_set": bool(keys),
        "librosa": "not_loaded",
        "parselmouth": "not_loaded",
    }

    # Warm up librosa — triggers scipy/numba/audioread imports and numba JIT
    try:
        import numpy as np
        import librosa
        _dummy = np.zeros(1600, dtype=np.float32)
        librosa.feature.mfcc(y=_dummy, sr=16000, n_mfcc=13)
        status["librosa"] = "ready"
        print("[VOICE] librosa warm-up complete")
    except Exception as exc:
        status["librosa"] = f"unavailable: {str(exc)[:80]}"
        print(f"[VOICE] librosa warm-up failed (non-fatal): {exc}")

    # Warm up parselmouth — triggers native Praat library initialisation
    try:
        import numpy as np
        import parselmouth
        parselmouth.Sound(np.zeros(160, dtype=np.float64), sampling_frequency=16000)
        status["parselmouth"] = "ready"
        print("[VOICE] parselmouth/Praat warm-up complete")
    except Exception as exc:
        status["parselmouth"] = f"unavailable: {str(exc)[:80]}"
        print(f"[VOICE] parselmouth warm-up failed (non-fatal): {exc}")

    print(f"[VOICE] Gemini voice analysis ready | model={model} key_set={bool(keys)}")
    return status


def fuse_emotions(text_emotion: dict, voice_emotion: dict, alpha: float = 0.6) -> dict:
    """
    Backward-compatible helper for callers that still ask the voice module to
    fuse two already-computed emotion dicts.
    """
    text_emo = text_emotion.get("emotion", "neutral")
    text_conf = float(text_emotion.get("confidence", 0.5))
    voice_emo = voice_emotion.get("emotion", "neutral")
    voice_conf = float(voice_emotion.get("confidence", 0.0))

    if voice_conf < 0.3:
        return {
            "emotion": text_emo,
            "confidence": text_conf,
            "source": "text",
            "conflict": False,
            "text_emotion": text_emo,
            "voice_emotion": voice_emo,
        }
    if text_emo == voice_emo:
        return {
            "emotion": text_emo,
            "confidence": round(min(0.95, text_conf * 0.7 + voice_conf * 0.3 + 0.1), 3),
            "source": "agreement",
            "conflict": False,
            "text_emotion": text_emo,
            "voice_emotion": voice_emo,
        }

    text_weighted = text_conf * alpha
    voice_weighted = voice_conf * (1 - alpha)
    final_emotion = text_emo if text_weighted >= voice_weighted else voice_emo
    final_conf = text_conf * 0.8 if final_emotion == text_emo else voice_conf * 0.8
    return {
        "emotion": final_emotion,
        "confidence": round(final_conf, 3),
        "source": "text" if final_emotion == text_emo else "voice",
        "conflict": True,
        "text_emotion": text_emo,
        "voice_emotion": voice_emo,
    }
