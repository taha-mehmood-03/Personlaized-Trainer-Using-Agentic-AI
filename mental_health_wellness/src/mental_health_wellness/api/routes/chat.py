"""Chat endpoints: text, streaming, pipeline, and voice."""

import json
import os
import tempfile
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from src.mental_health_wellness.agent import chat_with_agent
from src.mental_health_wellness.agent.graph import chat_with_agent_streaming
from src.mental_health_wellness.api.helpers import (
    _emotion_payload_from_result,
    latency_seconds,
)
from src.mental_health_wellness.api.models import ChatRequest, ChatResponse, PipelineRequest
from src.mental_health_wellness.security.compliance import enforce_user_scope, pseudonymize_user_id, redact_text
from src.mental_health_wellness.services.cache_state import invalidate_user_cache
from src.mental_health_wellness.api.rate_limit import limiter

import logging

logger = logging.getLogger("sentimind.server")

router = APIRouter()


# ── Audio helpers ─────────────────────────────────────────────────────────────

def _detect_audio_format(audio_bytes: bytes) -> str:
    if len(audio_bytes) < 4:
        return "wav"
    if audio_bytes[:4] == b"RIFF":
        return "wav"
    elif audio_bytes[:4] in (b"\xff\xfb", b"\xff\xfa"):
        return "mp3"
    elif audio_bytes[4:8] == b"ftyp":
        return "mp4"
    elif audio_bytes[:4] == b"OggS":
        return "ogg"
    elif b"\x1a\x45\xdf\xa3" in audio_bytes[:100]:
        return "webm"
    return "webm"


def _audio_upload_suffix(audio_data: str | None, audio_bytes: bytes) -> str:
    header = ""
    if audio_data and "," in audio_data:
        header = audio_data.split(",", 1)[0].lower()
    if "audio/wav" in header or "audio/x-wav" in header:
        return ".wav"
    if "audio/webm" in header:
        return ".webm"
    if "audio/ogg" in header:
        return ".ogg"
    if "audio/mpeg" in header or "audio/mp3" in header:
        return ".mp3"
    if "audio/mp4" in header or "audio/m4a" in header:
        return ".mp4"
    return f".{_detect_audio_format(audio_bytes)}"


def _save_audio_b64(audio_data: str) -> str | None:
    """Decode a base64 audio_data field to a temp file. Returns path or None."""
    import base64
    try:
        b64_str = audio_data
        if "," in b64_str:
            b64_str = b64_str.split(",")[1]
        audio_bytes = base64.b64decode(b64_str)
        suffix = _audio_upload_suffix(audio_data, audio_bytes)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(audio_bytes)
            return tf.name
    except Exception as e:
        print(f"[CHAT] Failed to decode audio_data: {e}")
        return None


