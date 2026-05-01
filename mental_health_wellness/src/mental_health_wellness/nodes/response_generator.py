"""
Response Generator Node - Empathy-focused response generation

ARCHITECTURE NODE 6:
Purpose: Generate empathetic response based on agentic decisions
Runs AFTER role selector (node 4.5) to adapt communication style
Runs BEFORE session saver (node 7)

KEY PRINCIPLES:
- Communication style is determined by agent_role (from role_selector_node)
- LLM generates PURE empathy ONLY (no technique names)
- Techniques are added PROGRAMMATICALLY based on agentic decisions
- This guarantees response text matches technique card exactly
- NO technique hallucination or mismatch possible

AGENT ROLES (from role_selector):
- "friend" (intensity < 0.4): Listen and validate only, NO exercises
- "coach" (0.4 ≤ intensity < 0.7): Validate + advise + optional exercise
- "trainer" (intensity ≥ 0.7): Validate + strongly recommend + guide
- "crisis_support" (crisis detected): Emergency resources + immediate help
"""

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Optional

from ..agent.state import MentalHealthState
from ..agent.prompts import get_response_prompt, get_role_based_prompt, PROMPTS
from ..llm import get_chat_llm


class EmpathyOnlyResponse(BaseModel):
    """Structured response - pure empathy without technique mention"""
    empathy: str = Field(
        description="2-4 sentences of warm, empathetic response to the user's situation. "
                    "Validate their feelings and show understanding. "
                    "DO NOT mention any specific technique or exercise name."
    )
    follow_up: str = Field(
        description="A supportive closing sentence or question (1 sentence). "
                    "DO NOT mention any technique name."
    )


