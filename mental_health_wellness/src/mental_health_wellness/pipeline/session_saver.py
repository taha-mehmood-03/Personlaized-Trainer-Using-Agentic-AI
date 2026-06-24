"""
Session Saver Node - Database and lightweight memory persistence

ARCHITECTURE NODE 7:
Purpose: Persist all conversation data for future reference and learning
Runs AFTER response generation (whether from crisis handler or response generator)

RESPONSIBILITIES:
1. Save message exchange to Prisma database
2. Save meaningful user turns to lightweight recall
3. Update user mood patterns and statistics
4. Cleanup temporary files (audio, etc)

ERROR HANDLING:
- If DB save fails: Logs error but continues to memory save
- If memory save fails: Logs error but continues to stats update
- If stats update fails: Logs error but continues to cleanup
- If cleanup fails: Logs error but doesn't prevent completion
- Never crashes - always returns completion status
"""

from ..agent.state import MentalHealthState
from ..tools import save_session as db_save_session
from ..db.prisma_json import prisma_json
from datetime import datetime, timezone, timedelta
from collections import Counter
import os


_NEGATIVE_EMOTIONS = {"anger", "disgust", "fear", "sadness", "anxiety"}
_POSITIVE_EMOTIONS = {"joy", "surprise"}


def _retention_until(days: int = 365) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def _clamped_float(value, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return default
    return max(0.0, min(1.0, number))


def _sentiment_for_emotion(emotion: str, explicit: str | None = None) -> str:
    emotion_lower = str(emotion or "neutral").lower().strip()
    if emotion_lower in _POSITIVE_EMOTIONS:
        derived = "POSITIVE"
    elif emotion_lower in _NEGATIVE_EMOTIONS:
        derived = "NEGATIVE"
    else:
        derived = "NEUTRAL"

    explicit_upper = str(explicit or "").upper().strip()
    if explicit_upper not in {"POSITIVE", "NEGATIVE", "NEUTRAL"}:
        return derived
    if explicit_upper == "NEUTRAL" and derived != "NEUTRAL":
        return derived
    return explicit_upper


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _turn_context_note(state: MentalHealthState) -> str | None:
    for key in ("current_topic", "active_thread_summary", "primary_concern", "triggering_context"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return None


def _technique_delivery_snapshot(state: MentalHealthState) -> dict:
    """Return the outcome baseline for a turn that delivers a technique."""
    if state.get("conversation_strategy", "") != "suggest_technique":
        return {}

    delivery_emotion = state.get(
        "technique_selection_emotion",
        state.get("fused_emotion", state.get("emotion", "neutral")),
    )
    delivery_intensity = state.get(
        "technique_selection_intensity",
        state.get("fused_intensity", state.get("intensity", 0.5)),
    )
    return {
        "technique_delivery_emotion": delivery_emotion,
        "technique_delivery_intensity": float(delivery_intensity),
        "technique_delivery_sub_emotion": state.get("primary_sub_emotion"),
        "technique_delivery_symptoms": _string_list(state.get("detected_symptoms")),
        "technique_delivery_behaviors": _string_list(state.get("detected_behaviors")),
    }


def _enum_text(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value).split(".")[-1]


def _latest_technique_payload(state: MentalHealthState, outcomes: list) -> dict:
    technique = state.get("recommended_technique") or state.get("latest_recommended_technique") or {}
    technique_id = ""
    technique_name = ""
    if isinstance(technique, dict):
        technique_id = technique.get("id") or technique.get("technique_id") or technique.get("techniqueId") or ""
        technique_name = technique.get("name") or ""

    recent = []
    for outcome in outcomes[:5]:
        recent.append({
            "technique_id": getattr(outcome, "techniqueId", None),
            "intensity_before": getattr(outcome, "intensityBefore", None),
            "intensity_after": getattr(outcome, "intensityAfter", None),
            "effectiveness": getattr(outcome, "effectiveness", None),
            "follow_through": getattr(outcome, "followThrough", None),
            "confidence": getattr(outcome, "confidence", None),
            "intervention_type": getattr(outcome, "interventionType", None),
        })

    return {
        "offered_this_turn": bool(state.get("technique_offered_this_turn", False)),
        "pending_outcome_id": state.get("pending_outcome_id"),
        "latest": {
            "id": technique_id or None,
            "name": technique_name or None,
        },
        "recent_outcomes": recent,
    }


async def update_structured_session_handoff(state: MentalHealthState) -> dict:
    """
    Persist a compact, structured handoff for the current session.

    The app does not have a single guaranteed "end session" event, so this
    updates the latest summary for the session after analytics persistence. It
    gives the next session a stable handoff without relying on raw transcript
    recall.
    """
    user_id = state.get("user_id", "")
    session_id = state.get("saved_session_id") or state.get("session_id", "")
    if not user_id or not session_id:
        return {"session_handoff_saved": False}

    try:
        from ..db.client import get_prisma_client
        from ..utils.turn_lifecycle import normalize_turn_type

        prisma = await get_prisma_client()
        session = await prisma.session.find_unique(where={"id": session_id})
        if not session:
            print(f"[NODE: SESSION_HANDOFF] Session {session_id[:20]} not found in DB, skipping")
            return {"session_handoff_saved": False}
        snapshots = await prisma.emotionsnapshot.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "asc"},
            take=200,
        )
        outcomes = await prisma.techniqueoutcome.find_many(
            where={"sessionId": session_id},
            order={"createdAt": "desc"},
            take=20,
        )

        turn_counts: Counter = Counter()
        final_snapshot = None
        for snapshot in snapshots:
            turn_type = normalize_turn_type(_enum_text(getattr(snapshot, "turnType", None)))
            if turn_type:
                turn_counts[turn_type] += 1
            final_snapshot = snapshot

        if not turn_counts and state.get("turn_type"):
            turn_counts[normalize_turn_type(str(state.get("turn_type")))] += 1

        final_emotion = (
            _enum_text(getattr(final_snapshot, "emotion", None)).lower()
            if final_snapshot
            else str(state.get("fused_emotion") or state.get("emotion") or "neutral").lower()
        )
        final_intensity = (
            _clamped_float(getattr(final_snapshot, "intensity", None), 0.5)
            if final_snapshot
            else _clamped_float(state.get("fused_intensity", state.get("intensity", 0.5)), 0.5)
        )

        peak_intensity = getattr(session, "peakIntensity", None) if session else None
        if peak_intensity is not None:
            relief_delta = _clamped_float(peak_intensity, 0.0) - final_intensity
            outcome = "improved" if relief_delta >= 0.15 else "difficult" if relief_delta <= -0.05 else "neutral"
        else:
            outcome = str(state.get("emotional_trend") or "neutral")

        summary_text, key_themes = _generate_rule_based_summary({**state, "fused_emotion": final_emotion, "fused_intensity": final_intensity})
        technique_payload = _latest_technique_payload(state, outcomes)
        technique_names = []
        latest_name = technique_payload.get("latest", {}).get("name")
        if latest_name:
            technique_names.append(latest_name)
        for outcome_row in outcomes[:5]:
            tech_id = getattr(outcome_row, "techniqueId", None)
            if tech_id and tech_id not in technique_names:
                technique_names.append(tech_id)

        existing = await prisma.sessionsummary.find_first(
            where={"sessionId": session_id},
            order={"createdAt": "desc"},
        )
        title = getattr(existing, "title", None) if existing else None
        title = title or f"Session - {final_emotion.capitalize()}"
        data = {
            "userId": user_id,
            "sessionId": session_id,
            "title": title[:100],
            "summary": summary_text[:1000],
            "emotion": final_emotion,
            "techniques": technique_names[:10],
            "outcome": outcome,
            "finalEmotion": final_emotion,
            "finalIntensity": final_intensity,
            "techniqueOffered": prisma_json(technique_payload),
            "turnTypeCounts": prisma_json(dict(turn_counts)),
            "keyThemes": key_themes[:12],
            "retentionUntil": _retention_until(365),
        }

        if existing:
            await prisma.sessionsummary.update(where={"id": existing.id}, data=data)
            summary_id = existing.id
        else:
            created = await prisma.sessionsummary.create(data=data)
            summary_id = created.id

        print(f"[NODE: SESSION_HANDOFF] Structured handoff saved for session {session_id[:20]}...")
        return {
            "session_handoff_saved": True,
            "session_handoff_summary_id": summary_id,
            "previous_session_handoff": {
                "final_emotion": final_emotion,
                "final_intensity": final_intensity,
                "turn_type_counts": dict(turn_counts),
                "technique_offered": technique_payload,
                "outcome": outcome,
            },
        }
    except Exception as err:
        print(f"[NODE: SESSION_HANDOFF] Handoff save failed (non-fatal): {str(err)[:140]}")
        return {"session_handoff_saved": False, "session_handoff_error": str(err)[:120]}


