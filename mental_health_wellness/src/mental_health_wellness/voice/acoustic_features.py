"""
Real (non-LLM) acoustic / paralinguistic feature extraction.

WHY THIS MODULE EXISTS:
Gemini's audio understanding is genuinely multimodal (it receives raw audio
bytes), but a generative LLM has no mechanism to *measure* signal-processing
quantities such as fundamental frequency (F0), jitter, shimmer, harmonics-to-
noise ratio (HNR), or MFCCs. When the voice pipeline asked Gemini to report
those as JSON numbers, it could only ever be an unverifiable guess -- and the
"compatibility" fields (`mfcc_vector`, `acoustic_features`) were in fact never
computed at all; they were hardcoded zero placeholders everywhere in
voice/__init__.py.

This module computes the real thing, deterministically, from the waveform:
  - librosa            -> MFCCs, RMS energy/loudness, spectral flux, a
                           real (not estimated) silence/pause ratio.
  - praat-parselmouth   -> pitch (F0) mean/std, jitter, shimmer, HNR -- the
                           field-standard correlates of vocal strain/tension
                           used throughout affective-computing research
                           (this is the same family of measures eGeMAPS/
                           openSMILE compute; parselmouth wraps Praat itself,
                           the reference implementation these formulas come
                           from).

DESIGN DECISION (intentional, not an oversight):
This module does NOT overwrite Gemini's holistic `arousal` / `valence` /
`distress_index` judgment -- those benefit from semantic understanding of
the words plus a qualitative tonal impression that pure DSP cannot capture
(e.g. calmly-stated crisis language vs. a merely tense-sounding voice).
Instead it:
  1. Populates `acoustic_features` and `mfcc_vector` with real measured
     values (previously always-zero placeholders).
  2. Replaces the previously LLM-guessed `pause_density` with a real,
     deterministic silence-ratio measurement on the same 0-1 scale, so
     existing threshold logic (`pause_density > 0.40` in
     emotion_fusion_node.py) keeps working without re-tuning.
  3. Adds a new, clearly-labelled `acoustic_distress_proxy` field: a
     transparent composite of jitter/shimmer/pitch-variability/HNR, useful
     as a cross-check against Gemini's self-reported distress_index (and a
     good signal to log/evaluate for an FYP results chapter).

All extraction is wrapped defensively: any failure (corrupt audio, an
unreadable container format, parselmouth/praat errors on very short or
silent clips) degrades to safe zeroed values and never raises -- consistent
with the rest of the voice pipeline's error-handling philosophy.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger("sentimind.voice.acoustic")

_MFCC_DIM = 13

# Typical literature ranges used to normalise raw measurements into 0-1
# proxies. These are intentionally generous (not diagnostic thresholds) --
# they only need to order strain to compute the composite proxy.
_JITTER_NORMAL_MAX = 0.020   # local jitter > ~2% is considered elevated
_SHIMMER_NORMAL_MAX = 0.150  # local shimmer > ~15% is considered elevated
_PITCH_CV_MAX = 0.50         # pitch std / pitch mean (coefficient of variation)
_HNR_GOOD = 20.0             # dB; healthy/relaxed voicing is usually >= ~20dB


def _clamp01(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize(value: float, hi: float) -> float:
    if hi <= 0:
        return 0.0
    return _clamp01(value / hi)


def _empty_acoustic_features() -> dict[str, float]:
    return {
        "pitch_mean": 0.0,
        "pitch_std": 0.0,
        "loudness_mean": 0.0,
        "jitter": 0.0,
        "shimmer": 0.0,
        "hnr": 0.0,
        "speech_rate": 0.0,
        "spectral_flux": 0.0,
    }


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "acoustic_features": _empty_acoustic_features(),
        "mfcc_vector": [0.0] * _MFCC_DIM,
        "pause_density": None,
        "acoustic_distress_proxy": None,
        "extraction_method": "dsp_failed",
        "error": reason,
    }


def _extract_pitch_jitter_shimmer_hnr(audio_path: str) -> dict[str, float]:
    """Real F0/jitter/shimmer/HNR via Praat (parselmouth). Returns zeros on failure."""
    import parselmouth
    from parselmouth.praat import call as praat_call

    out = {"pitch_mean": 0.0, "pitch_std": 0.0, "jitter": 0.0, "shimmer": 0.0, "hnr": 0.0}

    sound = parselmouth.Sound(audio_path)

    try:
        pitch = sound.to_pitch()
        freqs = pitch.selected_array["frequency"]
        voiced = freqs[freqs > 0]
        if voiced.size:
            out["pitch_mean"] = float(np.mean(voiced))
            out["pitch_std"] = float(np.std(voiced))
    except Exception as exc:
        logger.debug("pitch extraction failed: %s", exc)

    try:
        # Praat defaults for periodic point-process + jitter/shimmer (75-500Hz
        # pitch floor/ceiling, 0.0001-0.02s period range, 1.3 max period factor,
        # 1.6 max amplitude factor) -- the standard parameters used in Praat's
        # own jitter/shimmer scripts and replicated across speech-emotion papers.
        point_process = praat_call(sound, "To PointProcess (periodic, cc)", 75, 500)
        out["jitter"] = float(
            praat_call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        )
        out["shimmer"] = float(
            praat_call(
                [sound, point_process],
                "Get shimmer (local)",
                0, 0, 0.0001, 0.02, 1.3, 1.6,
            )
        )
    except Exception as exc:
        # Common on very short, silent, or unvoiced clips -- not fatal.
        logger.debug("jitter/shimmer extraction failed: %s", exc)

    try:
        harmonicity = sound.to_harmonicity()
        hnr_mean = praat_call(harmonicity, "Get mean", 0, 0)
        out["hnr"] = float(hnr_mean) if hnr_mean == hnr_mean else 0.0  # filter NaN
    except Exception as exc:
        logger.debug("HNR extraction failed: %s", exc)

    return out


def _extract_librosa_features(audio_path: str) -> dict[str, Any]:
    """Real MFCC/RMS/spectral-flux/pause-ratio via librosa. Returns zeros on failure."""
    import librosa

    result = {
        "loudness_mean": 0.0,
        "spectral_flux": 0.0,
        "speech_rate": 0.0,
        "mfcc_vector": [0.0] * _MFCC_DIM,
        "pause_density": None,
    }

    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    duration_s = float(len(y) / sr) if sr else 0.0
    if y.size == 0 or duration_s <= 0:
        return result

    # MFCCs (mean across time) -- the real 13-dim vector other code referred
    # to as `mfcc_vector` but never actually computed.
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=_MFCC_DIM)
        result["mfcc_vector"] = [float(v) for v in np.mean(mfcc, axis=1)]
    except Exception as exc:
        logger.debug("MFCC extraction failed: %s", exc)

    # Loudness proxy: mean RMS energy.
    try:
        rms = librosa.feature.rms(y=y)[0]
        result["loudness_mean"] = float(np.mean(rms))
    except Exception as exc:
        logger.debug("RMS extraction failed: %s", exc)

    # Spectral flux: frame-to-frame spectral magnitude change (timbral/energy
    # volatility -- elevated in strained or agitated speech).
    try:
        stft_mag = np.abs(librosa.stft(y))
        flux = np.sqrt(np.sum(np.diff(stft_mag, axis=1) ** 2, axis=0))
        result["spectral_flux"] = float(np.mean(flux)) if flux.size else 0.0
    except Exception as exc:
        logger.debug("spectral flux extraction failed: %s", exc)

    # Real pause/silence ratio via energy-based voice activity detection
    # (librosa.effects.split), replacing what used to be an LLM guess.
    try:
        non_silent_intervals = librosa.effects.split(y, top_db=35)
        voiced_samples = sum(end - start for start, end in non_silent_intervals)
        pause_density = 1.0 - (voiced_samples / len(y))
        result["pause_density"] = round(_clamp01(pause_density), 3)

        # Speech-rate proxy: voiced-segment count per second. Not a true
        # syllable-nuclei rate (that needs a dedicated algorithm), but a
        # deterministic, reproducible measure of speech choppiness/pacing.
        if duration_s > 0:
            result["speech_rate"] = round(len(non_silent_intervals) / duration_s, 3)
    except Exception as exc:
        logger.debug("pause/speech-rate extraction failed: %s", exc)

    return result


def _acoustic_distress_proxy(features: dict[str, float]) -> float:
    """Transparent composite strain score from jitter/shimmer/pitch-variability/HNR.

    This is NOT a clinical distress score -- it is a deterministic acoustic
    strain/tension proxy, useful as a cross-check against Gemini's holistic
    distress_index (and for logging/evaluation), not a replacement for it.
    """
    pitch_mean = features.get("pitch_mean", 0.0)
    pitch_std = features.get("pitch_std", 0.0)
    pitch_cv = (pitch_std / pitch_mean) if pitch_mean > 0 else 0.0

    jitter_n = _normalize(features.get("jitter", 0.0), _JITTER_NORMAL_MAX)
    shimmer_n = _normalize(features.get("shimmer", 0.0), _SHIMMER_NORMAL_MAX)
    pitch_var_n = _normalize(pitch_cv, _PITCH_CV_MAX)
    hnr_strain_n = _normalize(max(0.0, _HNR_GOOD - features.get("hnr", _HNR_GOOD)), _HNR_GOOD)

    composite = 0.30 * jitter_n + 0.30 * shimmer_n + 0.20 * pitch_var_n + 0.20 * hnr_strain_n
    return round(_clamp01(composite), 3)


def extract_acoustic_features(audio_path: str) -> dict[str, Any]:
    """Compute real acoustic/paralinguistic features from a waveform file.

    Synchronous and CPU-bound (typically well under ~300ms for short voice
    clips). Callers on the async request path should run this via
    `asyncio.to_thread` / an executor rather than awaiting it directly, so it
    does not block the event loop.

    Returns a dict with:
        acoustic_features:        dict (pitch_mean, pitch_std, loudness_mean,
                                   jitter, shimmer, hnr, speech_rate,
                                   spectral_flux) -- all real measurements.
        mfcc_vector:               list[float], real 13-dim MFCC mean vector.
        pause_density:             float 0-1, real energy-based silence ratio,
                                    or None if extraction failed (caller should
                                    fall back to the LLM-estimated value).
        acoustic_distress_proxy:   float 0-1, deterministic strain composite,
                                    or None if extraction failed.
        extraction_method:         "dsp" on success, "dsp_failed" on failure.
    """
    import os

    if not audio_path or not os.path.exists(audio_path):
        return _empty_result("audio file missing")

    try:
        praat_part = _extract_pitch_jitter_shimmer_hnr(audio_path)
    except Exception as exc:
        logger.warning("Praat/parselmouth extraction failed entirely: %s", str(exc)[:160])
        praat_part = {"pitch_mean": 0.0, "pitch_std": 0.0, "jitter": 0.0, "shimmer": 0.0, "hnr": 0.0}

    try:
        librosa_part = _extract_librosa_features(audio_path)
    except Exception as exc:
        logger.warning("librosa extraction failed entirely: %s", str(exc)[:160])
        librosa_part = {
            "loudness_mean": 0.0, "spectral_flux": 0.0, "speech_rate": 0.0,
            "mfcc_vector": [0.0] * _MFCC_DIM, "pause_density": None,
        }

    if not any(value for value in {**praat_part, **librosa_part}.values() if isinstance(value, (int, float))):
        # Both backends produced nothing usable (e.g. silent/corrupt clip).
        return _empty_result("no usable signal extracted")

    acoustic_features = {
        "pitch_mean": round(praat_part.get("pitch_mean", 0.0), 3),
        "pitch_std": round(praat_part.get("pitch_std", 0.0), 3),
        "loudness_mean": round(librosa_part.get("loudness_mean", 0.0), 5),
        "jitter": round(praat_part.get("jitter", 0.0), 5),
        "shimmer": round(praat_part.get("shimmer", 0.0), 5),
        "hnr": round(praat_part.get("hnr", 0.0), 3),
        "speech_rate": round(librosa_part.get("speech_rate", 0.0), 3),
        "spectral_flux": round(librosa_part.get("spectral_flux", 0.0), 5),
    }

    result = {
        "acoustic_features": acoustic_features,
        "mfcc_vector": librosa_part.get("mfcc_vector", [0.0] * _MFCC_DIM),
        "pause_density": librosa_part.get("pause_density"),
        "acoustic_distress_proxy": _acoustic_distress_proxy(acoustic_features),
        "extraction_method": "dsp",
    }
    logger.info(
        "DSP acoustic extraction complete | pitch=%.1fHz(+-%.1f) jitter=%.4f shimmer=%.4f "
        "hnr=%.1fdB pause_density=%s distress_proxy=%.2f",
        acoustic_features["pitch_mean"], acoustic_features["pitch_std"],
        acoustic_features["jitter"], acoustic_features["shimmer"],
        acoustic_features["hnr"], result["pause_density"], result["acoustic_distress_proxy"],
    )
    return result
