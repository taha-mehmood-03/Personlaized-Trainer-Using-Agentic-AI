"""
Optimized Response Generator - Single LLM call with structured input

ARCHITECTURE NODE 5:
Purpose: Generate single empathetic response with structured data
Runs AFTER technique selector, BEFORE session saver
ONE LLM call only - receives structured data from previous nodes
"""

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional, AsyncIterator
import logging
import time
import os
import re

from ..agent.state import MentalHealthState
from ..llm import get_chat_llm, get_llm_manager


_context_logger = logging.getLogger("sentimind.context")


def _safe_content(response) -> str:
    """
    Safely extract a plain string from any LangChain LLM response or chunk.

    Gemini can return `.content` as a *list* of content-part dicts when the
    model produces multimodal / structured output. Any code that does
    ``response.content.lower()`` or ``"".join(c.content for c in chunks)``
    crashes with 'list has no attribute ...' or 'sequence item 0: expected str'.

    This helper normalises all variants to a UTF-8 string.
    """
    if response is None:
        return ""
    content = getattr(response, "content", None)
    if content is None:
        return str(response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text") or part.get("content") or "")
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)



def _debug_context_enabled() -> bool:
    return os.getenv("SENTIMIND_DEBUG_CONTEXT", "0").lower() in {"1", "true", "yes"}


def _debug_full_context_enabled() -> bool:
    return os.getenv("SENTIMIND_DEBUG_CONTEXT_FULL", "0").lower() in {"1", "true", "yes"}


def _clip(value, limit: int = 700) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _avoid_repeated_empathy_opening(response: str, recent_history: list) -> str:
    """
    Small safety polish for adjacent replies. The prompt asks the model to vary
    empathy, but this keeps common repeated openings from leaking through.
    """
    text = (response or "").lstrip()
    if not text:
        return response

    previous_ai = ""
    for turn in reversed(recent_history or []):
        if getattr(turn, "type", "") == "ai":
            previous_ai = getattr(turn, "content", "") or ""
            break

    if not previous_ai:
        return response

    previous_lower = previous_ai.lower()
    current_lower = text.lower()
    repeated_prior = any(
        phrase in previous_lower
        for phrase in (
            "that sounds really heavy",
            "that sounds heavy",
            "that sounds really painful",
            "that sounds painful",
        )
    )
    repeated_current = re.match(
        r"^that sounds (really )?(heavy|painful|hard|difficult|overwhelming)[,.\s]",
        current_lower,
    )
    if repeated_prior and repeated_current:
        return re.sub(
            r"^\s*that sounds (really )?(heavy|painful|hard|difficult|overwhelming)[,.]?\s*",
            "I can see why that would get to you. ",
            response,
            count=1,
            flags=re.IGNORECASE,
        )

    return response