async def save_session(state: MentalHealthState) -> dict:
    """
    SESSION SAVER NODE - Persist all conversation data.
    
    STEP-BY-STEP PROCESS:
    1. Save message to Prisma DB (with emotion, crisis flag, voice data)
    2. Store meaningful user turn in lightweight recall
    3. Update user mood statistics
    4. Cleanup temporary files (audio from voice preprocessing)
    
    ERROR HANDLING:
    - Each step wrapped in try/except
    - Errors tracked in save_errors list
    - Continues to next step on failure
    - Returns completion status + error list
    
    Input State:
        - user_id: User identifier
        - messages: Conversation messages
        - final_response: Generated response
        - emotion: Detected emotion
        - crisis_detected: Crisis flag
        - session_id: Session identifier
        - temp_audio_path: (optional) Temp file to cleanup
        - voice_features: (optional) Voice analysis data
    
    Output State:
        - session_saved: Boolean
        - saved_session_id: Database session ID
        - save_errors: List of non-fatal errors during save
    """
    try:
        user_id = state.get("user_id", "")
        messages = state.get("messages", [])
        final_response = state.get("final_response", "")
        emotion = state.get("emotion", "neutral")
        persisted_emotion = state.get("fused_emotion") or emotion or "neutral"
        persisted_intensity = _clamped_float(
            state.get("fused_intensity", state.get("intensity", 0.5)),
            0.5,
        )
        persisted_sentiment = _sentiment_for_emotion(persisted_emotion, state.get("sentiment"))
        crisis_detected = state.get("crisis_detected", False)
        session_id = state.get("session_id", "")
        agent_role = state.get("agent_role", "coach")  # NEW: Get agent role
        recommended_technique = state.get("recommended_technique", None)
        voice_features = state.get("voice_features", {})
        
        save_errors = []
        
        print(f"\n[NODE: SESSION_SAVER]  Saving session data")
        print(f"[NODE: SESSION_SAVER] User: {user_id[:20] if user_id else 'UNKNOWN'}...")
        print(
            f"[NODE: SESSION_SAVER] Crisis: {crisis_detected}, "
            f"Emotion: {persisted_emotion}, Role: {agent_role}"
        )
        
        # ============================================
        # VALIDATE REQUIRED DATA
        # ============================================
        
        if not user_id:
            print("[NODE: SESSION_SAVER]  No user_id provided")
            return {
                "session_saved": False,
                "saved_session_id": None,
                "save_errors": ["Missing user_id"]
            }
        
        if not messages:
            print("[NODE: SESSION_SAVER]  No messages to save")
            return {
                "session_saved": False,
                "saved_session_id": None,
                "save_errors": ["No messages in state"]
            }
        
        # Use the last HUMAN message as the user message — NOT messages[-1].
        # Bypass routes (positive_feedback, technique_follow_up, …) append BOTH the
        # user turn AND the assistant reply to `messages` before persisting, so
        # messages[-1] is the AIMessage. Taking it blindly stored the assistant's
        # text in the USER row (user content overwritten by the assistant reply).
        def _is_human(m) -> bool:
            t = (getattr(m, "type", "") or getattr(m, "role", "") or "").lower()
            return t in ("human", "user") or m.__class__.__name__ == "HumanMessage"

        user_message = ""
        for _m in reversed(messages):
            if _is_human(_m):
                user_message = getattr(_m, "content", "") or ""
                break
        if not user_message and messages:
            # Fallback: last message that is NOT the assistant's final_response.
            _last = getattr(messages[-1], "content", "") or ""
            user_message = "" if _last == final_response else _last
        tools_used = state.get("tools_used", [])
        
        saved_session_id = None
        session_saved = False
        
        # ============================================
        # STEP 1: SAVE TO PRISMA DATABASE
        # ============================================
        
        print("[NODE: SESSION_SAVER]  Step 1: Saving to Prisma database...")
        
        try:
            # Prepare voice data if present
            voice_data = {}
            if voice_features:
                try:
                    voice_data = {
                        "voice_emotion": voice_features.get("emotion", "neutral"),
                        "voice_arousal": voice_features.get("arousal", 0.5),
                        "voice_valence": voice_features.get("valence", 0.5),
                        "voice_confidence": voice_features.get("confidence", 0.0),
                        "voice_distress_proxy": voice_features.get("acoustic_distress_proxy"),
                    }
                    print(f"[NODE: SESSION_SAVER]  Including voice data")
                except Exception as ve:
                    print(f"[NODE: SESSION_SAVER]  Voice data prep error: {str(ve)[:100]}")
                    save_errors.append(f"Voice data prep: {str(ve)[:100]}")
            
            # Save to database
            try:
                result = await db_save_session.ainvoke({
                    "user_id": user_id,
                    "user_message": user_message,
                    "assistant_response": final_response,
                    "emotion": persisted_emotion,
                    "sentiment": persisted_sentiment,
                    "intensity": persisted_intensity,
                    "crisis_level": "high" if crisis_detected else "low",
                    "session_id": session_id,
                    "agent_role": agent_role,  # NEW: Save agent role
                    "technique": recommended_technique,
                    "primary_sub_emotion": state.get("primary_sub_emotion"),
                    "secondary_sub_emotions": state.get("secondary_sub_emotions") or [],
                    "detected_symptoms": state.get("detected_symptoms") or [],
                    "detected_behaviors": state.get("detected_behaviors") or [],
                    "detected_contexts": state.get("detected_contexts") or [],
                    "emotion_scores": state.get("emotion_scores") or {},
                    "technique_offered_this_turn": bool(state.get("technique_offered_this_turn", False)),
                    **voice_data
                })
                
                saved_session_id = result.get("session_id", "unknown")
                session_saved = result.get("saved", False)
                
                if session_saved:
                    print(f"[NODE: SESSION_SAVER]  Prisma DB saved: {saved_session_id[:20] if saved_session_id else 'UNKNOWN'}")
                else:
                    print(f"[NODE: SESSION_SAVER]  Prisma save returned false (may still be queued)")
                    save_errors.append("Prisma save returned false")
                    
            except Exception as db_err:
                print(f"[NODE: SESSION_SAVER]  DB save error: {type(db_err).__name__}")
                print(f"[NODE: SESSION_SAVER] Details: {str(db_err)[:150]}")
                save_errors.append(f"DB save: {str(db_err)[:100]}")
                session_saved = False
                
        except Exception as e:
            print(f"[NODE: SESSION_SAVER]  CRITICAL DB error: {type(e).__name__}")
            print(f"[NODE: SESSION_SAVER] Details: {str(e)[:150]}")
            save_errors.append(f"Critical DB error: {str(e)[:100]}")

        # ============================================
        # STEP 2: SAVE TO LIGHTWEIGHT MEMORY
        # ============================================

        print("[NODE: SESSION_SAVER]  Step 2: Saving semantic memory...")
        try:
            if user_message and final_response:
                from ..memory import store_conversation_memory

                stored = await store_conversation_memory(
                    user_id=user_id,
                    user_message=user_message,
                    assistant_response=final_response,
                    emotion=emotion,
                    session_id=session_id or saved_session_id,
                )
                if not stored:
                    save_errors.append("Memory save returned false")
            else:
                print("[NODE: SESSION_SAVER]  Semantic memory skipped (missing user/assistant text)")
        except Exception as mem_err:
            print(f"[NODE: SESSION_SAVER]  Memory save failed: {str(mem_err)[:100]}")
            save_errors.append(f"Memory: {str(mem_err)[:100]}")
        

        # ============================================
        # STEP 3+4 (BATCHED): MOOD LOG + SESSION PHASE UPDATE
        # v6.0 FIX 5: Batch Prisma writes to reduce IPC round-trips.
        # Previously: 2-3 sequential calls (~200-500ms each on Windows).
        # Now: single batch_() call (~100-200ms total).
        # ============================================
        
        print("[NODE: SESSION_SAVER]  Step 3+4: Batched mood log + session phase update...")
        
        try:
            from ..db.client import get_prisma_client
            
            try:
                prisma = await get_prisma_client()
                
                # Validate intensity value
                intensity = persisted_intensity
                try:
                    intensity = float(intensity)
                    intensity = max(0.0, min(1.0, intensity))  # Clamp to [0, 1]
                except (ValueError, TypeError):
                    intensity = 0.5
                    print(f"[NODE: SESSION_SAVER]  Invalid intensity, using default")
                
                # Map emotion to valid Prisma Emotion enum
                from ..agent.preprocessing import normalize_emotion
                
                EMOTION_TO_PRISMA = {
                    # Direct matches
                    "anger": "ANGER", "disgust": "DISGUST", "fear": "FEAR",
                    "joy": "JOY", "neutral": "NEUTRAL", "sadness": "SADNESS",
                    "surprise": "SURPRISE", "anxiety": "ANXIETY",
                    # Common LLM outputs  closest Prisma enum
                    "happy": "JOY", "happiness": "JOY", "excited": "JOY",
                    "grateful": "JOY", "hopeful": "JOY", "content": "JOY",
                    "sad": "SADNESS", "depressed": "SADNESS", "lonely": "SADNESS",
                    "grief": "SADNESS", "melancholy": "SADNESS", "hopeless": "SADNESS",
                    "down": "SADNESS", "blue": "SADNESS", "empty": "SADNESS",
                    "miserable": "SADNESS",
                    "angry": "ANGER", "frustrated": "ANGER", "irritated": "ANGER",
                    "furious": "ANGER", "rage": "ANGER", "resentment": "ANGER",
                    "livid": "ANGER", "mad": "ANGER", "frustration": "ANGER",
                    "anxious": "ANXIETY", "worried": "ANXIETY", "nervous": "ANXIETY",
                    "stressed": "ANXIETY", "overwhelmed": "ANXIETY", "panic": "ANXIETY",
                    "tense": "ANXIETY", "uneasy": "ANXIETY", "dread": "ANXIETY",
                    "afraid": "FEAR", "scared": "FEAR", "terrified": "FEAR",
                    "frightened": "FEAR",
                    "confused": "NEUTRAL", "guilt": "SADNESS", "shame": "SADNESS",
                    "jealous": "ANGER", "envious": "ANGER",
                    "bored": "NEUTRAL", "tired": "NEUTRAL", "exhausted": "SADNESS",
                    "numb": "NEUTRAL",
                }
                
                normalized = normalize_emotion(persisted_emotion) if persisted_emotion else "neutral"
                emotion_lower = normalized.lower().strip()
                db_emotion = EMOTION_TO_PRISMA.get(emotion_lower, "NEUTRAL")
                
                print(f"[NODE: SESSION_SAVER]  Emotion mapping: '{persisted_emotion}'  '{normalized}'  '{db_emotion}'")
                
                emotion_to_sentiment = {
                    "JOY": "POSITIVE", "SURPRISE": "POSITIVE",
                    "NEUTRAL": "NEUTRAL",
                    "ANGER": "NEGATIVE", "DISGUST": "NEGATIVE", "FEAR": "NEGATIVE",
                    "SADNESS": "NEGATIVE", "ANXIETY": "NEGATIVE"
                }
                sentiment = _sentiment_for_emotion(db_emotion, persisted_sentiment)
                
                # Prepare session phase data
                conversation_phase = state.get("conversation_phase", "venting")
                intent_confidence = state.get("intent_confidence", 1.0)
                _PHASE_CONFIDENCE_THRESHOLD = 0.70
                should_update_phase = (
                    conversation_phase == "neutral"
                    or intent_confidence >= _PHASE_CONFIDENCE_THRESHOLD
                )
                PHASE_MAP = {
                    "venting":    "VENTING",
                    "reflection": "REFLECTION",
                    "solution":   "SOLUTION",
                    "recovery":   "RECOVERY",
                    "neutral":    "VENTING",
                }
                db_phase = PHASE_MAP.get(conversation_phase, "VENTING")
                
                #  BATCHED WRITE: mood log + session phase in one IPC call 
                try:
                    async with prisma.batch_() as batch:
                        batch.moodlog.create(
                            data={
                                "userId": user_id,
                                "emotion": db_emotion,
                                "intensity": intensity,
                                "sentiment": sentiment,
                                "primarySubEmotion": state.get("primary_sub_emotion"),
                                "secondarySubEmotions": _string_list(state.get("secondary_sub_emotions")),
                                "detectedSymptoms": _string_list(state.get("detected_symptoms")),
                                "detectedBehaviors": _string_list(state.get("detected_behaviors")),
                                "detectedContexts": _string_list(state.get("detected_contexts")),
                                "emotionScores": prisma_json(state.get("emotion_scores") or {}),
                                "context": _turn_context_note(state),
                                "retentionUntil": _retention_until(365),
                                # v14.0: trend + gate fields enable filtered regression + dashboard charts
                                "emotionalTrend": state.get("emotional_trend"),
                                "gateRoute": state.get("gate_route"),
                            }
                        )
                        if session_id:
                            _session_data: dict = {
                                # v14.0: persist per-session trend + recovery arc completion
                                "emotionalTrend": state.get("emotional_trend"),
                                "disclosureComplete": bool(state.get("session_disclosure_complete", False)),
                            }
                            if should_update_phase:
                                _session_data["phase"] = db_phase
                            batch.session.update(
                                where={"id": session_id},
                                data=_session_data,
                            )
                    
                    print(f"[NODE: SESSION_SAVER]  Batched write complete: mood={db_emotion}, phase={db_phase if should_update_phase else 'skipped'}")
                    
                except Exception as batch_err:
                    print(f"[NODE: SESSION_SAVER]  Batched write failed: {str(batch_err)[:100]}")
                    save_errors.append(f"Batched write: {str(batch_err)[:100]}")
                
                # Trigger LLM-powered session summary: content-aware condition.
                # Summarize when: >= 4 messages AND session had real therapeutic/advice content.
                # This prevents chitchat sessions from generating summaries while ensuring
                # deep 4-message therapeutic sessions always get one.
                msg_count = state.get("session_message_count", 0)
                conversation_strategy = state.get("conversation_strategy", "")
                gate_route = state.get("gate_route", "therapeutic")

                is_meaningful_turn = (
                    conversation_strategy not in ("", "no_action")
                    or gate_route in ("therapeutic", "crisis")
                )
                background_summary = (
                    os.getenv("SENTIMIND_BACKGROUND_LLM_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
                    or os.getenv("SENTIMIND_BACKGROUND_SESSION_SUMMARY", "0").lower() in {"1", "true", "yes", "on"}
                )
                should_summarize = background_summary and session_id and msg_count >= 4 and is_meaningful_turn

                if should_summarize and not state.get("anonymous_mode", False):
                    try:
                        import asyncio
                        from ..memory.session_summarizer import summarize_session

                        technique = state.get("recommended_technique", {})
                        technique_name = technique.get("name", "") if technique else ""
                        tech_list = [technique_name] if technique_name else []

                        _sum_trend = state.get("emotional_trend", "")
                        _sum_task = state.get("response_task", "")
                        _sum_phase = state.get("conversation_phase", "")
                        if (
                            _sum_trend == "improving"
                            or _sum_task in ("warm_close_and_invite", "positive_feedback")
                            or _sum_phase == "recovery"
                            or state.get("session_disclosure_complete", False)
                        ):
                            _sum_outcome = "helped"
                        elif _sum_task == "handle_technique_rejection":
                            _sum_outcome = "no_change"
                        else:
                            _sum_outcome = "neutral"

                        asyncio.create_task(summarize_session(
                            user_id=user_id,
                            session_id=session_id,
                            messages=messages,
                            emotion=persisted_emotion,
                            techniques=tech_list,
                            outcome=_sum_outcome
                        ))
                        print(f"[NODE: SESSION_SAVER]  LLM session summary scheduled (msg #{msg_count})")
                    except Exception as sum_err:
                        print(f"[NODE: SESSION_SAVER]  Summary task scheduling failed: {str(sum_err)[:80]}")
                        save_errors.append(f"Summary scheduling: {str(sum_err)[:80]}")

                # ============================================
                # v9.0: CLINICAL ASSESSMENT LOG WRITER
                # Persist PHQ-9/GAD-7 severity for longitudinal tracking
                # Only writes when severity > minimal (avoids noise)
                # ============================================
                clinical_severity = state.get("clinical_severity", "minimal")
                _SEVERITY_MAP = {
                    "minimal": "MINIMAL",
                    "mild": "MILD",
                    "moderate": "MODERATE",
                    "moderately_severe": "MODERATELY_SEVERE",
                    "severe": "SEVERE",
                }
                # positive_feedback stays here so _should_write_closing can fire on
                # those turns (bypass route positive_feedback turns need a closing
                # clinical snapshot). It is removed from analysis_and_planning's copy
                # so the clinical cache still gets refreshed for those turns.
                _CLINICAL_SKIP_ROUTES = {"chitchat", "positive_feedback", "memory_query", "technique_follow_up"}
                _current_gate_route = state.get("gate_route", "therapeutic")
                _skipped_this_turn = _current_gate_route in _CLINICAL_SKIP_ROUTES

                # Write a clinical log when severity > minimal on normal turns.
                # Also write on skip-route turns (positive_feedback/technique_follow_up)
                # when a session baseline exists — this captures the "After Therapy" score
                # even when the user sends a short follow-up message after completing an exercise.
                _raw_phq9 = state.get("clinical_raw_phq9") or state.get("clinical_phq9_score", 0)
                _raw_gad7 = state.get("clinical_raw_gad7") or state.get("clinical_gad7_score", 0)
                _start_score = state.get("session_start_clinical_score")

                # The severity stored in a log row MUST match the PHQ-9/GAD-7 scores
                # stored in that SAME row. Derive it from the raw scores we are about
                # to persist — never from the longitudinal/aggregated label, which can
                # legitimately differ from this single turn's numbers and otherwise
                # produces rows like "SEVERE (PHQ-9=2)" that look broken on the dashboard.
                from ..services.clinical_aggregator import _severity_from_scores as _sev_from_scores
                _score_severity = _sev_from_scores(int(_raw_phq9 or 0), int(_raw_gad7 or 0))

                _should_write_normal = (
                    _score_severity != "minimal"
                    and not _skipped_this_turn
                    and session_id
                )
                # Write closing snapshot on skip-route turns IF we already have a session
                # baseline (meaning a "Before Therapy" log was written earlier this session)
                # and we have real clinical scores in state.
                _should_write_closing = (
                    _skipped_this_turn
                    and session_id
                    and _start_score is not None
                    and _raw_phq9 > 0
                    and not _should_write_normal  # avoid double write
                )

                if (_should_write_normal or _should_write_closing) and session_id:
                    try:
                        db_severity = _SEVERITY_MAP.get(_score_severity, "MILD")
                        # Within-session delta: raw current score vs session-start baseline
                        _within_delta = round(_raw_phq9 - _start_score, 1) if _start_score is not None else state.get("clinical_delta")
                        await prisma.clinicalassessmentlog.create(data={
                            "sessionId": session_id,
                            "userId": user_id,
                            "severity": db_severity,
                            "phq9Score": _raw_phq9,
                            "gad7Score": _raw_gad7,
                            "indicators": state.get("clinical_indicators", []),
                            "confidence": state.get("clinical_confidence", 0.0),
                            "clinicalDelta": _within_delta,
                            "justification": None,
                            "retentionUntil": _retention_until(2555),
                        })
                        _log_kind = "closing snapshot" if _should_write_closing else db_severity
                        print(f"[NODE: SESSION_SAVER] 🏥 Clinical log saved: {_log_kind} "
                              f"(PHQ-9={_raw_phq9}, GAD-7={_raw_gad7}, delta={_within_delta})")
                    except Exception as clin_err:
                        print(f"[NODE: SESSION_SAVER]  Clinical log write failed: {str(clin_err)[:100]}")
                        save_errors.append(f"Clinical log: {str(clin_err)[:100]}")
                    
            except Exception as client_err:
                print(f"[NODE: SESSION_SAVER]  Prisma client error: {str(client_err)[:100]}")
                save_errors.append(f"Prisma client: {str(client_err)[:100]}")
                
        except ImportError as ie:
            print(f"[NODE: SESSION_SAVER]  DB module import error: {str(ie)[:100]}")
            save_errors.append("DB module not available")
        except Exception as e:
            print(f"[NODE: SESSION_SAVER]  CRITICAL stats error: {type(e).__name__}")
            print(f"[NODE: SESSION_SAVER] Details: {str(e)[:150]}")
            save_errors.append(f"Critical stats error: {str(e)[:100]}")
        
        # ============================================
        # STEP 5: CLEANUP TEMPORARY FILES
        # ============================================
        
        print("[NODE: SESSION_SAVER]  Step 4: Cleaning up temporary files...")
        
        temp_audio_path = state.get("temp_audio_path")
        if temp_audio_path:
            try:
                if os.path.exists(temp_audio_path):
                    try:
                        os.unlink(temp_audio_path)
                        print(f"[NODE: SESSION_SAVER]  Cleaned up temp file")
                    except Exception as del_err:
                        print(f"[NODE: SESSION_SAVER]  File deletion error: {str(del_err)[:100]}")
                        save_errors.append(f"File cleanup: {str(del_err)[:100]}")
                else:
                    print(f"[NODE: SESSION_SAVER]  Temp file already gone: {temp_audio_path}")
                    
            except Exception as e:
                print(f"[NODE: SESSION_SAVER]  Cleanup error: {type(e).__name__}")
                print(f"[NODE: SESSION_SAVER] Details: {str(e)[:150]}")
                save_errors.append(f"Cleanup: {str(e)[:100]}")
        
        # ============================================
        # RETURN SAVE STATUS WITH DIAGNOSTICS
        # ============================================
        
        if not save_errors:
            print(f"[NODE: SESSION_SAVER]  Session save complete - No errors")
        else:
            print(f"[NODE: SESSION_SAVER]  Session save complete - {len(save_errors)} non-fatal errors")
            for err in save_errors:
                print(f"  - {err}")

        # ============================================
        # FIX 5 SUPPORT: Capture within-session baseline on first turn
        # On the very first turn of a session, record the emotion and intensity.
        # OUTCOME_TRACKER uses this as the "before" baseline for effectiveness measurement.
        # This is ONLY set once per session (when session_start_emotion is None).
        # ============================================
        current_session_start_emotion = state.get("session_start_emotion")
        session_start_updates = {}
        if current_session_start_emotion is None:
            session_start_emotion = persisted_emotion
            session_start_intensity = persisted_intensity
            session_start_updates = {
                "session_start_emotion": session_start_emotion,
                "session_start_intensity": session_start_intensity,
                "session_start_sub_emotion": state.get("primary_sub_emotion"),
                "session_start_symptoms": _string_list(state.get("detected_symptoms")),
                "session_start_behaviors": _string_list(state.get("detected_behaviors")),
            }
            print(f"[NODE: SESSION_SAVER] Session baseline captured: "
                  f"{session_start_emotion} ({session_start_intensity:.0%})  will be used by OUTCOME_TRACKER")

        # Capture clinical baseline on the FIRST turn where real clinical data arrives.
        # Use raw per-turn scores (not aggregated max) so baseline matches the actual DB log.
        if state.get("session_start_clinical_score") is None:
            _first_phq = state.get("clinical_raw_phq9") or state.get("clinical_phq9_score", 0)
            _first_gad7 = state.get("clinical_raw_gad7") or state.get("clinical_gad7_score", 0)
            if _first_phq and _first_phq > 0:
                session_start_updates["session_start_clinical_score"] = float(_first_phq)
                session_start_updates["session_start_gad7_score"] = float(_first_gad7)
                print(f"[NODE: SESSION_SAVER] Clinical baseline captured: PHQ-9={_first_phq}, GAD-7={_first_gad7}")

        # ============================================
        # FIX 4: CAPTURE TECHNIQUE-DELIVERY MOMENT SNAPSHOT
        # When a technique is delivered THIS turn, record the emotion/intensity
        # at the EXACT moment of delivery. OUTCOME_TRACKER will compare the NEXT
        # message's emotion against THIS state  not the session-start state.
        # This measures "did emotions improve after the technique?" accurately.
        # ============================================
        technique_delivery_updates = _technique_delivery_snapshot(state)
        if technique_delivery_updates:
            print(f"[NODE: SESSION_SAVER] Technique delivery snapshot captured: "
                  f"{technique_delivery_updates['technique_delivery_emotion']} "
                  f"({technique_delivery_updates['technique_delivery_intensity']:.0%})  OUTCOME_TRACKER will measure from here")

        if session_saved:
            try:
                from ..services.cache_state import invalidate_user_cache

                invalidate_user_cache(user_id, session_id=saved_session_id or session_id)
            except Exception as cache_err:
                print(f"[NODE: SESSION_SAVER] Cache invalidation skipped: {str(cache_err)[:100]}")

        return {
            "session_saved": session_saved,
            "saved_session_id": saved_session_id,
            "save_errors": save_errors,
            **session_start_updates,  # FIX 5: inject session_start fields on first turn
            **technique_delivery_updates,  # FIX 4: inject technique_delivery fields when technique is suggested
        }
        
    except Exception as e:
        """
        CATCH-ALL ERROR HANDLER
        If anything goes catastrophically wrong, return error status
        Never crash - always return completion status
        """
        print(f"\n[NODE: SESSION_SAVER]  CATASTROPHIC ERROR")
        print(f"[NODE: SESSION_SAVER] Error Type: {type(e).__name__}")
        print(f"[NODE: SESSION_SAVER] Error Details: {str(e)[:200]}")
        
        import traceback
        error_trace = traceback.format_exc()
        print(f"[NODE: SESSION_SAVER] Traceback:\n{error_trace[:500]}")
        
        return {
            "session_saved": False,
            "saved_session_id": None,
            "save_errors": [f"Catastrophic error: {type(e).__name__}: {str(e)[:100]}"]
        }


def _generate_rule_based_summary(state: dict) -> tuple[str, list[str]]:
    """
    Generate a concise session summary using rule-based extraction.
    No LLM call  pure string analysis.
    
    Returns:
        (summary_text, key_themes)
    """
    emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
    intensity = state.get("fused_intensity", state.get("intensity", 0.5))
    trend = state.get("emotional_trend", "stable")
    strategy = state.get("conversation_strategy", "validate_only")
    phase = state.get("conversation_phase", "venting")
    technique = state.get("recommended_technique", {})
    technique_name = technique.get("name", "") if technique else ""
    msg_count = state.get("session_message_count", 0)
    
    # Extract key themes
    key_themes = []
    key_themes.append(f"emotion:{emotion}")
    if trend != "stable":
        key_themes.append(f"trend:{trend}")
    key_themes.append(f"phase:{phase}")
    if technique_name:
        key_themes.append(f"technique:{technique_name}")
    
    # Build summary string
    intensity_label = "high" if intensity > 0.7 else "moderate" if intensity > 0.4 else "mild"
    parts = [
        f"Session had {msg_count} messages.",
        f"Primary emotion: {emotion} ({intensity_label} intensity).",
        f"Emotional trend: {trend}.",
        f"Phase reached: {phase}.",
        f"Strategy used: {strategy}.",
    ]
    if technique_name:
        parts.append(f"Technique suggested: {technique_name}.")
    
    summary_text = " ".join(parts)
    return summary_text, key_themes