async def response_generator_node(state: MentalHealthState) -> dict:
    """
    RESPONSE GENERATOR NODE - Generate final empathetic response.
    
    ARCHITECTURE FLOW:
    Input: Agentic decisions + emotion analysis + agent_role
    Process: LLM generates role-appropriate response
    Output: If technique recommended → append programmatically
    
    KEY PRINCIPLES:
    1. Agent role determines communication style (friend/coach/trainer/crisis_support)
    2. LLM generates ONLY empathy (no technique names)
    3. Technique is appended PROGRAMMATICALLY if recommended by agent
    4. Guarantees 100% consistency between text and technique card
    5. Prevents LLM from hallucinating wrong techniques
    
    ERROR HANDLING:
    - If LLM fails: Returns empathetic fallback
    - If state missing data: Uses sensible defaults
    - Never crashes - always returns a response
    
    Input State:
        - messages: Current user message
        - chat_history: Previous messages for context
        - emotion: Detected emotion from agentic analysis
        - agent_role: Role from role_selector_node ("friend", "coach", "trainer", "crisis_support")
        - recommended_technique: Technique selected by agentic agent (if any)
        - is_new_user: Boolean flag
        - user_preferences: User's communication preferences
    
    Output State:
        - final_response: The complete response to send to user
        - response_generation_errors: List of non-fatal errors
    """
    
    try:
        # ============================================
        # GUARD: Don't overwrite non-crisis responses
        # ============================================
        existing_response = state.get("final_response", "")
        crisis_detected = state.get("crisis_detected", False)
        if existing_response and not crisis_detected:
            print("[NODE: RESPONSE_GENERATOR] ✅ Response already set — passing through")
            return {"final_response": existing_response}
        
        # ============================================
        # VALIDATE INPUT STATE
        # ============================================
        
        messages = state.get("messages", [])
        chat_history = state.get("chat_history", [])
        intent = state.get("intent", "casual")
        emotion = state.get("emotion", "neutral")
        is_new_user = state.get("is_new_user", False)
        agent_role = state.get("agent_role", "coach")  # NEW: Get agent role
        recommended_technique = state.get("recommended_technique", {})
        audio_file_path = state.get("audio_file_path", None)  # Check for voice
        
        user_message = messages[-1].content if messages else ""
        user_prefs = state.get("user_preferences", {})
        
        # Track if this was a voice message
        is_voice_message = bool(audio_file_path)
        
        print(f"\n[NODE: RESPONSE_GENERATOR] 💬 Generating response")
        print(f"[NODE: RESPONSE_GENERATOR] Agent Role: {agent_role}, Intent: {intent}, Emotion: {emotion}, New user: {is_new_user}")
        print(f"[NODE: RESPONSE_GENERATOR] Chat history: {len(chat_history)} previous messages")
        if is_voice_message:
            print(f"[NODE: RESPONSE_GENERATOR] 🎤 This was a VOICE MESSAGE")
        print(f"[NODE: RESPONSE_GENERATOR] Preferences: {user_prefs}")
        
        if recommended_technique:
            print(f"[NODE: RESPONSE_GENERATOR] Technique available: {recommended_technique.get('name', 'Unknown')}")
        
        # ============================================
        # SPECIAL CASES: NO LLM NEEDED
        # ============================================
        
        # ============================================
        # PREPARE CONTEXT FOR PROMPT SELECTOR
        # ============================================
        
        prompt_context = {
            "crisis_detected": state.get("crisis_detected", False),
            "crisis_level": state.get("crisis_level", "low"),
            "is_new_user": is_new_user,
            "session_count": state.get("session_count", 0),
            "intent": intent,
            "message": user_message
        }
        
        # Get the appropriate system prompt dynamically
        system_prompt = get_response_prompt(prompt_context)
        
        # ============================================
        # ADD ROLE-BASED PROMPT (NEW - NODE 4.5)
        # ============================================
        # Prepend the role-specific instructions to adapt communication style
        role_prompt = get_role_based_prompt(agent_role)
        system_prompt = role_prompt + "\n\n--- BASE INSTRUCTIONS ---\n" + system_prompt
        
        print(f"[NODE: RESPONSE_GENERATOR] 🎭 Using role-based prompt: {agent_role.upper()}")
        
        # ============================================
        # PREPEND CRITICAL SYSTEM INSTRUCTION
        # ============================================
        # Always start with the critical rule about not making up techniques
        from ..agent.prompts import PROMPTS
        system_instruction = PROMPTS.get("system_instruction", "")
        if system_instruction and system_instruction not in system_prompt:
            system_prompt = system_instruction + "\n\n" + system_prompt
        
        # ============================================
        # CHECK IF TEMPLATE RESPONSE IS SUFFICIENT
        # ============================================
        
        # If the prompt selector returned a fixed template (like casual greeting or new user welcome),
        # we might be able to use it directly without LLM if it's a simple template.
        # But for new logic, we typically want the LLM to personalize it slightly unless it's a strict template.
        # The prompt selector returns SYSTEM PROMPTS, not final responses, except for the crisis one
        # which acts as a template instruction.
        
        # However, for simple greetings, we might want to skip LLM to save cost/latency:
        if system_prompt == PROMPTS.get("casual_greeting") or system_prompt == PROMPTS.get("new_user_welcome"):
             # If it's a Greeting/Welcome, we can potentially return it directly 
             # OR let the LLM generate a variation. 
             # The previous logic had a "template greeting" return. 
             # Let's keep the LLM usage for personalization but with the specific prompt.
             pass

        
        # ============================================
        # FALLBACK: IF AGENT MISSED TECHNIQUE FOR NEGATIVE EMOTION
        # ============================================
        
        # USER REQUEST: DISABLED FALLBACK - Agent must select technique itself
        # if not recommended_technique and emotion in ["anxiety", "sadness", "anger", "fear", "stress"]:
        #     print(f"[NODE: RESPONSE_GENERATOR] ⚠️ Agent didn't select technique for {emotion} - fetching fallback...")
        #     try:
        #         from ..tools.technique_tools import recommend_technique
        #         # Manually invoke tool to get fallback technique
        #         fallback_result = await recommend_technique.ainvoke({"emotion": emotion, "limit": 1})
        #         if fallback_result and isinstance(fallback_result, list) and len(fallback_result) > 0:
        #             recommended_technique = fallback_result[0]
        #             state["recommended_technique"] = recommended_technique # Update state
        #             print(f"[NODE: RESPONSE_GENERATOR] ✅ Fallback technique found: {recommended_technique.get('name')}")
        #     except Exception as fb_err:
        #         print(f"[NODE: RESPONSE_GENERATOR] ❌ Fallback fetch failed: {fb_err}")

        # ============================================
        # BUILD CONTEXT FOR LLM
        # ============================================
        
        context_parts = []
        
        # User context
        if is_new_user and len(chat_history) == 0:
            context_parts.append("This is a NEW USER - be extra welcoming and introduce yourself briefly.")
        else:
            session_count = state.get("session_count", 0)
            if session_count > 5:
                context_parts.append(f"This is a RETURNING USER (session #{session_count}) - acknowledge their journey.")
        
        # Emotion context
        if emotion != "neutral":
            intensity = state.get("intensity", 0.5)
            context_parts.append(f"Detected emotion: {emotion.upper()} (intensity: {intensity:.0%})")
        
        # Voice message context
        if is_voice_message:
            context_parts.append("""🎤 VOICE MESSAGE: The user spoke this message (transcribed to text).
Acknowledge their voice naturally: "Thank you for sharing..." NOT "I read your message..."
Their spoken word is a valid way to communicate with you.""")
        
        # ============================================
        # TECHNIQUE HANDLING - NEW APPROACH
        # ============================================
        
        has_technique = bool(recommended_technique and recommended_technique.get("name"))
        
        if has_technique:
            tech_name = recommended_technique.get("name", "")
            tech_rating = recommended_technique.get("avg_rating", 0)
            tech_why = recommended_technique.get("why_it_works", "")
            
            print(f"[NODE: RESPONSE_GENERATOR] 🎯 Will add technique: '{tech_name}' (rating: {tech_rating})")
            
            # Tell LLM to generate ONLY empathy - NO technique mention
            context_parts.append(f"""
📝 YOUR TASK:
Generate a warm, empathetic response to the user's situation.
- Validate their feelings about: "{user_message}"
- Show understanding for their {emotion} emotion
- CRITICAL: DO NOT mention any specific technique, exercise, or tool name in your text.
- Valid Example: "I hear how overwhelmed you are. It's completely normal to feel this way."
- Invalid Example: "I hear you. Try the Box Breathing exercise." (DO NOT DO THIS)
- We will add the technique recommendation separately.
            """)
        else:
            # No technique - regular empathetic response
            intent_guidance = {
                "emotional": "User is sharing feelings - validate and empathize deeply.",
                "technique_request": "User asked for help - acknowledge their request warmly.",
                "check_in": "User wants to check their progress - summarize positively and encourage.",
                "casual": "Keep it light and friendly - no need for deep support."
            }
            context_parts.append(intent_guidance.get(intent, "Respond naturally and warmly."))
            
            # Extra warning for casual/emotional responses to NOT hallucinate techniques
            context_parts.append("IMPORTANT: Do NOT suggest any specific exercises or techniques. Just listen and empathize.")
        
        # Add conversation continuity reminder if there's chat history
        if chat_history:
            context_parts.append(
                "IMPORTANT: You have conversation history with this user. "
                "Reference previous topics naturally and maintain continuity. "
                "Do NOT introduce yourself again or ask questions you already asked. "
                "If user mentioned exercises, techniques, or coping strategies before, "
                "acknowledge that context in your response."
            )
        
        # Check messages for previous exercise discussion to preserve context
        if len(messages) >= 2:
            # Look at recent messages to see if exercises were discussed
            recent_msgs_str = " ".join([
                m.content.lower() for m in messages[-4:] 
                if hasattr(m, 'content') and hasattr(m, 'type') and m.type == 'ai'
            ])
            if any(term in recent_msgs_str for term in ['exercise', 'breathing', 'meditation', 'technique', 'grounding', 'relaxation']):
                context_parts.append(
                    "CONTEXT: We recently discussed a coping technique or exercise. "
                    "When answering, maintain context about that conversation and reference it if relevant."
                )
        
        # Add user communication preferences
        if user_prefs:
            pref_parts = []
            if user_prefs.get("communicationStyle"):
                pref_parts.append(f"communication style: {user_prefs['communicationStyle']}")
            if user_prefs.get("detailLevel"):
                pref_parts.append(f"detail level: {user_prefs['detailLevel']}")
            if user_prefs.get("tone"):
                pref_parts.append(f"tone: {user_prefs['tone']}")
            if pref_parts:
                context_parts.append(f"USER PREFERENCES: Respond with {', '.join(pref_parts)}.")
        
        context = "\n".join(context_parts)
        
        # ============================================
        # BUILD LLM MESSAGES WITH CHAT HISTORY
        # ============================================
        
        llm = get_chat_llm()
        
        # Combine both system-level instructions into a single SystemMessage
        # (some LLM providers only respect the last system message)
        combined_system = (
            system_prompt
            + "\n\n--- CONTEXT FOR THIS RESPONSE ---\n"
            + context
        )
        
        llm_messages = [
            SystemMessage(content=combined_system)
        ]
        
        # Add chat history for context continuity (limit to last 10 messages)
        recent_history = chat_history[-10:] if len(chat_history) > 10 else chat_history
        
        for msg in recent_history:
            if msg["role"] == "user":
                llm_messages.append(HumanMessage(content=msg["content"]))
            else:  # assistant
                llm_messages.append(AIMessage(content=msg["content"]))
         
        # Add current user message
        llm_messages.append(HumanMessage(content=user_message))
        
        print(f"[NODE: RESPONSE_GENERATOR] 🤖 Calling LLM with {len(llm_messages)} messages (history limit: 10)...")
        
        # ============================================
        # GENERATE RESPONSE
        # ============================================
        
        if has_technique:
            # Add instruction for pure empathy (without structured output - Groq compatibility)
            llm_messages.append(SystemMessage(
                content='Generate 2-3 sentences of warm, empathetic response to their situation. Validate their feelings. '
                        'DO NOT mention any technique or exercise name.'
            ))
            
            response = await llm.ainvoke(llm_messages)
            empathy_text = response.content.strip()
            
            # BUILD FINAL RESPONSE: Empathy + Programmatic Technique Intro
            tech_name = recommended_technique.get("name", "")
            tech_why = recommended_technique.get("why_it_works", "")
            
            # Create technique introduction programmatically
            technique_intro = f"I'd like to share a technique called **{tech_name}** that can help you with this."
            if tech_why:
                technique_intro += f" {tech_why}"
            
            invitation = "Would you like to give it a try?"
            
            # Combine: Empathy + Technique Intro + Invitation
            final_response = f"{empathy_text}\n\n{technique_intro}\n\n{invitation}"
            
            print(f"[NODE: RESPONSE_GENERATOR] ✅ Response with EXACT technique: {tech_name}")
            
        else:
            # Regular response (no technique)
            response = await llm.ainvoke(llm_messages)
            final_response = response.content.strip()
            
            print(f"[NODE: RESPONSE_GENERATOR] ✅ Regular response generated")
        
        print(f"[NODE: RESPONSE_GENERATOR] ✅ Final response ready ({len(final_response)} chars)")
        
        return {"final_response": final_response}
        
    except Exception as e:
        """
        CATCH-ALL ERROR HANDLER
        If anything goes wrong above, return sensible fallback
        Never crash - always return a response
        """
        print(f"\n[NODE: RESPONSE_GENERATOR] ❌ CRITICAL ERROR in response generation")
        print(f"[NODE: RESPONSE_GENERATOR] Error Type: {type(e).__name__}")
        print(f"[NODE: RESPONSE_GENERATOR] Error Details: {str(e)[:200]}")
        
        import traceback
        error_trace = traceback.format_exc()
        print(f"[NODE: RESPONSE_GENERATOR] Traceback:\n{error_trace[:500]}")
        
        # Track error for diagnostics
        response_gen_errors_list = []
        response_gen_errors_list.append({
            "error_type": type(e).__name__,
            "error_message": str(e)[:200],
            "node": "response_generator",
            "timestamp": __import__("datetime").datetime.now().isoformat()
        })
        
        # Return sensible fallback response
        fallback_response = (
            "I'm here to support you. "
            "Please take a moment to breathe and share what's on your mind."
        )
        
        print(f"[NODE: RESPONSE_GENERATOR] 🔄 Returning fallback response")
        
        return {
            "final_response": fallback_response,
            "response_generation_errors": response_gen_errors_list
        }
