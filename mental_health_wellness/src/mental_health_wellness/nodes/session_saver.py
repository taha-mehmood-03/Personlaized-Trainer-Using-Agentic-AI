"""
Session Saver Node - Database and vector memory persistence

ARCHITECTURE NODE 7:
Purpose: Persist all conversation data for future reference and learning
Runs AFTER response generation (whether from crisis handler or response generator)

RESPONSIBILITIES:
1. Save message exchange to Prisma database
2. Save conversation embedding to ChromaDB vector store
3. Update user mood patterns and statistics
4. Cleanup temporary files (audio, etc)

ERROR HANDLING:
- If DB save fails: Logs error but continues to vector memory
- If vector memory fails: Logs error but continues to stats update
- If stats update fails: Logs error but continues to cleanup
- If cleanup fails: Logs error but doesn't prevent completion
- Never crashes - always returns completion status
"""

from ..agent.state import MentalHealthState
from ..tools import save_session as db_save_session
from datetime import datetime


async def save_session(state: MentalHealthState) -> dict:
    """
    SESSION SAVER NODE - Persist all conversation data.
    
    STEP-BY-STEP PROCESS:
    1. Save message to Prisma DB (with emotion, crisis flag, voice data)
    2. Store conversation in ChromaDB for semantic retrieval
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
        crisis_detected = state.get("crisis_detected", False)
        session_id = state.get("session_id", "")
        agent_role = state.get("agent_role", "coach")  # NEW: Get agent role
        recommended_technique = state.get("recommended_technique", None)
        voice_features = state.get("voice_features", {})
        
        save_errors = []
        
        print(f"\n[NODE: SESSION_SAVER]  Saving session data")
        print(f"[NODE: SESSION_SAVER] User: {user_id[:20] if user_id else 'UNKNOWN'}...")
        print(f"[NODE: SESSION_SAVER] Crisis: {crisis_detected}, Emotion: {emotion}, Role: {agent_role}")
        
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
        
        user_message = messages[-1].content if messages else ""
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
                    "emotion": emotion,
                    "crisis_level": "high" if crisis_detected else "low",
                    "session_id": session_id,
                    "agent_role": agent_role,  # NEW: Save agent role
                    "technique": recommended_technique,
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
                intensity = state.get("intensity", 0.5)
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
                
                normalized = normalize_emotion(emotion) if emotion else "neutral"
                emotion_lower = normalized.lower().strip()
                db_emotion = EMOTION_TO_PRISMA.get(emotion_lower, "NEUTRAL")
                
                print(f"[NODE: SESSION_SAVER]  Emotion mapping: '{emotion}'  '{normalized}'  '{db_emotion}'")
                
                emotion_to_sentiment = {
                    "JOY": "POSITIVE", "SURPRISE": "POSITIVE",
                    "NEUTRAL": "NEUTRAL",
                    "ANGER": "NEGATIVE", "DISGUST": "NEGATIVE", "FEAR": "NEGATIVE",
                    "SADNESS": "NEGATIVE", "ANXIETY": "NEGATIVE"
                }
                sentiment = emotion_to_sentiment.get(db_emotion, "NEUTRAL")
                
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
                                "sentiment": sentiment
                            }
                        )
                        if session_id and should_update_phase:
                            batch.session.update(
                                where={"id": session_id},
                                data={"phase": db_phase}
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
                should_summarize = session_id and msg_count >= 4 and is_meaningful_turn

                if should_summarize:
                    try:
                        import asyncio
                        from ..memory.session_summarizer import summarize_session

                        technique = state.get("recommended_technique", {})
                        technique_name = technique.get("name", "") if technique else ""
                        tech_list = [technique_name] if technique_name else []

                        asyncio.create_task(summarize_session(
                            user_id=user_id,
                            session_id=session_id,
                            messages=messages,
                            emotion=emotion,
                            techniques=tech_list,
                            outcome="neutral"
                        ))
                        print(f"[NODE: SESSION_SAVER]  LLM session summary scheduled (msg #{msg_count})")
                    except Exception as sum_err:
                        print(f"[NODE: SESSION_SAVER]  Summary task scheduling failed: {str(sum_err)[:80]}")
                        save_errors.append(f"Summary scheduling: {str(sum_err)[:80]}")
                    
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
                import os
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
            session_start_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
            session_start_intensity = state.get("fused_intensity", state.get("intensity", 0.5))
            session_start_updates = {
                "session_start_emotion": session_start_emotion,
                "session_start_intensity": session_start_intensity,
            }
            print(f"[NODE: SESSION_SAVER] Session baseline captured: "
                  f"{session_start_emotion} ({session_start_intensity:.0%})  will be used by OUTCOME_TRACKER")

        # ============================================
        # FIX 4: CAPTURE TECHNIQUE-DELIVERY MOMENT SNAPSHOT
        # When a technique is delivered THIS turn, record the emotion/intensity
        # at the EXACT moment of delivery. OUTCOME_TRACKER will compare the NEXT
        # message's emotion against THIS state  not the session-start state.
        # This measures "did emotions improve after the technique?" accurately.
        # ============================================
        technique_delivery_updates = {}
        current_strategy = state.get("conversation_strategy", "")
        if current_strategy == "suggest_technique":
            delivery_emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
            delivery_intensity = state.get("fused_intensity", state.get("intensity", 0.5))
            technique_delivery_updates = {
                "technique_delivery_emotion": delivery_emotion,
                "technique_delivery_intensity": float(delivery_intensity),
            }
            print(f"[NODE: SESSION_SAVER] Technique delivery snapshot captured: "
                  f"{delivery_emotion} ({delivery_intensity:.0%})  OUTCOME_TRACKER will measure from here")

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
