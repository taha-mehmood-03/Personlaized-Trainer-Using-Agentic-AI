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
import time

from ..agent.state import MentalHealthState
from ..llm import get_chat_llm


class OptimizedResponse(BaseModel):
    """Structured response format for LLM"""
    response: str = Field(
        description="Warm empathetic response to user, acknowledging their emotion. "
                    "Can reference the technique if provided. 100-150 words."
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
        recommended_technique = state.get("recommended_technique", {})
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

        # NEW: voice acoustic context
        voice_features  = state.get("voice_features") or {}
        voice_processed = state.get("voice_processed", False)
        
        user_message = messages[-1].content if messages else ""
        # Within-session: last 6 message turns from LangGraph state (no DB needed)
        recent_history = messages[:-1][-6:] if len(messages) > 1 else []
        # Cross-session: semantic memory from ChromaDB (fetched by intake_node)
        memory_context = state.get("memory_context", "")

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
                    prev_ai = prev_ai_msgs[-1].content.lower()
                    if any(kw in prev_ai for kw in ["technique", "exercise", "breathing", "mindfulness", "meditation"]):
                        user_rejected_technique = True
                        print(f"[NODE:RESPONSE]  TECHNIQUE REJECTION DETECTED  user signalled previous technique didn't help")

        #  Technique acceptance detection 
        # When the AI offered a specific technique in the previous turn and the
        # user agrees (yes/sure/go for it/let's do it), deliver THAT technique
        # instead of starting fresh emotion analysis.
        _ACCEPTANCE_SIGNALS = {
            "yes", "sure", "okay", "ok", "go for it", "let's do it", "lets do it",
            "go ahead", "sounds good", "alright", "yeah", "yep", "yup",
            "please", "i'm ready", "im ready", "let's try", "lets try",
            "i'd like to", "id like to", "tell me", "show me", "guide me",
        }
        user_accepted_technique = False
        accepted_technique_name: str | None = None

        _last_user_lower = user_message.lower().strip()
        _is_short = len(_last_user_lower.split()) <= 6  # acceptance replies are usually short

        if _is_short and any(sig in _last_user_lower for sig in _ACCEPTANCE_SIGNALS):
            prev_ai_msgs = [m for m in recent_history if getattr(m, "type", "") == "ai"]
            if prev_ai_msgs:
                prev_ai_content = prev_ai_msgs[-1].content
                prev_ai_lower = prev_ai_content.lower()
                # Check AI previously proposed a technique
                _TECHNIQUE_OFFER_SIGNALS = [
                    "i'd like to suggest", "i would like to suggest",
                    "let me suggest", "i'd like to share", "i would like to share",
                    "how about trying", "would you like to try", "open to trying",
                    "give it a try", "let's try", "let me walk you through",
                ]
                if any(sig in prev_ai_lower for sig in _TECHNIQUE_OFFER_SIGNALS):
                    user_accepted_technique = True
                    # Try to extract the technique name from the previous AI message
                    import re
                    # Look for quoted or bolded technique names
                    match = re.search(
                        r"(?:suggest|share|try|walk you through)\s+['\"]?([A-Za-z0-9 \-]+?)['\"]?\s*(?:with|exercise|technique|,|\.|$)",
                        prev_ai_content, re.IGNORECASE
                    )
                    if match:
                        accepted_technique_name = match.group(1).strip()
                    print(f"[NODE:RESPONSE]  TECHNIQUE ACCEPTANCE DETECTED  user agreed to: {accepted_technique_name or 'the offered technique'}")

        print(f"[NODE:RESPONSE]  Generating | Role: {agent_role} | Emotion: {emotion} ({intensity:.0%}) | Strategy: {conversation_strategy}")
        if user_rejected_technique:
            print(f"[NODE:RESPONSE]  Will adapt response to acknowledge technique rejection")
        if distortion_type:
            print(f"[NODE:RESPONSE]  CBT Distortion: {distortion_type}")
        if memory_context:
            print(f"[NODE:RESPONSE]  Memory context available ({len(memory_context)} chars)  injecting into prompt")

        # Fetch LLM instance once  reused on both fast and therapeutic paths
        llm = get_chat_llm()

        
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
                
            simple_prompt = f"""You are SentiMind, a friendly companion. This is casual conversation  the user is NOT in distress.
Respond naturally and warmly. Keep it short (1-2 sentences). NO therapy, NO emotion analysis, NO technique suggestions.{memory_info}

 EMERGENCY SAFETY CLAUSE: If the user expresses ANY sudden sadness, fear, self-harm, or distress in this specific message, drop the casual tone immediately. Acknowledge their pain and offer gentle support instead of casual chitchat."""
            
            simple_msg = user_message

            # Build messages with within-session history so it remembers names mentioned 2 messages ago
            fast_messages = [SystemMessage(content=simple_prompt)]
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
            casual_response = await llm.ainvoke(fast_messages, config={"tags": ["final_response_llm"]})
            
            final_response = casual_response.content if hasattr(casual_response, 'content') else str(casual_response)
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
        )

        #  Rejection override: inject strong instruction into system prompt 
        if user_rejected_technique:
            rejection_instruction = (
                "\n\n CRITICAL CONTEXT  TECHNIQUE WAS REJECTED:\n"
                "The user has told you that the PREVIOUS technique or exercise you suggested did NOT help them.\n"
                "You MUST:\n"
                "  1. Acknowledge their frustration warmly (1 sentence)  e.g. 'I hear you, that one didn't resonate.'\n"
                "  2. Do NOT apologize excessively or repeat the same technique.\n"
                "  3. Introduce the NEW technique below with fresh energy, framing it as a different approach.\n"
                "  4. Keep the response concise and compassionate.\n"
                "NEVER re-suggest the same technique name. The new technique card will be shown automatically."
            )
            system_prompt += rejection_instruction

        #  Acceptance override: deliver the previously-offered technique 
        if user_accepted_technique:
            _tech_label = f'"{accepted_technique_name}"' if accepted_technique_name else "the technique you just offered"
            acceptance_instruction = (
                f"\n\n CRITICAL CONTEXT  USER ACCEPTED THE OFFERED TECHNIQUE:\n"
                f"The user has agreed to try {_tech_label}. They said: \"{user_message}\".\n"
                f"You MUST:\n"
                f"  1. Respond warmly to their acceptance (1 sentence)  e.g. 'Great, let's do this together!'\n"
                f"  2. Immediately begin guiding them through {_tech_label} step-by-step.\n"
                f"  3. Do NOT suggest a completely different technique.\n"
                f"  4. Do NOT repeat the offer  they already said yes. Start the exercise.\n"
                f"  5. Ignore the freshly-detected emotion below if it contradicts this context  \n"
                f"     the user's intent is clear from their 'yes'. Follow through.\n"
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
        if user_rejected_technique and not recommended_technique:
            print(f"[NODE:RESPONSE]  Rejection detected but no technique selected  force-fetching alternative")
            try:
                from ..tools.technique_tools import recommend_technique as _rt
                alt_top3 = await _rt.ainvoke({
                    "emotion": emotion,
                    "intensity": intensity,
                    "user_id": state.get("user_id", ""),
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
        )

        # ============================================
        # PREPARE LLM MESSAGES WITH LAYERED MEMORY
        # ============================================

        llm_messages = [SystemMessage(content=system_prompt)]

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
        
        start_time = time.time()
        
        # ============================================
        # SINGLE LLM CALL
        # ============================================
        
        # Tag the core therapeutic LLM call for event streaming filtering
        response = await llm.ainvoke(llm_messages, config={"tags": ["final_response_llm"]})
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        final_response = response.content if hasattr(response, 'content') else str(response)
        print(f"[NODE:RESPONSE]  Generated in {elapsed_ms}ms ({len(final_response)} chars)")

        result = {"final_response": final_response}
        # Propagate technique back to state (important when force-fetched during rejection)
        if recommended_technique and recommended_technique.get("name"):
            cat = recommended_technique.get("category", "Recommended")
            result["recommended_technique"] = recommended_technique
            result["recommended_techniques_by_category"] = {cat: recommended_technique}

        return result

        
    except Exception as e:
        print(f"[NODE:RESPONSE]  Error generating response: {str(e)[:100]}")
        fallback = "I hear you. Thank you for sharing. How can I support you right now? "
        return {"final_response": fallback}


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
- Be unconditionally present. The user needs to feel heard, not helped.
- Acknowledge the seriousness of what they've shared in 1-2 warm sentences.
- Validate their courage for reaching out.
- Ask ONE gentle open question to keep them talking (e.g., "Are you safe right now?").
- Do NOT suggest techniques, exercises, breathing drills, or hotlines.
- Do NOT minimize ("it'll get better"), invalidate ("things could be worse"), or rush to solutions.
- Do NOT reference past memories or previous sessions  focus entirely on NOW.

Tone: Deeply human, slow, warm, unhurried, unconditionally present. Like a trusted friend sitting beside them."""

    #  ROLE INSTRUCTIONS 
    role_instructions = {
        "friend":        "You are a warm, non-clinical friend. ONLY listen and validate. Never push exercises unless explicitly asked.",
        "coach":         "You are a supportive coach. Validate first, then guide gently. Introduce a technique only if the strategy says so.",
        "trainer":       "You are a confident trainer. Validate strongly, then present the technique with energy and guide them through it step by step.",
        "crisis_support":"You are in crisis support mode. Compassionate human connection is your ONLY goal. No techniques. No resources.",
    }
    role_desc = role_instructions.get(agent_role, role_instructions["coach"])

    #  TECHNIQUE DESCRIPTION 
    technique_desc = ""
    if technique and technique.get("name"):
        technique_desc = (
            f"\n\nTECHNIQUE TO INTRODUCE:\n"
            f"- Name: {technique.get('name')}\n"
            f"- Duration: {technique.get('duration_minutes', 'N/A')} min\n"
            f"- Category: {technique.get('category', 'N/A')}\n"
            f"- Why it works: {technique.get('why_it_works', '')}"
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
            "The question should help you understand them better before any action.\n"
            "Do NOT suggest a technique yet. Do NOT ask more than 1 question."
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
            "Then introduce the technique listed below naturally and warmly.\n"
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
"""

    return f"""You are SentiMind, a compassionate AI mental health companion. You are warm, non-judgmental, and clinically aware.


ROLE: {agent_role.upper()}
{role_desc}

SITUATION:
- Detected emotion: {emotion.upper()} at {intensity:.0%} intensity
- Conversation phase: {phase.upper()}
- Emotional trend: {trend.upper()}
{trend_desc}
{technique_desc}

WHAT TO DO NOW:
{strategy_desc}
{distortion_desc}


RESPONSE FORMAT:
- 2-3 short paragraphs, 80-150 words total
- Warm, empathetic, natural language
- 1-2 emojis max (optional)
- No medical jargon or clinical labels
- End with a gentle question or invitation (unless strategy is no_action)

MEMORY RULE:
If past session memories are provided below, use them only to personalize naturally.
Do NOT open with "I remember you said..."  just weave the context in.
If there are no memories, respond to what the user is sharing right now.

{hard_rules}"""




def _build_structured_context(
    emotion: str,
    intensity: float,
    sentiment: str,
    technique: dict,
    agent_role: str,
    is_new_user: bool,
    user_message: str,
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
) -> str:
    """
    Build structured context for LLM prompt.
    Now includes strategy, trend, phase, distortion, micro-action, and proactive hint.
    """
    
    technique_info = ""
    if technique:
        technique_info = f"""
RECOMMENDED TECHNIQUE:
- Name: {technique.get('name', 'Unknown')}
- Category: {technique.get('category', 'Unknown')}
- Duration: {technique.get('duration_minutes', 'N/A')} minutes
- Difficulty: {technique.get('difficulty', 'N/A')}
- Why it works: {technique.get('why_it_works', 'N/A')}"""
    
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
        "validate_only": "1. Acknowledge their emotion deeply\n2. Validate their feelings\n3. Show you're listening and present\n4. Do NOT suggest any technique",
        "ask_question": "1. Acknowledge their emotion\n2. Validate briefly\n3. Ask ONE thoughtful open-ended question\n4. Do NOT suggest any technique yet",
        "encourage_reflection": "1. Celebrate or validate that the user is actively practicing a technique or reflecting\n2. Ask a gentle question about their experience with it (e.g., 'What does it feel like in your body?')\n3. Encourage them to keep going or share what they notice\n4. Do NOT suggest a new technique  they are already practicing",
        "reframe": (
            f"1. Acknowledge their emotion warmly\n"
            f"2. Notice (without labelling clinically) that their language reflects {_distortion_label}\n"
            f"3. {_reframe_hint.capitalize()}\n"
            f"4. End with an open question or supportive next step"
        ),
        "suggest_technique": "1. Acknowledge their emotion\n2. Validate their feelings\n3. Introduce the technique naturally\n4. Offer supportive next step",
        "distract": "1. Acknowledge briefly\n2. Redirect to something positive\n3. Keep it light and warm",
    }
    task_text = strategy_tasks.get(strategy, strategy_tasks["validate_only"])
    
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

    # Cross-session semantic memory (ChromaDB)  summarized past context [v5.1]
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
- Sentiment: {sentiment.upper()}
- Intensity Level: {intensity:.0%}
- Emotional State: {'Highly distressed' if intensity > 0.7 else 'Moderately concerned' if intensity > 0.4 else 'Mild concern'}
- Emotional Trend: {trend.upper()}
- Conversation Phase: {phase.upper()}
{distortion_info}
{profile_info}
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
        # Use astream instead of ainvoke to get token-by-token output
        async for chunk in llm.astream(llm_messages):
            token_content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if token_content:
                yield token_content
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

        # Voice acoustic context (streaming path)
        voice_features  = state.get("voice_features") or {}
        voice_processed = state.get("voice_processed", False)

        user_message = messages[-1].content if messages else ""
        recent_history = messages[:-1][-6:] if len(messages) > 1 else []
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
                
            simple_prompt = f"""You are SentiMind, a friendly companion. This is casual conversation  the user is NOT in distress.
Respond naturally and warmly. Keep it short (1-2 sentences). NO therapy, NO emotion analysis, NO technique suggestions.{memory_info}

 EMERGENCY SAFETY CLAUSE: If the user expresses ANY sudden sadness, fear, self-harm, or distress in this specific message, drop the casual tone immediately. Acknowledge their pain and offer gentle support instead of casual chitchat."""
            
            simple_msg = user_message
            fast_messages = [SystemMessage(content=simple_prompt)]
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
        )
        
        context_text = _build_structured_context(
            emotion=emotion,
            intensity=intensity,
            sentiment=sentiment,
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
        )
        
        # PREPARE LLM MESSAGES
        llm_messages = [SystemMessage(content=system_prompt)]
        
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
