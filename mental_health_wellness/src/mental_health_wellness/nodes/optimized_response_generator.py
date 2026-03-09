"""
Optimized Response Generator - Single LLM call with structured input

ARCHITECTURE NODE 5:
Purpose: Generate single empathetic response with structured data
Runs AFTER technique selector, BEFORE session saver
ONE LLM call only - receives structured data from previous nodes
"""

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional
import time

from ..agent.state import MentalHealthState
from ..llm import get_chat_llm


class OptimizedResponse(BaseModel):
    """Structured response format for LLM"""
    response: str = Field(
        description="Warm empathetic response to user, acknowledging their emotion. "
                    "Can reference the technique if provided. 100-150 words."
    )


async def optimized_response_generator_node(state: MentalHealthState) -> dict:
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
            print("[RESPONSE] ✅ Crisis response already set")
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
        
        user_message = messages[-1].content if messages else ""
        
        print(f"[RESPONSE] 💬 Generating | Role: {agent_role} | Emotion: {emotion} | Intensity: {intensity:.0%}")
        if distortion_type:
            print(f"[RESPONSE] 🧠 Distortion: {distortion_type}")
        if micro_action:
            print(f"[RESPONSE] 💡 Micro-action: {micro_action[:50]}...")
        
        # ============================================
        # BUILD ULTRA-CONCISE SYSTEM PROMPT (<150 tokens)
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
        )
        
        # ============================================
        # PREPARE LLM MESSAGES (SINGLE CALL)
        # ============================================
        
        llm_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=context_text)
        ]
        
        start_time = time.time()
        
        # ============================================
        # SINGLE LLM CALL
        # ============================================
        
        llm = get_chat_llm()
        response = llm.invoke(llm_messages)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        final_response = response.content if hasattr(response, 'content') else str(response)
        
        print(f"[RESPONSE] ✅ Generated | Time: {elapsed_ms}ms | Length: {len(final_response)} chars")
        
        return {"final_response": final_response}
        
    except Exception as e:
        print(f"[RESPONSE] ❌ Error: {str(e)[:80]}")
        # Fallback response
        fallback = "I hear you. Thank you for sharing. How can I support you right now? 💙"
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
    Build ultra-concise system prompt (<200 tokens).
    Now includes conversation strategy, emotional trend, and cognitive distortion context.
    """
    
    if crisis_detected:
        return """You are SentiMind, a mental health companion in crisis mode.
IMMEDIATE RESPONSE:
- Acknowledge crisis seriously
- Show you care
- Provide these exact resources:

🆘 **Immediate Support:**
- **988 Suicide & Crisis Lifeline**: Call/text 988 (24/7)
- **Crisis Text Line**: Text HOME to 741741

Message tone: Warm, urgent, caring. Not clinical."""

    role_instructions = {
        "friend": "Listen and validate only. Show empathy. No exercises or techniques.",
        "coach": "Validate and support. If technique available, introduce it gently.",
        "trainer": "Validate strongly. Present technique confidently and guide them through it.",
        "crisis_support": "Emergency focus. Provide resources. Keep them safe."
    }
    
    role_desc = role_instructions.get(agent_role, role_instructions["coach"])
    
    technique_desc = ""
    if technique:
        technique_desc = f"\n\nTECHNIQUE AVAILABLE:\n- Name: {technique.get('name', 'Unknown')}\n- Duration: {technique.get('duration_minutes', 'N/A')} min\n- Category: {technique.get('category', 'N/A')}"
    
    # Strategy-specific response instructions
    strategy_instructions = {
        "no_action": "STRATEGY: This is casual conversation. Respond naturally as a friendly companion. Do NOT validate feelings, analyze emotions, or suggest any technique.",
        "validate_only": "STRATEGY: Only validate and listen. Do NOT suggest any technique or exercise. Show you understand.",
        "ask_question": "STRATEGY: After validating, ask ONE thoughtful open-ended question to understand the user better.",
        "encourage_reflection": "STRATEGY: Gently guide the user to reflect on their patterns or feelings.",
        "reframe": "STRATEGY: Help the user see their situation from a new, more constructive perspective.",
        "suggest_technique": "STRATEGY: After validating, introduce the recommended technique naturally.",
        "distract": "STRATEGY: Lighten the mood with positive redirection while remaining supportive.",
    }
    strategy_desc = strategy_instructions.get(strategy, strategy_instructions["validate_only"])
    
    # Trend context
    trend_desc = {
        "improving": "The user's emotional state has been IMPROVING over recent messages.",
        "worsening": "The user's emotional state has been WORSENING — provide extra care and urgency.",
        "stable": "The user's emotional state is stable.",
    }.get(trend, "")
    
    # Distortion-specific instruction [v3 NEW]
    distortion_desc = ""
    if distortion_type:
        distortion_instructions = {
            "catastrophizing":    "The user is catastrophizing. Gently normalize and introduce conditional thinking (\"sometimes\" instead of \"always\").",
            "black_white":        "The user is thinking in black-and-white. Help them find the nuanced middle ground.",
            "overgeneralization": "The user is overgeneralizing. Help them see this as one event, not a pattern.",
            "mind_reading":       "The user is mind-reading others. Gently question whether they know that for sure.",
            "personalization":    "The user is over-personalizing. Help them separate what is their responsibility vs. not.",
            "should_statements":  "The user is using rigid 'should' thinking. Replace with flexible 'could' language.",
            "emotional_reasoning":"The user is equating feelings with facts. Help them distinguish.",
            "magnification":      "The user is magnifying the situation. Help them find proportionate perspective.",
        }
        instruction = distortion_instructions.get(distortion_type, "")
        if instruction:
            distortion_desc = f"\n\nCBT NOTE: {instruction}"

    return f"""You are SentiMind, a compassionate mental health companion.

ROLE: {agent_role.upper()}
{role_desc}

CONTEXT:
- Detected emotion: {emotion.upper()}
- Intensity: {intensity:.0%}
- User feeling: {'Strong' if intensity > 0.7 else 'Moderate' if intensity > 0.4 else 'Mild'}
- Conversation phase: {phase.upper()}
- Emotional trend: {trend.upper()}
{technique_desc}

{strategy_desc}
{trend_desc}
{distortion_desc}

RESPONSE RULES:
- 2-3 short paragraphs (100-150 words max)
- Warm, empathetic, natural tone
- No medical advice or diagnosis
- 1-2 emojis max
- If technique available and strategy is suggest_technique: "I'd like to share **[technique_name]**..."
- Always ask how they're feeling or offer next step"""


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
        "magnification":       f"offer a proportionate perspective — acknowledge the difficulty without amplifying it",
    }
    _reframe_hint = _distortion_reframe_hints.get(distortion_type or "", "help them see their situation from a new, more constructive angle")

    strategy_tasks = {
        "validate_only": "1. Acknowledge their emotion deeply\n2. Validate their feelings\n3. Show you're listening and present\n4. Do NOT suggest any technique",
        "ask_question": "1. Acknowledge their emotion\n2. Validate briefly\n3. Ask ONE thoughtful open-ended question\n4. Do NOT suggest any technique yet",
        "encourage_reflection": "1. Acknowledge their emotion\n2. Gently help them reflect on patterns\n3. Guide toward self-awareness\n4. Technique optional if natural",
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

    return f"""STRUCTURED ANALYSIS:

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
TASK:
Generate a warm, empathetic response that:
{task_text}

Remember: Focus on empathy and connection first."""