async def _preprocess_voice(
    audio_temp_path: str,
    message: str,
    *,
    label: str,
    prior_messages: list | None = None,
) -> tuple[str, Optional[dict]]:
    """Run Gemini voice preprocessing. Returns (final_message, voice_features_or_None)."""
    from src.mental_health_wellness.pipeline.voice_preprocessing import preprocess_voice_input

    voice_result = await preprocess_voice_input({
        "audio_file_path": audio_temp_path,
        "message": message,
        "messages": prior_messages or [],
    })
    transcription = voice_result.get("transcription", "").strip()
    final_message = transcription or voice_result.get("final_message", message) or message

    vf_candidate = voice_result.get("voice_features")
    is_authoritative = (
        isinstance(vf_candidate, dict)
        and str(vf_candidate.get("extraction_method", "")).lower().strip() == "gemini_audio"
    )
    prefetched = vf_candidate if is_authoritative else None
    if prefetched:
        vf = prefetched
        print(
            f"[{label}] Voice features forwarded: emotion={vf.get('emotion')} "
            f"intensity={vf.get('intensity', 0.5):.0%}"
        )
    return final_message, prefetched


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    """Main chat endpoint using the deterministic graph pipeline."""
    request_start = time.time()
    safe_user = pseudonymize_user_id(request.user_id)
    enforce_user_scope(http_request, request.user_id)
    logger.info(
        "Latency CHAT | start | user=%s session=%s audio=%s",
        safe_user,
        redact_text(request.session_id or "new", max_len=32),
        bool(request.audio_data),
    )

    audio_temp_path = None
    try:
        final_message = request.message
        prefetched_voice_features: Optional[dict] = None

        if request.audio_data:
            audio_temp_path = _save_audio_b64(request.audio_data)

        if audio_temp_path:
            final_message, prefetched_voice_features = await _preprocess_voice(
                audio_temp_path, request.message, label="CHAT"
            )

        result = await chat_with_agent(
            user_id=request.user_id,
            message=final_message,
            session_id=request.session_id,
            audio_file_path=audio_temp_path if not prefetched_voice_features else None,
            voice_features=prefetched_voice_features,
        )
        invalidate_user_cache(request.user_id, session_id=result.get("session_id") or request.session_id)
        logger.info(
            "Latency CHAT | done | user=%s | %.3fs | bottleneck=%s",
            safe_user,
            latency_seconds(request_start),
            result.get("latency_summary", {}).get("bottleneck"),
        )

        return ChatResponse(
            response=result.get("response", "I'm here to listen."),
            session_id=result.get("session_id"),
            **_emotion_payload_from_result(result),
            crisis_detected=result.get("crisis_detected", False),
            tools_used=result.get("tools_used", []),
            node_trace=result.get("node_trace", []),
            latency_trace=result.get("latency_trace", []),
            latency_summary=result.get("latency_summary", {}),
            technique_reasoning=result.get("technique_reasoning"),
            recommended_techniques_by_category=result.get("recommended_techniques_by_category", {}),
            alternative_techniques=result.get("alternative_techniques", []),
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.exception(
            "Latency CHAT | failed | user=%s | %.3fs | error=%s",
            safe_user,
            latency_seconds(request_start),
            redact_text(e),
        )
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")
    finally:
        if audio_temp_path and os.path.exists(audio_temp_path):
            try:
                os.remove(audio_temp_path)
            except Exception:
                pass


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """Token-streaming chat endpoint (Server-Sent Events)."""
    request_start = time.time()
    safe_user = pseudonymize_user_id(request.user_id)
    enforce_user_scope(http_request, request.user_id)

    async def event_generator():
        audio_temp_path = None
        first_token_logged = False
        try:
            final_message = request.message
            prefetched_voice_features: Optional[dict] = None

            if request.audio_data:
                audio_temp_path = _save_audio_b64(request.audio_data)

            if audio_temp_path:
                final_message, prefetched_voice_features = await _preprocess_voice(
                    audio_temp_path, request.message, label="STREAM"
                )

            stream = chat_with_agent_streaming(
                user_id=request.user_id,
                message=final_message,
                session_id=request.session_id,
                audio_file_path=audio_temp_path if not prefetched_voice_features else None,
                voice_features=prefetched_voice_features,
            )

            async for chunk_data in stream:
                if chunk_data["type"] == "token":
                    if not first_token_logged:
                        first_token_logged = True
                        logger.info(
                            "Latency STREAM | first_token | user=%s | %.3fs",
                            safe_user,
                            latency_seconds(request_start),
                        )
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk_data['content']})}\n\n"
                elif chunk_data["type"] == "done":
                    metadata = chunk_data["metadata"]
                    metadata["type"] = "done"
                    invalidate_user_cache(
                        request.user_id,
                        session_id=metadata.get("session_id") or request.session_id,
                    )
                    yield f"data: {json.dumps(metadata)}\n\n"
                    logger.info(
                        "Latency STREAM | complete | user=%s | %.3fs",
                        safe_user,
                        latency_seconds(request_start),
                    )

        except Exception as e:
            logger.exception(
                "Latency STREAM | failed | user=%s | %.3fs | error=%s",
                safe_user,
                latency_seconds(request_start),
                redact_text(e),
            )
            yield f"data: {json.dumps({'type': 'error', 'content': 'Something went wrong. Please try again.'})}\n\n"
        finally:
            if audio_temp_path and os.path.exists(audio_temp_path):
                try:
                    os.remove(audio_temp_path)
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/pipeline/complete")
async def pipeline_complete(request: PipelineRequest, http_request: Request):
    """Compatibility wrapper around /api/chat for frontend clients."""
    start_time = time.time()
    try:
        user_id = request.user_id
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")
        enforce_user_scope(http_request, user_id)

        result = await chat_with_agent(
            user_id=user_id,
            message=request.message,
            session_id=request.session_id,
        )
        invalidate_user_cache(user_id, session_id=result.get("session_id") or request.session_id)

        total_s = time.time() - start_time
        ep = _emotion_payload_from_result(result)

        return {
            "status": "success",
            "mood_analysis": {
                "sentiment": ep.get("sentiment", "neutral"),
                "emotion": ep.get("emotion", "neutral"),
                "intensity": ep.get("intensity", 0.5),
                "confidence": ep.get("confidence", 0.8),
                "raw_emotion_label": ep.get("raw_emotion_label"),
                "primary_sub_emotion": ep.get("primary_sub_emotion"),
                "secondary_sub_emotions": ep.get("secondary_sub_emotions", []),
                "detected_symptoms": ep.get("detected_symptoms", []),
                "detected_behaviors": ep.get("detected_behaviors", []),
                "detected_contexts": ep.get("detected_contexts", []),
                "emotion_scores": ep.get("emotion_scores", {}),
                "emotion_label": ep.get("emotion_label"),
            },
            "response": result.get("response", "I'm here to listen."),
            "crisis_detected": result.get("crisis_detected", False),
            "session_id": result.get("session_id"),
            "tools_used": result.get("tools_used", []),
            "node_trace": result.get("node_trace", []),
            "techniques": result.get("techniques", []),
            "performance": {
                "total_ms": int(total_s * 1000),
                "total_seconds": round(total_s, 3),
                "latency_summary": result.get("latency_summary", {}),
                "latency_trace": result.get("latency_trace", []),
            },
        }

    except Exception:
        return {
            "status": "success",
            "mood_analysis": {"sentiment": "neutral", "emotion": "neutral", "intensity": 0.5, "confidence": 0.5},
            "response": "I appreciate you sharing. How are you feeling right now?",
            "crisis_detected": False,
            "tools_used": [],
            "performance": {"total_ms": 0},
        }