def _strip_response_metadata_prefix(response: str) -> str:
    """Remove accidental model metadata prefixes from user-visible replies."""
    text = str(response or "")
    # Strip explicit SELECTED_TECHNIQUE_ID: <id> prefix
    text = re.sub(
        r"^\s*SELECTED_TECHNIQUE_ID\s*:\s*[^\s]+\s*(?:\r?\n)?",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    # Strip bare CUID/ID token the LLM sometimes emits without the label.
    # Shape: 8-32 lowercase alphanumeric chars at the very start, followed
    # by whitespace, so it won't eat real opening words like "certainly".
    text = re.sub(
        r"^\s*[a-z0-9]{8,32}(?=\s)",
        "",
        text,
        count=1,
    )
    text = re.sub(r"^\s*(?:0|1(?:\.0)?|0\.\d+)\s*(?:\r?\n)+", "", text)
    text = re.sub(
        r"^\s*(?:emotion|sub[_ -]?emotion|sentiment|intensity|confidence)\s*[:=]\s*[^\n\r]+(?:\r?\n)+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _clean_final_response(response: str, recent_history: list | None = None) -> str:
    text = _avoid_repeated_empathy_opening(response, recent_history or [])
    text = _strip_response_metadata_prefix(text).strip()
    return text or "I hear you. Thank you for sharing. How can I support you right now?"


def _response_includes_technique(response: str, technique: dict | None) -> bool:
    if not response or not isinstance(technique, dict):
        return False
    name = str(technique.get("name") or "").strip().lower()
    lowered = response.lower()
    if name and name in lowered:
        return True
    return bool(
        technique.get("id")
        and any(marker in lowered for marker in ("try this", "step 1", "start by", "breathe", "write down", "exercise"))
    )


def _extract_selected_technique_id(response: str) -> str:
    match = re.match(
        r"^\s*SELECTED_TECHNIQUE_ID\s*:\s*([^\s]+)",
        str(response or ""),
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _valid_technique_candidates(candidates) -> list[dict]:
    cleaned: list[dict] = []
    seen: set[str] = set()
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        tech_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not tech_id or not name or tech_id in seen:
            continue
        seen.add(tech_id)
        cleaned.append(item)
    return cleaned[:8]


def _candidate_by_selected_id(candidates: list[dict], selected_id: str) -> dict:
    if not selected_id:
        return {}
    for item in candidates:
        if str(item.get("id") or "").strip() == selected_id:
            return item
    return {}


def _format_technique_candidates(candidates: list[dict]) -> str:
    lines = []
    for index, item in enumerate(candidates, start=1):
        targets = ", ".join((item.get("target_sub_emotions") or [])[:5]) or "none"
        symptoms = ", ".join((item.get("target_symptoms") or [])[:4]) or "none"
        behaviors = ", ".join((item.get("target_behaviors") or [])[:4]) or "none"
        avoids = ", ".join(
            [
                *((item.get("avoid_sub_emotions") or [])[:3]),
                *((item.get("avoid_symptoms") or [])[:3]),
                *((item.get("avoid_behaviors") or [])[:3]),
            ]
        ) or "none"
        reasons = "; ".join((item.get("score_reasons") or [])[:3]) or "semantic shortlist"
        lines.append(
            f"{index}. id={item.get('id')} | name={item.get('name')} | "
            f"category={item.get('category', 'Unknown')} | brief={item.get('brief', '')} | "
            f"targets={targets} | symptoms={symptoms} | behaviors={behaviors} | "
            f"avoid={avoids} | reasons={reasons}"
        )
    return "\n".join(lines)


def _response_max_tokens(default: int = 1200) -> int:
    try:
        return int(os.getenv("SENTIMIND_RESPONSE_MAX_TOKENS", str(default)))
    except ValueError:
        return default


async def _invoke_response_llm(
    messages: list,
    *,
    max_tokens: int,
    temperature: float,
    config: Optional[dict] = None,
):
    """Final-response LLM call with Gemini key rotation and E2E streaming support."""
    manager = get_llm_manager()
    
    # Detect streaming request
    streaming = config and "tags" in config and "final_response_llm" in config["tags"]
    
    if streaming:
        if hasattr(manager, "astream_gemini_with_rotation"):
            print("[RESPONSE-GENERATOR] 🌀 True stream response active (Gemini key rotation)")
            chunks = []
            async for chunk in manager.astream_gemini_with_rotation(
                messages,
                model=getattr(manager, "model_response", None),
                max_tokens=max_tokens,
                temperature=temperature,
                config=config,
            ):
                chunks.append(chunk)
            if chunks:
                # _safe_content handles list content-parts from Gemini multimodal responses
                assembled = "".join(_safe_content(c) for c in chunks)
                return AIMessage(content=assembled)

    if hasattr(manager, "ainvoke_gemini_with_rotation"):
        return await manager.ainvoke_gemini_with_rotation(
            messages,
            model=getattr(manager, "model_response", None),
            max_tokens=max_tokens,
            temperature=temperature,
            config=config,
        )

    llm = get_chat_llm().bind(max_output_tokens=max_tokens, temperature=temperature)
    return await llm.ainvoke(messages, config=config)


def _extract_formulation_block(context_text: str) -> str:
    marker = "THERAPEUTIC FORMULATION:"
    if marker not in context_text:
        return ""
    start = context_text.find(marker)
    end = context_text.find("CLINICAL SEVERITY", start)
    if end == -1:
        end = context_text.find("USER CONTEXT:", start)
    if end == -1:
        end = min(len(context_text), start + 1000)
    return context_text[start:end].strip()


def _debug_print_response_context(
    *,
    state: MentalHealthState,
    recent_history: list,
    continuity_context: str,
    context_text: str,
    llm_messages: list,
) -> None:
    if not _debug_context_enabled():
        return

    formulation = _extract_formulation_block(context_text)
    checks = {
        "recent_history_injected": bool(recent_history),
        "continuity_block_injected": bool(continuity_context),
        "structured_context_injected": bool(context_text and "STRUCTURED ANALYSIS:" in context_text),
        "formulation_injected": bool(formulation),
        "response_task_injected": bool(state.get("response_task") and f"Response task: {state.get('response_task')}" in context_text),
        "active_thread_injected": bool(state.get("active_thread_summary") and str(state.get("active_thread_summary")) in context_text),
        "last_question_injected": bool(state.get("last_assistant_question") and str(state.get("last_assistant_question")) in context_text),
        "expected_answer_type_injected": bool(state.get("expected_answer_type") and str(state.get("expected_answer_type")) in context_text),
    }
    required = ["structured_context_injected", "formulation_injected", "response_task_injected"]
    verdict = "PASS" if all(checks[key] for key in required) else "WARN"

    roles = [getattr(message, "type", message.__class__.__name__) for message in llm_messages]
    _context_logger.info("Response Context Injection | %s", verdict)
    _context_logger.info("  checks: %s", checks)
    _context_logger.info("  llm_messages: count=%s | roles=%s", len(llm_messages), roles)
    _context_logger.info(
        "  injected_sizes: recent_history=%s | continuity_chars=%s | structured_chars=%s",
        len(recent_history),
        len(continuity_context),
        len(context_text),
    )
    _context_logger.info(
        "  routing: response_task=%s | stage=%s | intent=%s",
        state.get("response_task"),
        state.get("conversation_stage"),
        state.get("intent"),
    )
    _context_logger.info(
        "  active_thread_summary: %s",
        _clip(state.get("active_thread_summary"), 500) or "none",
    )
    _context_logger.info(
        "  last_question: %s | expected=%s",
        _clip(state.get("last_assistant_question"), 300) or "none",
        state.get("expected_answer_type") or "none",
    )
    _context_logger.info("  formulation_block: %s", _clip(formulation, 900) or "missing")
    if _debug_full_context_enabled():
        _context_logger.info("Response Full Continuity Context:\n%s", continuity_context or "none")
        _context_logger.info("Response Full Structured Context:\n%s", context_text)


class OptimizedResponse(BaseModel):
    """Structured response format for LLM"""
    response: str = Field(
        description="Warm empathetic response to user, acknowledging their emotion. "
                    "Can reference the technique if provided. 50-100 words."
    )


async def generate_response(state: MentalHealthState) -> dict:
    """
    OPTIMIZED RESPONSE GENERATOR - Single LLM call only.
    
    Process:
    1. Build ultra-concise system prompt (<150 tokens)
    2. Structure input data: emotion, intensity, technique, role
    3. Single LLM call with structured context
    4. Parse response
    
    Input State:
        - emotion: From mood analyzer
        - intensity: From mood analyzer
        - recommended_technique: From technique selector
        - agent_role: From role selector (or from crisis detection)
        - messages: Current user message
        - chat_history: For context
    
    Output State:
        - final_response: Complete response to send to user
    """
    
    try:
        # Guard: Don't overwrite crisis response
        if state.get("crisis_detected") and state.get("final_response"):
            print("[RESPONSE]  Crisis response already set")
            return {"final_response": state.get("final_response")}
        
        # Extract structured data
        emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        intensity = state.get("fused_intensity", state.get("intensity", 0.5))
        sentiment = state.get("sentiment", "neutral")
        primary_sub_emotion = state.get("primary_sub_emotion") or ""
        secondary_sub_emotions = state.get("secondary_sub_emotions") or []
        detected_symptoms = state.get("detected_symptoms") or []
        detected_behaviors = state.get("detected_behaviors") or []
        detected_contexts = state.get("detected_contexts") or []
        recommended_technique = state.get("recommended_technique", {})
        technique_candidates = _valid_technique_candidates(state.get("technique_candidates") or [])
        agent_role = state.get("agent_role", "coach")
        messages = state.get("messages", [])
        is_new_user = state.get("is_new_user", False)
        crisis_detected = state.get("crisis_detected", False)
        
        # NEW v3: distortion and behavioral activation context
        conversation_strategy = state.get("conversation_strategy", "validate_only")
        emotional_trend = state.get("emotional_trend", "stable")
        conversation_phase = state.get("conversation_phase", "venting")
        distortion_type = state.get("distortion_type")
        distortion_explanation = state.get("distortion_explanation")
        micro_action = state.get("micro_action")
        proactive_alert = state.get("proactive_alert")
        psych_profile = state.get("psych_profile", {})

        # v9.0: Clinical severity context
        clinical_severity = state.get("clinical_severity", "minimal")
        clinical_phq9 = state.get("clinical_phq9_score", 0)
        clinical_gad7 = state.get("clinical_gad7_score", 0)
        clinical_indicators = state.get("clinical_indicators", [])
        conversation_stage = state.get("conversation_stage", "DISCOVERY")
        current_intent = state.get("intent", "")
        needs_technique = state.get("needs_technique", False)
        response_task = state.get("response_task", "ask_next_context_question")
        latest_recommended_technique = state.get("latest_recommended_technique") or {}
        latest_rejected_technique = state.get("latest_rejected_technique") or {}
        preferred_techniques = state.get("preferred_techniques", []) or []
        if not needs_technique and current_intent != "accept_technique":
            recommended_technique = {}
            technique_candidates = []
        if response_task not in {"offer_one_technique", "ask_permission_before_technique"}:
            technique_candidates = []

        # NEW: voice acoustic context
        voice_features  = state.get("voice_features") or {}
        voice_processed = state.get("voice_processed", False)
        
        user_message = messages[-1].content if messages else ""
        # Within-session: full rolling message window from LangGraph state
        # (graph.py caps this at _MAX_MESSAGE_HISTORY, so this stays bounded).
        recent_history = _select_prompt_history(messages)
        # Cross-session: compact memory context from context_loader
        memory_context = state.get("memory_context", "")

        if response_task == "answer_memory_query" or current_intent == "memory_query":
            remembered = latest_recommended_technique or latest_rejected_technique or {}
            if remembered and remembered.get("name"):
                reply = f"The technique was **{remembered['name']}**."
            else:
                reply = "I do not have an exact technique name stored from this session yet."
            if _debug_context_enabled():
                _context_logger.info("Response Context Injection | PASS | direct_memory_query=True")
                _context_logger.info(
                    "  latest_recommended: %s",
                    remembered.get("name") if remembered else "none",
                )
                _context_logger.info(
                    "  active_thread_summary: %s",
                    _clip(state.get("active_thread_summary"), 500) or "none",
                )
            return {
                "final_response": reply,
                "response_task": "answer_memory_query",
                "latest_recommended_technique": latest_recommended_technique,
                "latest_rejected_technique": latest_rejected_technique,
            }

        #  Technique rejection detection 
        # Scan recent history for: (1) an AI message that contained a technique
        # suggestion, followed by (2) a user message expressing that it didn't work.
        _REJECTION_SIGNALS = {
            "didn't help", "did not help", "not working", "doesn't work", "doesn't feel",
            "didn't work", "still feeling", "still feel", "not helping", "try something else",
            "different exercise", "another exercise", "that didn't", "that didn't",
            "not useful", "useless", "no improvement", "no better", "same"
        }
        user_rejected_technique = False
        if len(recent_history) >= 2:
            last_user_msg = user_message.lower()
            if any(signal in last_user_msg for signal in _REJECTION_SIGNALS):
                # Check if the previous AI message suggested a technique
                prev_ai_msgs = [m for m in recent_history if getattr(m, "type", "") == "ai"]
                if prev_ai_msgs:
                    prev_ai_content = _safe_content(prev_ai_msgs[-1]).lower()
                    if any(kw in prev_ai_content for kw in ["technique", "exercise", "breathing", "mindfulness", "meditation"]):
                        user_rejected_technique = True
                        print(f"[NODE:RESPONSE]  TECHNIQUE REJECTION DETECTED  user signalled previous technique didn't help")

        # Technique acceptance is decided upstream by the LLM smart gate/planner.
        # Do not reinterpret "yes/ok/sure" here with keyword rules.
        user_accepted_technique = current_intent == "accept_technique" or response_task == "continue_active_technique"
        accepted_source = recommended_technique or latest_recommended_technique or state.get("active_technique") or {}
        accepted_technique_name = accepted_source.get("name") if isinstance(accepted_source, dict) else None
        if user_accepted_technique and accepted_technique_name:
            print(f"[NODE:RESPONSE]  Technique acceptance from planner: {accepted_technique_name}")

        print(f"[NODE:RESPONSE]  Generating | Role: {agent_role} | Emotion: {emotion} ({intensity:.0%}) | Strategy: {conversation_strategy}")
        if user_rejected_technique:
            print(f"[NODE:RESPONSE]  Will adapt response to acknowledge technique rejection")
        if distortion_type:
            print(f"[NODE:RESPONSE]  CBT Distortion: {distortion_type}")
        if memory_context:
            print(f"[NODE:RESPONSE]  Memory context available ({len(memory_context)} chars)  injecting into prompt")

        # ============================================
        # BUILD ULTRA-CONCISE SYSTEM PROMPT (<150 tokens)
        # ============================================
        
        # ============================================
        # FAST PATH: no_action (casual chitchat)
        # Avoid injecting all the emotion analysis noise into a grocery-list conversation
        # ============================================
        if conversation_strategy == "no_action":
            # Inject memory into casual path too so it doesn't hallucinate amnesia
            memory_info = ""
            if memory_context:
                memory_info = f"\nPAST SESSION MEMORIES: {memory_context[:600]}\nIMPORTANT MEMORY RULE: You DO have memory. If asked, refer to these memories. Do not invent past conversations."
            else:
                memory_info = "\nIMPORTANT MEMORY RULE: You DO have memory capabilities, but since this is a new session/account, there are no past memories yet. If asked, state honestly that we haven't talked much yet."
                
            simple_prompt = f"""You are SentiMind, a friendly companion. This is casual conversation unless the recent session thread shows the user is continuing a distress concern.
Respond naturally and warmly. Keep it short (1-2 sentences). NO therapy, NO emotion analysis, NO technique suggestions. If the current message is a short reply to an earlier distress thread, connect it back with empathy and ask one gentle follow-up.{memory_info}

 EMERGENCY SAFETY CLAUSE: If the user expresses ANY sudden sadness, fear, self-harm, or distress in this specific message, drop the casual tone immediately. Acknowledge their pain and offer gentle support instead of casual chitchat."""
            
            simple_msg = user_message

            # Build messages with within-session history so it can resolve references
            # across the whole rolling session window.
            fast_messages = [SystemMessage(content=simple_prompt)]
            continuity_context = _build_session_continuity_context(recent_history, user_message)
            if continuity_context:
                fast_messages.append(SystemMessage(content=continuity_context))
            if recent_history:
                for turn in recent_history:
                    role = getattr(turn, 'type', 'human')
                    content = getattr(turn, 'content', '')
                    if content:
                        if role == 'human':
                            fast_messages.append(HumanMessage(content=content))
                        else:
                            fast_messages.append(AIMessage(content=content))
                print(f"[NODE:RESPONSE]  Injected {len(recent_history)} recent turns into fast path")
            
            fast_messages.append(HumanMessage(content=simple_msg))
            # Tag the call so we can filter its stream events later
            casual_response = await _invoke_response_llm(
                fast_messages,
                max_tokens=int(os.getenv("SENTIMIND_CASUAL_RESPONSE_MAX_TOKENS", "320")),
                temperature=0.5,
                config={"tags": ["final_response_llm"]},
            )
            
            final_response = _safe_content(casual_response)
            final_response = _clean_final_response(final_response, recent_history)
            print(f"[NODE:RESPONSE]  Casual response generated (no_action fast path)")
            return {"final_response": final_response}

        # ============================================
        # BUILD SYSTEM PROMPT
        # ============================================

        system_prompt = _build_optimized_system_prompt(
            agent_role=agent_role,
            emotion=emotion,
            intensity=intensity,
            technique=recommended_technique,
            crisis_detected=crisis_detected,
            strategy=conversation_strategy,
            trend=emotional_trend,
            phase=conversation_phase,
            distortion_type=distortion_type,
            clinical_severity=clinical_severity,
            conversation_stage=conversation_stage,
            current_intent=current_intent,
            needs_technique=needs_technique,
            response_task=response_task,
            technique_candidates=technique_candidates,
            # v11.0: consent governance
            exercise_consent=state.get("exercise_consent", "unknown"),
            suppressed_topics=state.get("suppressed_topics") or [],
            active_issue_source=state.get("active_issue_source"),
            solution_preference=state.get("solution_preference", "unknown"),
            mismatch=bool(state.get("mismatch", False)),
            possible_masking=bool(state.get("possible_masking", False)),
            fusion_confidence=state.get("fusion_confidence"),
        )

        #  Rejection override: inject strong instruction into system prompt 
        if user_rejected_technique:
            rejection_instruction = (
                "\n\n CRITICAL CONTEXT  TECHNIQUE WAS REJECTED:\n"
                "The user has told you that the PREVIOUS technique or exercise you suggested did NOT help them.\n"
                "You MUST:\n"
                "  1. Acknowledge their frustration warmly (1 sentence)  e.g. 'I hear you, that one didn't resonate.'\n"
                "  2. Do NOT apologize excessively or repeat the same technique.\n"
                "  3. Do NOT suggest a replacement technique yet. Ask what felt unhelpful so you can understand.\n"
                "  4. Keep the response concise and compassionate.\n"
                "NEVER re-suggest the same technique name."
            )
            system_prompt += rejection_instruction

        #  Acceptance override: deliver the previously-offered technique 
        if user_accepted_technique:
            _tech_label = f'"{accepted_technique_name}"' if accepted_technique_name else "the technique you just offered"
            acceptance_instruction = (
                f"\n\n CRITICAL CONTEXT  USER ACCEPTED THE OFFERED TECHNIQUE:\n"
                f"The planner/gate has resolved the latest user message as agreement to try {_tech_label}. "
                f"Latest user message: \"{user_message}\".\n"
                f"You MUST:\n"
                f"  1. Respond warmly to their acceptance (1 sentence)  e.g. 'Great, let's do this together!'\n"
                f"  2. Name {_tech_label} and tell them the steps are ready in the exercise panel/sidebar.\n"
                f"  3. Do NOT suggest a completely different technique.\n"
                f"  4. Do NOT repeat the offer  they already accepted it.\n"
                f"  5. Ignore the freshly-detected emotion below if it contradicts this context  \n"
                f"     the user's intent is clear from upstream contextual routing. Follow through.\n"
                f"  6. Do NOT list, paraphrase, or invent technique steps. Steps come from the database/sidebar.\n"
                f"NEVER start a fresh technique suggestion when the user has already agreed to one."
            )
            system_prompt += acceptance_instruction
            print(f"[NODE:RESPONSE]  Acceptance override injected into system prompt")

            # Force UI to display the accepted technique instead of whatever new one was just picked
            if accepted_technique_name:
                print(f"[NODE:RESPONSE]  Fetching accepted technique: {accepted_technique_name}")
                try:
                    from ..tools.technique_tools import get_technique_by_name
                    accepted_tech = await get_technique_by_name(accepted_technique_name)
                    if accepted_tech:
                        recommended_technique = accepted_tech
                        print(f"[NODE:RESPONSE]  State override: UI will now display '{accepted_tech['name']}'")
                except Exception as e:
                    print(f"[NODE:RESPONSE]  Failed to fetch accepted technique: {e}")

        #  Safety net: force-fetch a new technique if rejection was detected but
        # the planner/selector didn't pick one (e.g., intent was misclassified as venting)
        consent_allows_force_fetch = (
            state.get("exercise_consent", "unknown") not in {"denied_soft", "denied_hard"}
            and state.get("solution_preference", "unknown") != "listen_only"
            and response_task != "ask_permission_before_technique"
        )
        if user_rejected_technique and needs_technique and not recommended_technique and consent_allows_force_fetch:
            print(f"[NODE:RESPONSE]  Rejection detected but no technique selected  force-fetching alternative")
            try:
                from ..tools.technique_tools import recommend_technique as _rt
                alt_top3 = await _rt.ainvoke({
                    "emotion": emotion,
                    "intensity": intensity,
                    "user_id": state.get("user_id", ""),
                    "primary_sub_emotion": primary_sub_emotion,
                    "secondary_sub_emotions": secondary_sub_emotions,
                    "detected_symptoms": detected_symptoms,
                    "detected_behaviors": detected_behaviors,
                    "detected_contexts": detected_contexts,
                })
                if alt_top3:
                    recommended_technique = alt_top3[0]
                    print(f"[NODE:RESPONSE]  Force-fetched alternative: {recommended_technique.get('name')}")
            except Exception as fe:
                print(f"[NODE:RESPONSE]  Force-fetch failed: {fe}")


        # ============================================
        # BUILD STRUCTURED INPUT CONTEXT
        # ============================================

        context_text = _build_structured_context(
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            primary_sub_emotion=primary_sub_emotion,
            secondary_sub_emotions=secondary_sub_emotions,
            detected_symptoms=detected_symptoms,
            detected_behaviors=detected_behaviors,
            detected_contexts=detected_contexts,
            technique=recommended_technique,
            agent_role=agent_role,
            is_new_user=is_new_user,
            user_message=user_message,
            strategy=conversation_strategy,
            trend=emotional_trend,
            phase=conversation_phase,
            distortion_type=distortion_type,
            distortion_explanation=distortion_explanation,
            micro_action=micro_action,
            proactive_alert=proactive_alert,
            psych_profile=psych_profile,
            memory_context=memory_context,
            voice_features=voice_features,
            voice_processed=voice_processed,
            text_emotion_raw=state.get("emotion", "neutral"),
            clinical_severity=clinical_severity,
            clinical_phq9=clinical_phq9,
            clinical_gad7=clinical_gad7,
            clinical_indicators=clinical_indicators,
            conversation_stage=conversation_stage,
            current_intent=current_intent,
            needs_technique=needs_technique,
            technique_candidates=technique_candidates,
            primary_concern=state.get("primary_concern"),
            concern_duration=state.get("concern_duration"),
            triggering_subject=state.get("triggering_subject"),
            triggering_context=state.get("triggering_context"),
            functional_impact=state.get("functional_impact"),
            core_belief=state.get("core_belief"),
            latest_recommended_technique=latest_recommended_technique,
            latest_rejected_technique=latest_rejected_technique,
            preferred_techniques=preferred_techniques,
            response_task=response_task,
            active_thread_summary=state.get("active_thread_summary"),
            last_assistant_question=state.get("last_assistant_question"),
            expected_answer_type=state.get("expected_answer_type"),
            # v11.0: consent governance
            exercise_consent=state.get("exercise_consent", "unknown"),
            suppressed_topics=state.get("suppressed_topics") or [],
            active_issue_source=state.get("active_issue_source"),
            solution_preference=state.get("solution_preference", "unknown"),
            mismatch=bool(state.get("mismatch", False)),
            possible_masking=bool(state.get("possible_masking", False)),
            fusion_confidence=state.get("fusion_confidence"),
        )

        # ============================================
        # PREPARE LLM MESSAGES WITH LAYERED MEMORY
        # ============================================

        llm_messages = [SystemMessage(content=system_prompt)]
        continuity_context = _build_session_continuity_context(recent_history, user_message)
        if continuity_context:
            llm_messages.append(SystemMessage(content=continuity_context))

        # Layer 1: Within-session recall  last 6 turns from LangGraph state (no DB, no token bloat)
        if recent_history:
            for turn in recent_history:
                role = getattr(turn, 'type', 'human')
                content = getattr(turn, 'content', '')
                if content:
                    if role == 'human':
                        llm_messages.append(HumanMessage(content=content))
                    else:
                        llm_messages.append(AIMessage(content=content))
            print(f"[NODE:RESPONSE]  Injected {len(recent_history)} recent turns (within-session memory)")

        # Layer 2: Structured analysis of current message (always last)
        llm_messages.append(HumanMessage(content=context_text))

        _debug_print_response_context(
            state=state,
            recent_history=recent_history,
            continuity_context=continuity_context,
            context_text=context_text,
            llm_messages=llm_messages,
        )
        
        start_time = time.time()
        
        # ============================================
        # SINGLE LLM CALL
        # ============================================
        
        # Tag the core therapeutic LLM call for event streaming filtering
        response = await _invoke_response_llm(
            llm_messages,
            max_tokens=_response_max_tokens(),
            temperature=0.7,
            config={"tags": ["final_response_llm"]},
        )
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        raw_response = _safe_content(response)
        selected_technique_id = _extract_selected_technique_id(raw_response)
        selected_technique = _candidate_by_selected_id(technique_candidates, selected_technique_id)

        if technique_candidates:
            _bar = "\u2500" * 64
            print(f"\n\u250c{_bar}\u2510")
            print(f"\u2502  LLM EXERCISE SELECTION  ({elapsed_ms}ms)")
            print(f"\u251c{_bar}\u2524")
            print(f"\u2502  Semantic Context:")
            print(f"\u2502    Emotion   : {emotion} (intensity={state.get('fused_intensity', state.get('intensity', 0.5)):.0%})")
            if primary_sub_emotion or secondary_sub_emotions:
                print(f"\u2502    Subs      : {primary_sub_emotion or 'None'} (secondary: {secondary_sub_emotions})")
            if detected_symptoms or detected_behaviors:
                print(f"\u2502    Clinical  : symptoms={detected_symptoms} | behaviors={detected_behaviors}")
            if distortion_type:
                print(f"\u2502    Distortion: {distortion_type}")
            if detected_contexts:
                print(f"\u2502    Triggers  : {detected_contexts}")
            print(f"\u2502    System    : intent={current_intent} | task={response_task}")
            print(f"\u2502  Shortlist: {len(technique_candidates)} candidates passed to LLM")
            for _idx, _cand in enumerate(technique_candidates, 1):
                _marker = "\u2605" if selected_technique and _cand.get("id") == selected_technique.get("id") else " "
                print(f"\u2502    {_idx}. {_marker} [{_cand.get('id','?')}] {_cand.get('name')} [{_cand.get('category','?')}]")
            if selected_technique:
                print(f"\u2502  \u2714 LLM PICKED : {selected_technique.get('name')} (id={selected_technique_id})")
            elif selected_technique_id:
                print(f"\u2502  \u26a0 Invalid id : '{selected_technique_id}' not in shortlist \u2014 using pre-selected")
            else:
                print(f"\u2502  \u2139 No LLM pick: using pre-selected technique from selector node")
            print(f"\u2514{_bar}\u2518")
        else:
            print(f"[NODE:RESPONSE] Generated in {elapsed_ms}ms ({len(_safe_content(response))} chars) | no candidates")

        final_response = _clean_final_response(raw_response, recent_history)
        print(f"[NODE:RESPONSE] Response ready: {elapsed_ms}ms | {len(final_response)} chars")


        result = {
            "final_response": final_response,
            "response_task": response_task,
            "technique_candidates": technique_candidates,
        }
        if selected_technique_id:
            result["llm_selected_technique_id"] = selected_technique_id
        if selected_technique and response_task == "ask_permission_before_technique":
            result["pending_recommended_technique"] = selected_technique
            result["pending_technique_reason"] = "LLM selected from semantic shortlist"
            result["pending_technique_created_at_turn"] = state.get("session_message_count", 0)
        elif selected_technique:
            recommended_technique = selected_technique
            result["alternative_techniques"] = [
                item
                for item in technique_candidates
                if item.get("id") != selected_technique.get("id")
            ][:2]
        # Propagate technique back to state (important when force-fetched during rejection)
        if recommended_technique and recommended_technique.get("name"):
            cat = recommended_technique.get("category", "Recommended")
            technique_offered_this_turn = _response_includes_technique(final_response, recommended_technique)
            result["recommended_technique"] = recommended_technique
            result["recommended_techniques_by_category"] = {cat: recommended_technique}
            result["latest_recommended_technique"] = recommended_technique
            result["technique_offered_this_turn"] = technique_offered_this_turn
            if technique_offered_this_turn:
                result["turn_technique_id"] = (
                    recommended_technique.get("id")
                    or recommended_technique.get("technique_id")
                    or recommended_technique.get("techniqueId")
                )
        elif latest_recommended_technique:
            result["latest_recommended_technique"] = latest_recommended_technique
            result["technique_offered_this_turn"] = False
        if current_intent == "reject_technique" and latest_recommended_technique:
            result["latest_rejected_technique"] = latest_recommended_technique
        if latest_rejected_technique:
            result["latest_rejected_technique"] = latest_rejected_technique
        if preferred_techniques:
            result["preferred_techniques"] = preferred_techniques

        return result

        
    except Exception as e:
        print(f"[NODE:RESPONSE]  Error generating response: {str(e)[:100]}")
        fallback = _build_contextual_fallback_response(state)
        return {"final_response": fallback}


def _build_contextual_fallback_response(state: MentalHealthState) -> str:
    """Grounded fallback for provider failures; avoids the tiny generic response."""
    messages = state.get("messages", []) or []
    user_message = (getattr(messages[-1], "content", "") if messages else "").strip()
    response_task = state.get("response_task", "")
    primary = state.get("primary_concern") or state.get("active_thread_summary") or user_message
    duration = state.get("concern_duration")
    subject = state.get("triggering_subject")

    if state.get("crisis_detected"):
        return (
            "I'm really glad you told me. This sounds serious, and I want to focus on your immediate safety. "
            "Are you safe right now, or is there someone nearby you can contact?"
        )

    if response_task == "give_reflective_opinion":
        return (
            f"From what you've shared, this seems less like a small mood shift and more like something that has been weighing on you"
            f"{f' for {duration}' if duration else ''}. "
            "It makes sense that it would feel heavy. What feels like the biggest part of it right now?"
        )

    if response_task == "summarize_known_context" or "context_complete" in (state.get("gate_context_flags") or []):
        details = []
        if primary:
            details.append(str(primary))
        if subject:
            details.append(f"connected to {subject}")
        if duration:
            details.append(f"going on for {duration}")
        known = ", ".join(details) if details else "what you've already shared"
        return (
            f"Okay, I won't keep digging for more details. The main thread I have is: {known}. "
            "We can stay with that and move toward what would help you handle the next part."
        )

    if response_task == "handle_technique_rejection":
        latest = state.get("latest_recommended_technique") or {}
        name = latest.get("name") if isinstance(latest, dict) else ""
        return (
            f"That makes sense, {name + ' ' if name else 'that exercise '}didn't fit for you. "
            "What part felt unhelpful: the timing, the steps, or the feeling it brought up?"
        )

    if primary and primary != user_message:
        return (
            f"I hear you. It sounds like the main thread is {primary}. "
            "What part of that feels hardest to carry today?"
        )

    return (
        "I hear you. That sounds like a lot to sit with. "
        "What has been the hardest part of it today?"
    )


def _build_session_continuity_context(recent_history: list, user_message: str) -> str:
    """
    Build a small instruction block that teaches the LLM how to use the raw
    within-session history that follows. This is prompt-only context: no DB,
    no extra model call, and no change to graph routing.
    """
    if not recent_history:
        return ""

    active_summary = _infer_active_thread_summary(recent_history, user_message)
    lines = [
        "CURRENT SESSION THREAD FOR REFERENCE RESOLUTION:",
        "Use the entire thread below before answering. The latest user message may be a continuation, correction, answer, acceptance, rejection, or reference to something earlier.",
        "If the current user message is brief, assume it answers the most recent assistant question unless the thread clearly says otherwise.",
        "Resolve 'it', 'that', and 'this' to the active concern across the session, not only the latest noun.",
        "When a user asks 'what do you think about it?', explain the active pattern from the whole thread rather than treating 'it' as a new vague topic.",
        "Do not restart the conversation or give generic advice when the user is continuing the same concern.",
        "Do not ask broad restart questions like 'what has been going on?' or 'what has been on your mind?' when recent turns already explain it.",
        "Ask the next useful question from the known thread, or reflect the active pattern in the current moment.",
        "",
        "Conversation thread:",
    ]
    if active_summary:
        lines.extend(["", "Active formulation from recent turns:", active_summary, ""])

    for turn in recent_history:
        role = getattr(turn, "type", "human")
        content = (getattr(turn, "content", "") or "").strip()
        if not content:
            continue
        label = "Assistant" if role == "ai" else "User"
        lines.append(f"{label}: {content[:500]}")

    lines.extend([
        "",
        f"Current user message to resolve: {user_message[:500]}",
    ])
    return "\n".join(lines)


def _select_prompt_history(messages: list) -> list:
    """Return the bounded same-session history injected into the final LLM call."""
    if len(messages) <= 1:
        return []
    try:
        limit = int(os.getenv("SENTIMIND_RESPONSE_HISTORY_MESSAGES", "8"))
    except ValueError:
        limit = 8
    limit = max(2, min(limit, 16))
    return list(messages[:-1])[-limit:]


def _infer_active_thread_summary(recent_history: list, user_message: str) -> str:
    """Build a compact same-session formulation from recent turns.

    This is intentionally heuristic and local: it avoids extra latency and keeps
    continuity grounded in the user's own recent words.
    """
    text_parts = [
        (getattr(turn, "content", "") or "")
        for turn in recent_history[-8:]
        if getattr(turn, "type", "") == "human"
    ]
    combined = " ".join([*text_parts, user_message or ""]).lower()
    notes: list[str] = []

    if any(k in combined for k in ("anxious", "anxiety", "off lately", "not like myself")):
        notes.append("The active concern is ongoing anxiety / feeling off, not a new standalone issue.")
    if any(k in combined for k in ("heavy", "tired", "drained", "not like myself")):
        notes.append("They described heaviness, tiredness, feeling drained, and not feeling like themselves.")
    if any(k in combined for k in ("chest", "tightness", "shoulders", "tense")):
        notes.append("They feel it physically as chest tightness and shoulder tension.")
    if any(k in combined for k in ("work", "routine", "small things", "piling up")):
        notes.append("The pressure seems to come from routine/work/small things piling up, not one big event.")
    if any(k in combined for k in ("should be fine", "should be doing", "guilty", "guilt")):
        notes.append("A key loop is pressure/shoulds -> guilt -> more tiredness.")
    if any(k in combined for k in ("shut down", "staring at my phone", "stare at my phone", "wall", "nothing gets done", "wasting time")):
        notes.append("When overwhelmed, they shut down, stare at the phone/wall, get little done, then feel worse.")
    if any(k in (user_message or "").lower() for k in ("not good", "not okay", "not ok", "bad currently", "currently")) and notes:
        notes.append("The current message means they are inside that same difficult loop right now.")

    return "\n".join(f"- {note}" for note in notes)


def _build_optimized_system_prompt(
    agent_role: str,
    emotion: str,
    intensity: float,
    technique: dict,
    crisis_detected: bool,
    strategy: str = "validate_only",
    trend: str = "stable",
    phase: str = "venting",
    distortion_type: str | None = None,
    clinical_severity: str = "minimal",
    conversation_stage: str = "DISCOVERY",
    current_intent: str = "",
    needs_technique: bool = False,
    response_task: str = "ask_next_context_question",
    technique_candidates: list[dict] | None = None,
    # v11.0: consent governance
    exercise_consent: str = "unknown",
    suppressed_topics: list | None = None,
    active_issue_source: str | None = None,
    solution_preference: str = "unknown",
    mismatch: bool = False,
    possible_masking: bool = False,
    fusion_confidence: float | None = None,
) -> str:
    """
    Build the SentiMind system prompt  comprehensive, scenario-aware, edge-case hardened.
    Handles: technique rejection, refusal of exercises, venting only, good news,
    anger at bot, short messages, clinical signals, and cross-session memory.
    """

    #  CRISIS OVERRIDE 
    if crisis_detected:
        return """You are SentiMind, a mental health companion in CRISIS MODE.

YOUR ONLY JOB RIGHT NOW:
- Keep the user alive and connected through the next few minutes.
- Be warm, direct, steady, and serious. Do not sound casual or generic.
- Start by naming that you are really glad they told you and that their life matters right now.
- Ask them to make one immediate safety move: put distance between themselves and anything they could use to hurt themselves, or move near another person.
- Encourage real-world support: ask them to contact a trusted person nearby or local emergency services now if they might act on the urge.
- Ask ONE direct safety question: "Are you in immediate danger right now?" or "Can you move away from the thing you might use to hurt yourself?"
- Keep them engaged: invite a short reply like "just send me one word: safe or not safe."
- Do NOT suggest normal wellness techniques, exercises, productivity advice, or generic coping lists.
- Do NOT debate, shame, guilt, threaten, or say "think of your family."
- Do NOT minimize ("it'll get better"), invalidate ("things could be worse"), or rush into problem-solving.
- Do NOT reference past memories or previous sessions; focus entirely on NOW.

Response shape:
1. 1-2 sentences of serious validation and connection.
2. 1-2 sentences asking for immediate safety action and real-world support.
3. One direct safety question or one-word check-in.

Tone: Deeply human, calm, protective, and present. The goal is not therapy; the goal is helping them not act on the urge right now."""

    # ============================================
    # v11.0: CONSENT OVERRIDE — Listen-only mode
    # If exercise_consent == "denied", inject a hard rule that blocks ALL
    # technique language regardless of strategy or response_task.
    # ============================================
    consent_override_block = ""
    # v11.0: Differentiate between listen_only mode and advice_allowed mode.
    # Case 1: The user wants to talk and just be heard (venting only). No exercises and no advice.
    if solution_preference == "listen_only":
        _lines = [
            "╔══════════════════════════════════════════════════╗",
            "║  CONSENT OVERRIDE — LISTEN-ONLY MODE ACTIVE     ║",
            "╚══════════════════════════════════════════════════╝",
            "The user has explicitly said they just want to vent and be heard. They do NOT want exercises or advice.",
            "STRICT PROHIBITIONS — any violation is a critical failure:",
            "  • NEVER suggest, name, hint at, or prepare ANY technique or coping exercise.",
            "  • NEVER offer suggestions, advice, or problem-solving solutions.",
            "  • NEVER say 'Would you like to try…', 'We could practice…', or similar.",
            "Your ONLY job is to LISTEN, VALIDATE, and REFLECT with warm, compassionate friendship.",
        ]
        consent_override_block = "\n\n" + "\n".join(_lines)

    # Case 2: The user is open to dialogue-based advice/suggestions but has blocked formal/physical exercises.
    elif exercise_consent in ("denied_soft", "denied_hard") or solution_preference == "advice_allowed":
        _lines = [
            "╔══════════════════════════════════════════════════╗",
            "║  CONSENT OVERRIDE — CBT EXERCISES BLOCKED        ║",
            "╚══════════════════════════════════════════════════╝",
            "The user wants warm suggestions and advice, but does NOT want homework, breathing exercises, or formal CBT techniques.",
            "STRICT PROHIBITIONS — any violation is a critical failure:",
            "  • NEVER suggest, name, hint at, or prepare ANY formal coping exercise or technique.",
            "  • NEVER list therapy exercises (e.g. journaling, breathing exercises, progressive relaxation).",
            "  • NEVER end a reply with an offer to try a practice or exercise.",
            "PERMITTED SOLUTIONS:",
            "  • Provide warm, conversational CBT suggestions, alternate perspectives, and gentle reframings directly in dialogue.",
            "  • Act as a wise, supportive, compassionate friend who helps them think through things verbally.",
        ]
        consent_override_block = "\n\n" + "\n".join(_lines)

    # ============================================
    # v11.0: STALE TOPIC SUPPRESSION
    # If the user has corrected old memories, inject an explicit block
    # telling the LLM never to reference those topics.
    # ============================================
    suppression_block = ""
    _suppressed_labels = [
        t.get("topic", "") for t in (suppressed_topics or []) if t.get("topic")
    ]
    if _suppressed_labels:
        _suppression_lines = [
            "STALE TOPIC SUPPRESSION — MANDATORY:",
            "The user has explicitly corrected you. The following topics are NOT the reason",
            "for their current distress and MUST NEVER be referenced, implied, or used to",
            "select a technique:",
            "  - " + "\n  - ".join(_suppressed_labels),
        ]
        if active_issue_source:
            _suppression_lines.append(
                f"The user says the REAL reason is: '{active_issue_source}'. "
                "Focus on this instead."
            )
        suppression_block = "\n\n" + "\n".join(_suppression_lines)

    masking_block = ""
    if mismatch or possible_masking:
        confidence_text = ""
        if fusion_confidence is not None:
            try:
                confidence_text = f" Fusion confidence: {max(0.0, min(1.0, float(fusion_confidence))):.0%}."
            except (TypeError, ValueError):
                confidence_text = ""
        masking_block = (
            "\n\nPOSSIBLE EMOTION MISMATCH:\n"
            "- The user's words and nonverbal/context signals may not fully match."
            f"{confidence_text}\n"
            "- Do not assert that the user feels differently than they said.\n"
            "- Use gentle uncertainty: 'part of this sounds...', 'I might be wrong, but...', or 'there may be more under this.'\n"
            "- Validate what they stated first, then make room for hidden strain without over-interpreting."
        )

    #  ROLE INSTRUCTIONS 
    role_instructions = {
        "friend":        "You are a warm, non-clinical friend. ONLY listen and validate. Never push exercises unless explicitly asked.",
        "coach":         "You are a supportive coach. Validate first, then guide gently. Introduce a technique only if the strategy says so.",
        "trainer":       "You are a confident trainer. Validate strongly, then present the technique with energy. Do not generate steps; the database/sidebar provides them.",
        "crisis_support":"You are in crisis support mode. Keep the user alive and connected right now. Be direct, warm, and protective. Ask for immediate safety and real-world support. No normal wellness techniques.",
    }
    role_desc = role_instructions.get(agent_role, role_instructions["coach"])

    #  TECHNIQUE DESCRIPTION 
    technique_desc = ""
    candidate_selection_allowed = (
        bool(technique_candidates)
        and needs_technique
        and response_task in {"offer_one_technique", "ask_permission_before_technique"}
        and current_intent != "accept_technique"
    )
    if candidate_selection_allowed:
        technique_desc = (
            "\n\nTECHNIQUE SELECTION MODE:\n"
            "- A safe semantic shortlist is provided in the structured context.\n"
            "- Choose exactly one candidate id that best fits the gathered context.\n"
            "- Your first line MUST be exactly: SELECTED_TECHNIQUE_ID: <candidate_id>\n"
            "- After that first line, write only the user-facing response.\n"
            "- If response_task is ask_permission_before_technique, still choose an id, but do not name or describe the technique to the user.\n"
            "- If response_task is offer_one_technique, name only the chosen technique and do not mention unselected candidates.\n"
            "- Never choose an exercise whose avoid tags conflict with the user's current state."
        )
    elif needs_technique and technique and technique.get("name"):
        technique_desc = (
            f"\n\nTECHNIQUE TO INTRODUCE:\n"
            f"- Name: {technique.get('name')}\n"
            f"- Duration: {technique.get('duration_minutes', 'N/A')} min\n"
            f"- Category: {technique.get('category', 'N/A')}\n"
            f"- Why it works: {technique.get('why_it_works', '')}"
            f"\n- Reasons it fits this moment: {'; '.join(technique.get('score_reasons', []))}" if technique.get("score_reasons") else ""
        )

    #  STRATEGY INSTRUCTIONS 
    strategy_instructions = {
        "no_action": (
            "STRATEGY  CASUAL CONVERSATION:\n"
            "This message is casual or off-topic. Respond like a warm, friendly companion.\n"
            "Do NOT analyze emotions, validate feelings therapeutically, or suggest any technique.\n"
            "Keep it short (1-2 sentences), natural, and friendly."
        ),
        "validate_only": (
            "STRATEGY  PURE VALIDATION:\n"
            "The user needs to feel heard  not fixed. Only listen and validate.\n"
            "Do NOT suggest any technique, exercise, or coping mechanism  even if one is listed below.\n"
            "Reflect their emotion back to them with warmth and empathy."
        ),
        "ask_question": (
            "STRATEGY  UNDERSTAND FIRST:\n"
            "Validate their feelings briefly, then ask ONE thoughtful, open-ended question.\n"
            "The question should build on known details from the recent thread before any action.\n"
            "Do NOT ask broad restart questions like 'what's been going on?' if the recent thread already contains details.\n"
            "Do NOT suggest, name, hint at, or prepare a technique yet. Do NOT ask more than 1 question."
        ),
        "encourage_reflection": (
            "STRATEGY  ENCOURAGE REFLECTION:\n"
            "The user is reflecting on their feelings or reporting on a technique they tried.\n"
            "Celebrate or validate their self-awareness.\n"
            "Ask a gentle question about their experience (e.g., 'What did you notice in your body?').\n"
            "Do NOT introduce a new technique  they are already in a reflective process."
        ),
        "reframe": (
            "STRATEGY  GENTLE REFRAME:\n"
            "Validate first, then gently offer a new perspective without being preachy.\n"
            "Don't label their thinking as a 'distortion'  just model the alternative thinking naturally.\n"
            "End with an open question or a supportive next step."
        ),
        "suggest_technique": (
            "STRATEGY  SUGGEST TECHNIQUE:\n"
            "Validate the user's feelings first (1-2 sentences).\n"
            "Only introduce the technique listed below if response_task is offer_one_technique, continue_active_technique, or crisis_support AND needs_technique=true.\n"
            "If the thread is still in early exploration, the user is answering a follow-up, or needs_technique=false, postpone the technique and ask ONE focused follow-up instead.\n"
            "Do NOT re-introduce a technique if the user is already doing it or has just agreed to it.\n"
            "Use language like: 'I'd like to share something that might help...'\n"
            "After introducing it, invite them: 'Would you like to give it a try?'"
        ),
        "distract": (
            "STRATEGY  POSITIVE REDIRECTION:\n"
            "Acknowledge briefly, then gently redirect to something lighter or positive.\n"
            "Keep it warm and never dismissive."
        ),
    }
    strategy_desc = strategy_instructions.get(strategy, strategy_instructions["validate_only"])

    #  TREND CONTEXT 
    trend_desc = {
        "improving":  " TREND: The user's emotional state has been IMPROVING  affirm their progress.",
        "worsening":  " TREND: The user's emotional state is WORSENING  show extra care and urgency. Don't minimize.",
        "stable":     "",
    }.get(trend, "")

    #  CBT DISTORTION 
    distortion_desc = ""
    if distortion_type:
        distortion_map = {
            "catastrophizing":    "User is catastrophizing. Model conditional language: 'sometimes'/'right now' instead of 'always'/'never'.",
            "black_white":        "User is thinking in extremes. Gently surface the nuanced middle ground.",
            "overgeneralization": "User is over-generalizing. Help them see this as one event, not a permanent pattern.",
            "mind_reading":       "User is assuming they know what others think. Gently question the certainty.",
            "personalization":    "User is taking on blame that isn't theirs. Help separate their responsibility from others'.",
            "should_statements":  "User uses rigid 'should/must'. Model flexible 'could/might' alternatives.",
            "emotional_reasoning":"User treats feelings as facts. Gently distinguish emotion from objective reality.",
            "magnification":      "User is magnifying the difficulty. Offer proportionate perspective without dismissing real pain.",
        }
        instruction = distortion_map.get(distortion_type, "")
        if instruction:
            distortion_desc = (
                f"\n\nCBT INSIGHT: {instruction}\n"
                " Maintain clinical empathy even if role is 'friend'. Never sound dismissive."
            )

    #  ABSOLUTE HARD RULES 
    hard_rules = """
ABSOLUTE RULES  NEVER VIOLATE THESE:
1.  NEVER suggest a technique if the user has explicitly said they don't want exercises, "I just want to talk", "I don't want to do exercises", or similar.
2.  NEVER re-suggest the SAME technique the user just said didn't help. Always offer a DIFFERENT approach.
3.  NEVER invent past conversations or memories. If you don't have memory context, just respond to now.
4.  NEVER give medical diagnoses, prescribe medication, or make clinical labels (e.g., "You have anxiety disorder").
5.  NEVER ask more than ONE question at a time.
6.  NEVER be preachy, lecture, or repeat the same advice multiple times.
7.  NEVER dismiss positive news with unsolicited therapy (e.g., if the user says "I got the job!", just celebrate with them).
8.  If the user seems angry at you or says "you're not helping", validate their frustration honestly and ask what would actually help them right now.
9.  If the user sends a very short reply ("ok", "yes", "no", "maybe"), treat it as a cue to reflect or gently ask a follow-up  don't over-explain.
10.  If the user mentions clinical symptoms (poor sleep, appetite changes, concentration issues, persistent hopelessness for weeks), acknowledge gently and ask if they've spoken to anyone  but never diagnose.
11.  If the user says a technique HELPED, celebrate it warmly and encourage them to keep using it.
12.  Use the user's name if you know it (from memory context). It makes the conversation feel personal.
13.  Resolve short answers and pronouns from the current session before replying. If the user says "about 3 weeks", "maths", "that", or "it", treat it as part of the active thread, not a standalone topic.
14.  Do NOT offer a technique on the first distress disclosure unless the user accepts a technique already offered.
15.  A request like "help me", "what should I do", "can you suggest something", or "any advice" is not enough by itself. First ask one focused follow-up unless the thread already contains a concrete formulation.
16.  When needs_technique=false, no new technique language is allowed: no "I can suggest", no "we could try", no coping lists, and no therapy homework. Only mention an existing stored technique for memory queries, acceptance/rejection, or positive feedback.
17.  If the user says they have no more details ("nothing else", "I shared everything", "that's all"), do not ask another exploratory context question. Use what is already known.
18.  Do not reuse the same empathy opener in adjacent replies. If the last assistant reply said "that sounds really heavy/painful", start differently.
19.  Never claim to be a licensed therapist, doctor, emergency responder, or substitute for professional care.
20.  Keep crisis replies plain, direct, and safety-focused. Do not add decorative language.
21.  When a candidate shortlist is present, choose exactly one listed candidate id and use only that selected technique. Otherwise, when a recommended or active technique is present, use only that exact technique name. Never invent, rename, list, or switch to a technique outside the provided data.
22.  If the user accepted a technique, acknowledge consent, name the selected technique once, explain why it fits the exact issue, then begin the first step.
23.  Do not treat "thanks", "thank you", "ok thanks", or "thanks for it" as technique acceptance or improvement feedback. Only say a technique helped if the user explicitly says helped, worked, calmer, better, or similar.
24.  If the response task is acknowledge_and_pause, reply briefly and naturally; do not analyze, offer a technique, or mark it as progress.
"""

    continuity_rules = """
IN-SESSION CONTINUITY:
- Read the recent session thread as the primary context for this reply.
- Treat the current message as the next turn in the same conversation, not as a fresh chat, unless the user clearly changes topic.
- Short replies usually answer your last question. Connect them back to the user's original concern.
- Pronouns like "it", "that", "this", and "what do you think about it" usually refer to the whole active concern, unless the immediately previous turn clearly discussed a specific technique.
- If the user asks for your view, answer using the full thread: concern, duration, trigger, impact, body feeling, belief, and the latest answer.
- Keep the central thread alive across turns. Do not reset to generic advice just because the latest message is brief.
- If the user says they are "not good", "not okay", or "currently" struggling, treat that as a worsening of the active thread, not a new opening disclosure.
- If the user says they have already shared everything, treat the context-gathering step as complete. Summarize the known concern and move to the planned next step.
- Use the already gathered pattern. For example: if they described shutdown, guilt, tiredness, chest tightness, or small things piling up, reflect that pattern explicitly before asking anything.
- Avoid repeating stock validation phrases like "it takes courage" or "your feelings are valid" in every turn.
- Avoid back-to-back "That sounds..." openings. Vary empathy naturally: "I can see why...", "That must feel...", "I'm sorry you're carrying...", "It makes sense that..."
- For loneliness or isolation, sound especially human and relational. Do not rush to an exercise; first understand when the loneliness hits, what connection they are missing, and what kind of support would feel less alone.
"""

    technique_pacing_rules = """
TECHNIQUE PACING:
- A recommended technique is a candidate, not a command.
- Follow-up questions come before therapy or technique offers. The user must feel understood first.
- Before suggesting a technique, gather a concrete formulation: concern plus at least one detail such as duration, trigger, subject, situation, body feeling, impact, or belief.
- If the current turn is still an early disclosure or a short answer to your follow-up question, do not suggest a technique yet. Validate and ask one focused follow-up instead.
- Loneliness needs slower pacing than exam stress or acute anxiety. If the user has only shared loneliness once or twice, offer warmth and one gentle exploration question before any technique.
- Stop context gathering when the planner marks context_complete/no_more_details/followup_limit_reached. At that point, do not ask "is there anything else?"
- Suggest a technique only when strategy is SUGGEST_TECHNIQUE, response_task permits it, needs_technique=true, and the thread has enough context, or when the user accepts a previous offer.
"""

    stage_rules = f"""
STAGE MACHINE:
- Current stage: {conversation_stage}
- Current intent: {current_intent or "unknown"}
- needs_technique: {str(needs_technique).lower()}
- response_task: {response_task}
- DISCOVERY/UNDERSTANDING: validate and ask exactly one relevant context question. No techniques.
- INTERVENTION: introduce exactly one listed technique only when needs_technique=true and response_task is offer_one_technique.
- FOLLOW_UP: continue, discuss, recall, accept, or reject the previous technique. Do not introduce a new technique during rejection or memory queries.
- RECOVERY: reinforce progress and ask what changed or what helped. Do not introduce a new technique unless explicitly requested.
- asking_opinion: give a thoughtful interpretation of the active concern; do not offer a technique.
- memory_query: answer directly from the latest/preferred/rejected technique fields; if missing, say you do not have the exact name.
- reject_technique: validate dissatisfaction and ask what felt unhelpful; do not suggest a replacement yet.
- technique_preference_update: acknowledge the preference and use it for the next step.
- positive_feedback: acknowledge progress warmly and do not treat it as a new exercise request.
- acknowledge_and_pause: answer the acknowledgement warmly and briefly; do not infer consent, improvement, or a new topic.
- context_complete/no_more_details/followup_limit_reached: stop asking for more background. Use the known formulation and follow response_task.
- If needs_technique=false, never mention, offer, hint at, or name a technique.
"""

    # Dynamic distortion reframing hints for give_reflective_opinion
    reframe_hint = ""
    if distortion_type:
        dt_lower = str(distortion_type).lower()
        if "catastrophiz" in dt_lower:
            reframe_hint = "Address catastrophizing: gently explore probability and coping ability. (e.g. 'It sounds like your mind is jumping to the worst possible outcome. Maybe we can slow that down and look at what is most likely, not only what is most frightening.')"
        elif "mind-read" in dt_lower or "mind read" in dt_lower:
            reframe_hint = "Address mind-reading: separate assumption from evidence. (e.g. 'It's natural to try to guess what others are thinking, but sometimes our minds fill in the blanks with our own worries. What actual evidence do you have for that assumption?')"
        elif "should" in dt_lower:
            reframe_hint = "Address should-statements: soften rigid self-pressure and introduce self-compassion. (e.g. 'You're holding yourself to a very high standard. What if we softened that \"should\" into \"I would prefer to\" or \"It's okay if I can't do it all right now\"?')"
        elif any(kw in dt_lower for kw in ("all-or-nothing", "all or nothing", "black-and-white", "black and white")):
            reframe_hint = "Address all-or-nothing thinking: introduce middle-ground thinking. (e.g. 'It can feel like everything is either perfect or a failure, but most of life happens in the gray area. Can we look for a middle ground or a partial success here?')"
        elif "overgeneral" in dt_lower:
            reframe_hint = "Address overgeneralization: focus on this single event rather than a permanent pattern. (e.g. 'It feels like this one setback means it will always be this way. But this is just one moment, not the final word on your future.')"
        elif "personaliz" in dt_lower:
            reframe_hint = "Address personalization: gently challenge taking sole responsibility for external outcomes. (e.g. 'It's heavy to carry the blame for how this turned out. But there are many factors outside of your control that contributed to this.')"

    if reframe_hint:
        give_reflective_opinion_rule = (
            "RESPONSE TASK - GIVE REFLECTIVE OPINION:\n"
            f"Ground your advice in addressing the user's detected thinking pattern: {reframe_hint}.\n"
            "CRITICAL THERAPEUTIC RULES:\n"
            "  • NEVER expose the clinical name of the distortion to the user (e.g., NEVER say 'You are catastrophizing' or 'This is mind-reading').\n"
            "  • Integrate the cognitive reframe naturally, and do not offer or mention any structured coping technique.\n"
            "  • Keep it conversational, warm, and supportive."
        )
    else:
        give_reflective_opinion_rule = (
            "RESPONSE TASK - GIVE REFLECTIVE OPINION:\n"
            "Answer what you think about the active concern. Summarize the pattern and offer a grounded interpretation. "
            "Do not ask another exploratory question unless absolutely necessary. Do not mention a technique."
        )

    response_task_rules = {
        "ask_next_context_question": (
            "RESPONSE TASK - ASK NEXT CONTEXT QUESTION:\n"
            "Reflect the active thread, then ask exactly one focused question based on the missing detail. "
            "Do not restart with broad questions like 'what has been going on?' Do not mention any technique."
        ),
        "give_reflective_opinion": give_reflective_opinion_rule,
        "summarize_known_context": (
            "RESPONSE TASK - SUMMARIZE KNOWN CONTEXT:\n"
            "The user has indicated there are no more details to add. Briefly summarize the active concern using exact known details. "
            "Do not ask another exploratory question. If needs_technique=false, end with a supportive next step without naming a technique."
        ),
        "offer_one_technique": (
            "RESPONSE TASK - OFFER ONE TECHNIQUE:\n"
            "Use the known formulation to explain why the listed technique fits. Name exactly one listed technique. "
            "Tie the rationale to the user's exact issue (for example bedtime exam rumination, fear of failure, or a specific catastrophic thought). "
            "Ask consent to try it together. Do not list multiple options, and do not mention techniques that were not selected."
        ),
        "continue_active_technique": (
            "RESPONSE TASK - CONTINUE ACTIVE TECHNIQUE:\n"
            "The user accepted the previously offered technique. Continue that same technique. "
            "Acknowledge consent, name only the selected technique, explain why it fits this specific concern, and invite the first step. "
            "Do not switch to a new one or repeat the offer as if they have not accepted."
        ),
        "handle_technique_rejection": (
            "RESPONSE TASK - HANDLE REJECTION:\n"
            "Acknowledge that the technique did not fit. Do not defend it or offer a replacement yet. "
            "Ask what felt unhelpful so the next support can adapt."
        ),
        "record_preference": (
            "RESPONSE TASK - RECORD PREFERENCE:\n"
            "Acknowledge the preference and connect it to the user's next step. Do not push a new technique."
        ),
        "answer_memory_query": (
            "RESPONSE TASK - ANSWER MEMORY QUERY:\n"
            "Answer directly from stored technique/context fields. Do not turn this into therapy or a new exercise offer."
        ),
        "positive_feedback": (
            "RESPONSE TASK - POSITIVE FEEDBACK:\n"
            "Warmly acknowledge what helped, name the active technique only if it is stored, and ask one gentle follow-up about what changed. "
            "Do not suggest a new technique."
        ),
        "acknowledge_and_pause": (
            "RESPONSE TASK - ACKNOWLEDGE AND PAUSE:\n"
            "The user gave a polite acknowledgement or low-signal affirmation. "
            "Respond in 1-2 short sentences. Do not infer that an exercise was accepted or helped. "
            "Do not suggest, name, or hint at a technique."
        ),
        "ask_permission_before_technique": (
            "RESPONSE TASK - ASK PERMISSION:\n"
            "You have a potentially helpful technique to share. "
            "If the user added more detail after a previous technique offer, briefly acknowledge that detail and then ask permission again from the same formulation. "
            "Before sharing it, ask the user if they would like you to share it. "
            "Do NOT name the technique yet. Do NOT describe it yet. Just ask permission."
        ),
    }
    response_task_desc = response_task_rules.get(response_task, response_task_rules["ask_next_context_question"])

    base_prompt = f"""You are SentiMind, a compassionate AI mental health companion. You are warm, non-judgmental, and clinically aware.


ROLE: {agent_role.upper()}
{role_desc}

SITUATION:
- Detected emotion: {emotion.upper()} at {intensity:.0%} intensity
- Conversation phase: {phase.upper()}
- Emotional trend: {trend.upper()}
{trend_desc}
{technique_desc}
{masking_block}

WHAT TO DO NOW:
{strategy_desc}
{distortion_desc}

{continuity_rules}
{technique_pacing_rules}
{stage_rules}
{response_task_desc}

RESPONSE FORMAT:
- 2-4 paragraphs, 80-200 words total
- Warm, empathetic, natural language
- Prefer plain human language over clinical phrasing. Sound like a steady companion, not a worksheet.
- Do not repeat the same emotional adjective from your previous reply unless the user repeats it first.
- No emojis unless the user clearly uses them first; never use emojis in crisis replies.
- No medical jargon or clinical labels
- End according to response_task. Do not force a question when response_task is give_reflective_opinion or answer_memory_query.

MEMORY RULE:
If past session memories are provided below, use them only to personalize naturally.
Do NOT open with "I remember you said..."  just weave the context in.
If there are no memories, respond to what the user is sharing right now.

{hard_rules}"""

    # v9.0: CLINICAL SEVERITY GUIDANCE — append after base prompt
    if clinical_severity and clinical_severity != "minimal":
        _clinical_map = {
            "mild": "\nCLINICAL NOTE: User shows MILD clinical indicators. Continue supportive care. Monitor for escalation.",
            "moderate": "\nCLINICAL NOTE: User shows MODERATE clinical indicators. Prioritize structured techniques. Gently mention professional support is available.",
            "moderately_severe": "\nCLINICAL NOTE: User shows MODERATELY SEVERE clinical indicators. Strongly recommend professional support alongside any technique. Be extra present and validating.",
            "severe": "\nSAFETY NOTE: User shows SEVERE clinical indicators. Deep validation is priority. Encourage professional help warmly. Do NOT dismiss their experience. If suicidal ideation is flagged, follow crisis protocol.",
        }
        base_prompt += _clinical_map.get(clinical_severity, "")

    # v11.0: Append consent override block (injected with highest priority)
    if consent_override_block:
        base_prompt += consent_override_block
    if suppression_block:
        base_prompt += suppression_block

    return base_prompt



def _build_clinical_context_block(
    severity: str = "minimal",
    phq9: int = 0,
    gad7: int = 0,
    indicators: list = None,
) -> str:
    """Build a structured clinical severity context block for the LLM."""
    indicators = indicators or []
    if severity == "minimal" and phq9 == 0 and gad7 == 0:
        return ""  # No clinical info to inject

    indicator_str = ", ".join(indicators) if indicators else "none"
    severity_label = severity.upper().replace("_", " ")

    return f"""CLINICAL SEVERITY ASSESSMENT (PHQ-9/GAD-7):
- Estimated Severity: {severity_label}
- PHQ-9 Score: {phq9}/27  |  GAD-7 Score: {gad7}/21
- Active Indicators: {indicator_str}
NOTE: Adapt response depth and urgency based on severity level."""


def _build_structured_context(
    emotion: str,
    intensity: float,
    sentiment: str,
    technique: dict,
    agent_role: str,
    is_new_user: bool,
    user_message: str,
    primary_sub_emotion: str = "",
    secondary_sub_emotions: list | None = None,
    detected_symptoms: list | None = None,
    detected_behaviors: list | None = None,
    detected_contexts: list | None = None,
    strategy: str = "validate_only",
    trend: str = "stable",
    phase: str = "venting",
    distortion_type: str | None = None,
    distortion_explanation: str | None = None,
    micro_action: str | None = None,
    proactive_alert: str | None = None,
    psych_profile: dict | None = None,
    memory_context: str = "",
    voice_features: dict | None = None,
    voice_processed: bool = False,
    text_emotion_raw: str = "neutral",
    clinical_severity: str = "minimal",
    clinical_phq9: int = 0,
    clinical_gad7: int = 0,
    clinical_indicators: list = None,
    conversation_stage: str = "DISCOVERY",
    current_intent: str = "",
    needs_technique: bool = False,
    technique_candidates: list[dict] | None = None,
    primary_concern: str | None = None,
    concern_duration: str | None = None,
    triggering_subject: str | None = None,
    triggering_context: str | None = None,
    functional_impact: str | None = None,
    core_belief: str | None = None,
    latest_recommended_technique: dict | None = None,
    latest_rejected_technique: dict | None = None,
    preferred_techniques: list | None = None,
    response_task: str = "ask_next_context_question",
    active_thread_summary: str | None = None,
    last_assistant_question: str | None = None,
    expected_answer_type: str | None = None,
    # v11.0: consent governance
    exercise_consent: str = "unknown",
    suppressed_topics: list | None = None,
    active_issue_source: str | None = None,
    solution_preference: str = "unknown",
) -> str:
    """
    Build structured context for LLM prompt.
    Now includes strategy, trend, phase, distortion, micro-action, and proactive hint.
    """
    
    candidates = _valid_technique_candidates(technique_candidates)
    technique_info = ""
    if needs_technique and candidates and response_task in {"offer_one_technique", "ask_permission_before_technique"}:
        technique_info = f"""
TECHNIQUE CANDIDATE SHORTLIST:
Select exactly one candidate by id. These are safe DB exercises already narrowed by semantic search.
{_format_technique_candidates(candidates)}"""
    elif needs_technique and technique:
        technique_info = f"""
RECOMMENDED TECHNIQUE:
- Name: {technique.get('name', 'Unknown')}
- Category: {technique.get('category', 'Unknown')}
- Duration: {technique.get('duration_minutes', 'N/A')} minutes
- Difficulty: {technique.get('difficulty', 'N/A')}
- Why it works: {technique.get('why_it_works', 'N/A')}"""
    elif not needs_technique:
        withheld_reason = "withheld because the current response must understand first and ask a follow-up."
        if response_task == "summarize_known_context":
            withheld_reason = "withheld because this response should summarize the known context without another exploratory question."
        technique_info = """
RECOMMENDED TECHNIQUE:
- {withheld_reason}""".format(withheld_reason=withheld_reason)
    
    # Strategy-specific task instructions
    # For reframe: dynamically name the exact distortion so the LLM is surgically precise
    _distortion_label = distortion_type.replace("_", " ") if distortion_type else "unhelpful thinking"
    _distortion_reframe_hints = {
        "catastrophizing":     f"gently replace absolute language ('always'/'never') with conditional alternatives ('sometimes'/'right now')",
        "black_white":         f"help them find the nuanced middle ground between the two extremes",
        "overgeneralization":  f"help them see this as one isolated event, not a universal pattern about themselves",
        "mind_reading":        f"gently question whether they can actually know what the other person is thinking",
        "personalization":     f"help them separate what is genuinely within their control vs. what is not",
        "should_statements":   f"soften rigid 'should/must' language into flexible 'could/might' alternatives",
        "emotional_reasoning": f"gently distinguish between how something feels and what is objectively true",
        "magnification":       f"offer a proportionate perspective  acknowledge the difficulty without amplifying it",
    }
    _reframe_hint = _distortion_reframe_hints.get(distortion_type or "", "help them see their situation from a new, more constructive angle")

    strategy_tasks = {
        "validate_only": "1. Acknowledge their emotion in fresh, plain language\n2. Validate their feelings without repeating the previous assistant wording\n3. Show you're listening and present\n4. Do NOT suggest any technique",
        "ask_question": "1. Acknowledge their emotion in fresh, plain language\n2. Validate briefly without repeating the previous assistant wording\n3. Ask ONE thoughtful open-ended question\n4. For loneliness/isolation, explore the missing connection before any technique\n5. Do NOT suggest, name, hint at, or prepare any technique yet",
        "encourage_reflection": "1. Celebrate or validate that the user is actively practicing a technique or reflecting\n2. Ask a gentle question about their experience with it (e.g., 'What does it feel like in your body?')\n3. Encourage them to keep going or share what they notice\n4. Do NOT suggest a new technique  they are already practicing",
        "reframe": (
            f"1. Acknowledge their emotion warmly\n"
            f"2. Notice (without labelling clinically) that their language reflects {_distortion_label}\n"
            f"3. {_reframe_hint.capitalize()}\n"
            f"4. End with an open question or supportive next step"
        ),
        "suggest_technique": (
            "1. Acknowledge their emotion\n"
            "2. Validate their feelings\n"
            "3. Introduce the technique only if needs_technique is true and the response task permits it\n"
            "4. If this is still an early disclosure, a short answer, or needs_technique is false, postpone the technique and ask ONE focused follow-up\n"
            "5. Offer supportive next step"
        ),
        "distract": "1. Acknowledge briefly\n2. Redirect to something positive\n3. Keep it light and warm",
    }
    task_text = strategy_tasks.get(strategy, strategy_tasks["validate_only"])
    _dialogue_reframe_hint = ""
    if distortion_type:
        dt_lower = str(distortion_type).lower()
        if "catastrophiz" in dt_lower:
            _dialogue_reframe_hint = "gently explore probability and coping ability (e.g. 'It sounds like your mind is jumping to the worst possible outcome. Maybe we can slow that down and look at what is most likely, not only what is most frightening.')"
        elif "mind-read" in dt_lower or "mind read" in dt_lower:
            _dialogue_reframe_hint = "separate assumption from evidence (e.g. 'It's natural to try to guess what others are thinking, but sometimes our minds fill in the blanks with our own worries. What actual evidence do you have for that assumption?')"
        elif "should" in dt_lower:
            _dialogue_reframe_hint = "soften rigid self-pressure and introduce self-compassion (e.g. 'You're holding yourself to a very high standard. What if we softened that \"should\" into \"I would prefer to\" or \"It's okay if I can't do it all right now\"?')"
        elif any(kw in dt_lower for kw in ("all-or-nothing", "all or nothing", "black-and-white", "black and white")):
            _dialogue_reframe_hint = "introduce middle-ground thinking (e.g. 'It can feel like everything is either perfect or a failure, but most of life happens in the gray area. Can we look for a middle ground or a partial success here?')"
        elif "overgeneral" in dt_lower:
            _dialogue_reframe_hint = "focus on this single event rather than a permanent pattern (e.g. 'It feels like this one setback means it will always be this way. But this is just one moment, not the final word on your future.')"
        elif "personaliz" in dt_lower:
            _dialogue_reframe_hint = "gently challenge taking sole responsibility for external outcomes (e.g. 'It's heavy to carry the blame for how this turned out. But there are many factors outside of your control that contributed to this.')"

    if _dialogue_reframe_hint:
        _give_opinion_task = (
            "1. Answer the user's request for your view directly\n"
            "2. Summarize the active thread and what it seems to mean\n"
            f"3. Ground your advice in addressing their thinking pattern: {_dialogue_reframe_hint}\n"
            "4. NEVER expose the clinical name of the distortion to the user\n"
            "5. Do not ask another exploratory question or offer any structured technique"
        )
    else:
        _give_opinion_task = (
            "1. Answer the user's request for your view directly\n"
            "2. Summarize the active thread and what it seems to mean\n"
            "3. Do not ask another exploratory question\n"
            "4. Do not mention any technique"
        )

    response_task_tasks = {
        "ask_next_context_question": (
            "1. Use the active thread before asking\n"
            "2. Ask exactly one focused next question\n"
            "3. If the active thread is loneliness/isolation, ask about when it hits or what kind of connection feels missing\n"
            "4. Do not suggest, name, hint at, or prepare a technique"
        ),
        "give_reflective_opinion": _give_opinion_task,
        "summarize_known_context": (
            "1. Acknowledge that you have enough context for now\n"
            "2. Summarize the active thread using exact known details\n"
            "3. Do not ask another exploratory question\n"
            "4. If needs_technique is false, end with a supportive next step without naming a technique"
        ),
        "offer_one_technique": (
            "1. Summarize the formulation briefly\n"
            "2. Introduce exactly one listed technique\n"
            "3. Explain why it fits this specific thread, such as bedtime exam rumination or a scary failure belief\n"
            "4. Ask if they would like to try it together\n"
            "5. Do not mention unselected techniques"
        ),
        "continue_active_technique": (
            "1. Acknowledge the user's consent\n"
            "2. Continue the same technique already offered and use only its exact name\n"
            "3. Explain why it fits this specific issue\n"
            "4. Begin the first step\n"
            "5. Do not recommend a different technique or repeat the offer as if the user has not accepted"
        ),
        "handle_technique_rejection": (
            "1. Acknowledge the technique did not fit\n"
            "2. Ask what felt unhelpful\n"
            "3. Do not suggest a replacement yet"
        ),
        "record_preference": (
            "1. Acknowledge the preference\n"
            "2. Connect it to the active thread or next step\n"
            "3. Do not introduce a new technique"
        ),
        "answer_memory_query": "1. Answer directly from stored context\n2. Do not ask a therapy follow-up",
        "positive_feedback": "1. Acknowledge what helped\n2. Mention the active technique only if known\n3. Ask one gentle question about what changed\n4. Do not suggest a new technique",
        "acknowledge_and_pause": "1. Reply warmly and briefly\n2. Do not infer technique acceptance, outcome improvement, or a new emotional state\n3. Do not suggest a technique",
        # v11.0: consent-aware response tasks
        "listen_only": (
            "RESPONSE TASK - LISTEN ONLY:\n"
            "Acknowledge warmly. Do NOT offer any technique, exercise, or advice. "
            "Reflect what the user said with empathy. "
            "End with a gentle, open-ended question or a simple validating statement."
        ),
        "ask_permission_before_technique": (
            "RESPONSE TASK - ASK PERMISSION:\n"
            "You have a potentially helpful technique to share. "
            "If the user added more detail after a previous technique offer, briefly acknowledge that detail and then ask permission again from the same formulation. "
            "Before sharing it, ask the user if they would like you to share it. "
            "Say something like: 'I have something that might help — would you like me to share it?' "
            "Do NOT name the technique yet. Do NOT describe it yet. Just ask permission."
        ),

    }
    if response_task in response_task_tasks:
        task_text = response_task_tasks[response_task]
    
    # Cognitive distortion context [v3 NEW]
    distortion_info = ""
    if distortion_type and distortion_explanation:
        distortion_info = f"""
\nCOGNITIVE PATTERN DETECTED:
- Type: {distortion_type.replace('_', ' ').title()}
- Note: {distortion_explanation}"""

    # Behavioral micro-action [v3 NEW]
    micro_action_info = ""
    if micro_action:
        micro_action_info = f"""
\nMICRO-ACTION AVAILABLE (optional, weave in naturally if appropriate):
- Action: {micro_action}"""

    # Proactive alert hint [v3 NEW]
    proactive_info = ""
    if proactive_alert:
        proactive_info = f"""
\nPROACTIVE CONTEXT: {proactive_alert}"""

    # Psych profile summary [v3 NEW]
    profile_info = ""
    if psych_profile:
        coping = psych_profile.get('coping_style', '')
        resilience = psych_profile.get('resilience_score', 0.5)
        if coping:
            profile_info = f"""
\nUSER PROFILE SUMMARY:
- Coping style: {coping}
- Resilience level: {'High' if resilience > 0.65 else 'Medium' if resilience > 0.35 else 'Low'}"""

    latest_name = (latest_recommended_technique or {}).get("name", "") if isinstance(latest_recommended_technique, dict) else ""
    rejected_name = (latest_rejected_technique or {}).get("name", "") if isinstance(latest_rejected_technique, dict) else ""
    preferred_names = [
        p.get("name", "")
        for p in (preferred_techniques or [])
        if isinstance(p, dict) and p.get("name")
    ]
    formulation_info = f"""
\nTHERAPEUTIC FORMULATION:
- Stage: {conversation_stage}
- Intent: {current_intent or 'unknown'}
- Response task: {response_task}
- Needs technique now: {needs_technique}
- Primary concern: {primary_concern or 'unknown'}
- Active thread summary: {active_thread_summary or 'unknown'}
- Duration: {concern_duration or 'unknown'}
- Triggering subject: {triggering_subject or 'unknown'}
- Triggering context: {triggering_context or 'unknown'}
- Functional impact: {functional_impact or 'unknown'}
- Core belief: {core_belief or 'unknown'}
- Last assistant question: {last_assistant_question or 'none'}
- Expected answer type: {expected_answer_type or 'none'}
- Latest recommended technique: {latest_name or 'none'}
- Latest rejected technique: {rejected_name or 'none'}
- Preferred techniques: {', '.join(preferred_names) if preferred_names else 'none'}
- Exercise consent: {exercise_consent}
- Solution preference: {solution_preference}
- Suppressed topics: {", ".join([t.get("topic","") for t in (suppressed_topics or []) if t.get("topic")]) or "none"}
- Active issue source: {active_issue_source or "not specified"}"""

    # Cross-session memory context summarized for prompt use
    memory_info = ""
    if memory_context and memory_context.strip():
        memory_info = f"""
\nPAST SESSION MEMORIES (use to personalize, do not quote directly):
{memory_context[:600]}"""  # Cap at 600 chars to stay within token budget

    #  VOICE ACOUSTIC CONTEXT [new] 
    # Inject psychoacoustic signals so the LLM adapts tone, depth, and urgency.
    voice_context = ""
    if voice_processed and voice_features:
        distress_idx   = float(voice_features.get("distress_index", 0.0))
        arousal_val    = float(voice_features.get("arousal", 0.5))
        pause_val      = float(voice_features.get("pause_density", 0.25))
        voice_emotion  = voice_features.get("emotion", "neutral")
        voice_conf     = float(voice_features.get("confidence", 0.0))
        conflict       = voice_emotion != text_emotion_raw

        distress_label = (
            " HIGH  user may be masking their true emotional state"
            if distress_idx > 0.60 else
            " MODERATE  some vocal tension present"
            if distress_idx > 0.35 else
            " LOW  voice sounds relaxed"
        )
        arousal_label  = "elevated" if arousal_val > 0.65 else "normal"
        pause_label    = "hesitant/slow speech" if pause_val > 0.35 else "fluent speech"
        conflict_label = (
            " MISALIGNMENT  voice and text express different emotions. "
            "The user may be downplaying how they truly feel."
            if conflict else
            " aligned  voice and text agree"
        )

        voice_context = f"""
\n VOICE ACOUSTIC ANALYSIS (raw microphone signal  NOT text):
- Voice emotion detected: {voice_emotion.upper()} (confidence: {voice_conf:.0%})
- Psychoacoustic distress index: {distress_idx:.2f}  {distress_label}
- Arousal level: {arousal_val:.0%} ({arousal_label})
- Pause density: {pause_val:.2f} ({pause_label})
- Voice vs. text alignment: {conflict_label}

INSTRUCTION: Let these acoustic signals guide your TONE:
 If distress_index > 0.6  be extra gentle even if the text seems calm
 If voice/text conflict  gently invite the user to share more (don't confront directly)
 If pause_density > 0.4  the user may be finding it hard to speak; give them space
"""

    return f"""STRUCTURED ANALYSIS:

{memory_info}
{voice_context}
USER MESSAGE:
"{user_message}"

EMOTION ANALYSIS:
- Primary Emotion: {emotion.upper()}
- Primary Sub-Emotion: {(primary_sub_emotion or 'unknown').upper()}
- Secondary Sub-Emotions: {', '.join(secondary_sub_emotions or []) if secondary_sub_emotions else 'none'}
- Detected Symptoms: {', '.join(detected_symptoms or []) if detected_symptoms else 'none'}
- Detected Behaviors: {', '.join(detected_behaviors or []) if detected_behaviors else 'none'}
- Detected Contexts: {', '.join(detected_contexts or []) if detected_contexts else 'none'}
- Sentiment: {sentiment.upper()}
- Intensity Level: {intensity:.0%}
- Emotional State: {'Highly distressed' if intensity > 0.7 else 'Moderately concerned' if intensity > 0.4 else 'Mild concern'}
- Emotional Trend: {trend.upper()}
- Conversation Phase: {phase.upper()}
{distortion_info}
{profile_info}
{formulation_info}

{_build_clinical_context_block(clinical_severity, clinical_phq9, clinical_gad7, clinical_indicators or [])}

USER CONTEXT:
- New User: {is_new_user}
- Agent Role for This Response: {agent_role.upper()}
- Strategy: {strategy.upper()}
{technique_info}
{micro_action_info}
{proactive_info}

STRATEGY TO EXECUTE:
{task_text}
    """.strip()


# ============================================
# STREAMING SUPPORT (v5.3 LATENCY OPTIMIZATION)
# ============================================

async def stream_response_tokens(llm, llm_messages) -> AsyncIterator[str]:
    """
    Stream LLM response token-by-token using Groq's streaming API.
    
    Yields:
        Individual tokens from the LLM as they arrive.
    
    This allows the client to display text incrementally instead of waiting
    for the full response to generate (saves perceived latency by 1-3 seconds).
    """
    try:
        prefix_buffer = ""
        prefix_checked = False

        # Use astream instead of ainvoke to get token-by-token output
        async for chunk in llm.astream(llm_messages):
            token_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if token_content:
                if not prefix_checked:
                    prefix_buffer += token_content
                    cleaned = _strip_response_metadata_prefix(prefix_buffer)
                    if cleaned != prefix_buffer or "\n" in prefix_buffer or len(prefix_buffer) >= 24:
                        prefix_checked = True
                        if cleaned:
                            yield cleaned
                    continue
                yield token_content
        if not prefix_checked:
            cleaned = _strip_response_metadata_prefix(prefix_buffer)
            if cleaned and not re.fullmatch(r"\s*(?:0|1(?:\.0)?|0\.\d+)\s*", cleaned):
                yield cleaned
    except Exception as e:
        print(f"[STREAM]  Streaming error: {e}")
        yield f"\n\n[Error streaming response: {str(e)[:50]}]"


async def optimized_response_generator_node_streaming(state: MentalHealthState):
    """
    STREAMING VARIANT - Returns an async generator instead of blocking.
    
    Use this when you need to stream tokens to the client via SSE/WebSocket.
    Returns a tuple of (async_generator, state_updates) so the graph can
    continue while tokens are being streamed.
    
    This is called by the /chat/stream endpoint INSTEAD OF optimized_response_generator_node.
    """
    try:
        # Guard: Don't overwrite crisis response
        if state.get("crisis_detected") and state.get("final_response"):
            print("[RESPONSE]  Crisis response already set (streaming)")
            # For crisis, return pre-computed response (no streaming) because safety is paramount
            async def _crisis_gen():
                yield state.get("final_response", "")
            return _crisis_gen(), {"final_response_streamed": True}
        
        # Extract structured data (same as non-streaming)
        emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        intensity = state.get("fused_intensity", state.get("intensity", 0.5))
        sentiment = state.get("sentiment", "neutral")
        primary_sub_emotion = state.get("primary_sub_emotion") or ""
        secondary_sub_emotions = state.get("secondary_sub_emotions") or []
        detected_symptoms = state.get("detected_symptoms") or []
        detected_behaviors = state.get("detected_behaviors") or []
        detected_contexts = state.get("detected_contexts") or []
        recommended_technique = state.get("recommended_technique", {})
        agent_role = state.get("agent_role", "coach")
        messages = state.get("messages", [])
        is_new_user = state.get("is_new_user", False)
        crisis_detected = state.get("crisis_detected", False)
        
        conversation_strategy = state.get("conversation_strategy", "validate_only")
        emotional_trend = state.get("emotional_trend", "stable")
        conversation_phase = state.get("conversation_phase", "venting")
        distortion_type = state.get("distortion_type")
        distortion_explanation = state.get("distortion_explanation")
        micro_action = state.get("micro_action")
        proactive_alert = state.get("proactive_alert")
        psych_profile = state.get("psych_profile", {})
        clinical_severity = state.get("clinical_severity", "minimal")
        conversation_stage = state.get("conversation_stage", "DISCOVERY")
        current_intent = state.get("intent", "")
        needs_technique = state.get("needs_technique", False)
        response_task = state.get("response_task", "ask_next_context_question")
        latest_recommended_technique = state.get("latest_recommended_technique") or {}
        latest_rejected_technique = state.get("latest_rejected_technique") or {}
        preferred_techniques = state.get("preferred_techniques", []) or []
        if not needs_technique and current_intent != "accept_technique":
            recommended_technique = {}

        # Voice acoustic context (streaming path)
        voice_features  = state.get("voice_features") or {}
        voice_processed = state.get("voice_processed", False)

        user_message = messages[-1].content if messages else ""
        recent_history = _select_prompt_history(messages)
        memory_context = state.get("memory_context", "")
        
        print(f"[NODE:RESPONSE-STREAM]  Streaming | Role: {agent_role} | Emotion: {emotion} ({intensity:.0%}) | Strategy: {conversation_strategy}")
        
        llm = get_chat_llm()
        
        # FAST PATH: no_action (casual chitchat)  don't stream, too fast
        if conversation_strategy == "no_action":
            memory_info = ""
            if memory_context:
                memory_info = f"\nPAST SESSION MEMORIES: {memory_context[:600]}\nIMPORTANT MEMORY RULE: You DO have memory. If asked, refer to these memories. Do not invent past conversations."
            else:
                memory_info = "\nIMPORTANT MEMORY RULE: You DO have memory capabilities, but since this is a new session/account, there are no past memories yet. If asked, state honestly that we haven't talked much yet."
                
            simple_prompt = f"""You are SentiMind, a friendly companion. This is casual conversation unless the recent session thread shows the user is continuing a distress concern.
Respond naturally and warmly. Keep it short (1-2 sentences). NO therapy, NO emotion analysis, NO technique suggestions. If the current message is a short reply to an earlier distress thread, connect it back with empathy and ask one gentle follow-up.{memory_info}

 EMERGENCY SAFETY CLAUSE: If the user expresses ANY sudden sadness, fear, self-harm, or distress in this specific message, drop the casual tone immediately. Acknowledge their pain and offer gentle support instead of casual chitchat."""
            
            simple_msg = user_message
            fast_messages = [SystemMessage(content=simple_prompt)]
            continuity_context = _build_session_continuity_context(recent_history, user_message)
            if continuity_context:
                fast_messages.append(SystemMessage(content=continuity_context))
            if recent_history:
                for turn in recent_history:
                    role = getattr(turn, 'type', 'human')
                    content = getattr(turn, 'content', '')
                    if content:
                        if role == 'human':
                            fast_messages.append(HumanMessage(content=content))
                        else:
                            fast_messages.append(AIMessage(content=content))
            
            fast_messages.append(HumanMessage(content=simple_msg))
            
            # For casual, stream it anyway for consistency
            async def _casual_generator():
                async for token in stream_response_tokens(llm, fast_messages):
                    yield token
            
            return _casual_generator(), {"final_response_streamed": True}
        
        # BUILD SYSTEM PROMPT AND CONTEXT (same as non-streaming)
        system_prompt = _build_optimized_system_prompt(
            agent_role=agent_role,
            emotion=emotion,
            intensity=intensity,
            technique=recommended_technique,
            crisis_detected=crisis_detected,
            strategy=conversation_strategy,
            trend=emotional_trend,
            phase=conversation_phase,
            distortion_type=distortion_type,
            clinical_severity=clinical_severity,
            conversation_stage=conversation_stage,
            current_intent=current_intent,
            needs_technique=needs_technique,
            response_task=response_task,
            # v11.0: consent governance (was missing in streaming path — critical fix)
            exercise_consent=state.get("exercise_consent", "unknown"),
            suppressed_topics=state.get("suppressed_topics") or [],
            active_issue_source=state.get("active_issue_source"),
            solution_preference=state.get("solution_preference", "unknown"),
        )
        
        context_text = _build_structured_context(
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
            primary_sub_emotion=primary_sub_emotion,
            secondary_sub_emotions=secondary_sub_emotions,
            detected_symptoms=detected_symptoms,
            detected_behaviors=detected_behaviors,
            detected_contexts=detected_contexts,
            technique=recommended_technique,
            agent_role=agent_role,
            is_new_user=is_new_user,
            user_message=user_message,
            strategy=conversation_strategy,
            trend=emotional_trend,
            phase=conversation_phase,
            distortion_type=distortion_type,
            distortion_explanation=distortion_explanation,
            micro_action=micro_action,
            proactive_alert=proactive_alert,
            psych_profile=psych_profile,
            memory_context=memory_context,
            voice_features=voice_features,
            voice_processed=voice_processed,
            text_emotion_raw=state.get("emotion", "neutral"),
            clinical_severity=clinical_severity,
            clinical_phq9=state.get("clinical_phq9_score", 0),
            clinical_gad7=state.get("clinical_gad7_score", 0),
            clinical_indicators=state.get("clinical_indicators", []),
            conversation_stage=conversation_stage,
            current_intent=current_intent,
            needs_technique=needs_technique,
            primary_concern=state.get("primary_concern"),
            concern_duration=state.get("concern_duration"),
            triggering_subject=state.get("triggering_subject"),
            triggering_context=state.get("triggering_context"),
            functional_impact=state.get("functional_impact"),
            core_belief=state.get("core_belief"),
            latest_recommended_technique=latest_recommended_technique,
            latest_rejected_technique=latest_rejected_technique,
            preferred_techniques=preferred_techniques,
            response_task=response_task,
            active_thread_summary=state.get("active_thread_summary"),
            last_assistant_question=state.get("last_assistant_question"),
            expected_answer_type=state.get("expected_answer_type"),
            # v11.0: consent governance
            exercise_consent=state.get("exercise_consent", "unknown"),
            suppressed_topics=state.get("suppressed_topics") or [],
            active_issue_source=state.get("active_issue_source"),
            solution_preference=state.get("solution_preference", "unknown"),
        )
        
        # PREPARE LLM MESSAGES
        llm_messages = [SystemMessage(content=system_prompt)]
        continuity_context = _build_session_continuity_context(recent_history, user_message)
        if continuity_context:
            llm_messages.append(SystemMessage(content=continuity_context))
        
        if recent_history:
            for turn in recent_history:
                role = getattr(turn, 'type', 'human')
                content = getattr(turn, 'content', '')
                if content:
                    if role == 'human':
                        llm_messages.append(HumanMessage(content=content))
                    else:
                        llm_messages.append(AIMessage(content=content))
            print(f"[NODE:RESPONSE-STREAM]  Injected {len(recent_history)} recent turns")
        
        llm_messages.append(HumanMessage(content=context_text))

        _debug_print_response_context(
            state=state,
            recent_history=recent_history,
            continuity_context=continuity_context,
            context_text=context_text,
            llm_messages=llm_messages,
        )
        
        print("[NODE:RESPONSE-STREAM]  Starting token stream...")
        
        # Return the async generator
        async def _streaming_generator():
            async for token in stream_response_tokens(llm, llm_messages):
                yield token
            print("[NODE:RESPONSE-STREAM]  Stream complete")
        
        return _streaming_generator(), {"final_response_streamed": True}
        
    except Exception as e:
        print(f"[NODE:RESPONSE-STREAM]  Error in streaming generator: {str(e)[:100]}")
        async def _error_generator():
            yield "I hear you. Thank you for sharing. How can I support you right now? "
        return _error_generator(), {"final_response_streamed": False}