@router.post("/api/chat/voice")
async def chat_voice(
    http_request: Request,
    audio: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    message: str = Form(""),
    session_id: Optional[str] = Form(None),
):
    """Voice-enabled chat: accepts a raw audio upload, transcribes via Gemini, then runs the pipeline."""
    request_start = time.time()
    temp_audio_path = None
    try:
        enforce_user_scope(http_request, user_id)
        audio_bytes = await audio.read()
        audio_format = _detect_audio_format(audio_bytes)
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
            tmp.write(audio_bytes)
            temp_audio_path = tmp.name

        final_message, prefetched_voice_features = await _preprocess_voice(
            temp_audio_path, message, label="VOICE"
        )
        transcription = final_message if final_message != message else ""

        result = await chat_with_agent(
            user_id=user_id,
            message=final_message,
            session_id=session_id,
            audio_file_path=temp_audio_path if not prefetched_voice_features else None,
            voice_features=prefetched_voice_features,
        )

        voice_features = result.get("voice_features") or {}
        voice_processed = bool(result.get("voice_processed") and voice_features)

        logger.info(
            "Latency VOICE | complete | user=%s session=%s | %.3fs",
            user_id,
            result.get("session_id") or session_id or "new",
            latency_seconds(request_start),
        )

        ep = _emotion_payload_from_result(result)
        return {
            "response": result.get("response", "I'm here to listen."),
            "session_id": result.get("session_id"),
            **ep,
            "voice_emotion": voice_features.get("emotion", "neutral") if voice_processed else None,
            "voice_confidence": voice_features.get("confidence", 0.0) if voice_processed else 0.0,
            "voice_primary_sub_emotion": voice_features.get("primary_sub_emotion") if voice_features else None,
            "voice_secondary_sub_emotions": voice_features.get("secondary_sub_emotions", []) if voice_features else [],
            "voice_detected_symptoms": voice_features.get("detected_symptoms", []) if voice_features else [],
            "voice_detected_behaviors": voice_features.get("detected_behaviors", []) if voice_features else [],
            "voice_detected_contexts": voice_features.get("detected_contexts", []) if voice_features else [],
            "transcription": transcription or result.get("transcription") or None,
            "acoustic_features": voice_features.get("acoustic_features", {}) if voice_features else {},
            "acoustic_distress_proxy": result.get("acoustic_distress_proxy"),
            "crisis_detected": result.get("crisis_detected", False),
            "tools_used": result.get("tools_used", []),
            "has_voice": True,
            "recommended_technique": result.get("recommended_technique"),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.exception(
            "Latency VOICE | failed | user=%s | %.3fs | error=%s",
            user_id,
            latency_seconds(request_start),
            e,
        )
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")
    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception:
                pass
