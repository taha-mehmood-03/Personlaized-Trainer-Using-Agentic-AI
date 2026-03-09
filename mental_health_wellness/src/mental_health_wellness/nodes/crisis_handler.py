"""
Crisis Handler Node - Immediate safety intervention
HIGHEST PRIORITY - Handles all crisis situations
"""

from ..agent.state import MentalHealthState
from ..agent.prompts import PROMPTS


async def crisis_handler_node(state: MentalHealthState) -> dict:
    """
    Handle crisis situations with immediate safety response.
    
    Purpose:
        - Detect crisis severity level
        - Provide immediate crisis resources (hotlines)
        - Generate compassionate crisis response
        - Log for safety tracking
    
    CRITICAL: This node ALWAYS provides crisis resources.
    It sets final_response directly to ensure immediate help.
    
    Input State:
        - messages: Conversation history
        - user_id: For logging
    
    Output State:
        - crisis_level: "low", "medium", "high"
        - crisis_detected: True
        - crisis_resources: Hotline information
        - final_response: Set directly (skips normal response generation)
        - tools_used: Updated with crisis tools
    
    Risk Levels:
        - HIGH: Immediate danger (suicide, self-harm intent)
        - MEDIUM: Warning signs (hopelessness, giving up)
        - LOW: General distress
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "unknown")
    
    last_message = messages[-1].content if messages else ""
    
    print(f"\n[NODE: CRISIS_HANDLER] 🚨 CRISIS RESPONSE ACTIVATED")
    print(f"[NODE: CRISIS_HANDLER] User: {user_id}")
    print(f"[NODE: CRISIS_HANDLER] Message: \"{last_message[:80]}...\"")
    
    try:
        # ============================================
        # CRISIS CHECK: RELY ON AGENT JUDGMENT
        # ============================================
        
        # 1. Check if Agent set a crisis level
        agent_crisis_level = state.get("crisis_level", "low")
        
        # 2. Check if Agent called crisis tools explicitly
        tools_used = state.get("tools_used", [])
        agent_called_crisis_tools = "handle_crisis" in tools_used
        
        print(f"[NODE: CRISIS_HANDLER] 🔍 Agent Crisis Level: {agent_crisis_level.upper()}")
        print(f"[NODE: CRISIS_HANDLER] 🛠️ Agent Tools: {tools_used}")
        
        # Determine final crisis status
        final_crisis_level = "low"
        crisis_pre_screened = state.get("crisis_pre_screened", False)
        
        if crisis_pre_screened:
            final_crisis_level = state.get("crisis_level", "medium")
            print(f"[NODE: CRISIS_HANDLER] 🛡️ Pre-screener trusted — using level: {final_crisis_level.upper()}")
        elif agent_called_crisis_tools:
            final_crisis_level = "high"
            print(f"[NODE: CRISIS_HANDLER] 🤖 Agent explicitly called crisis tools - ESCALATING TO HIGH RISK")
        elif agent_crisis_level in ["medium", "high"]:
            final_crisis_level = agent_crisis_level
            print(f"[NODE: CRISIS_HANDLER] ⚠️ Agent set risk level to {agent_crisis_level.upper()}")
            
        
        # Only treat as crisis if risk level is medium or high
        if final_crisis_level in ["medium", "high"]:
            # Build crisis resources dict (since we removed crisis_resources tool)
            resources = {
                "primary_hotline": {
                    "name": "988 Suicide & Crisis Lifeline",
                    "number": "988",
                    "available": "24/7"
                },
                "text_line": {
                    "name": "Crisis Text Line",
                    "action": "Text HOME to 741741",
                    "available": "24/7"
                }
            }
            
            print(f"[NODE: CRISIS_HANDLER] 📞 Resources: {resources['primary_hotline']['name']}")
            
            # Generate crisis response
            if final_crisis_level == "high":
                response = _generate_high_risk_response(resources)
            else:
                response = _generate_medium_risk_response(resources)
            
            print(f"[NODE: CRISIS_HANDLER] ✅ Crisis response generated")
            
            return {
                "crisis_level": final_crisis_level,
                "crisis_detected": True,
                "crisis_resources": resources,
                "final_response": response,
                "tools_used": ["handle_crisis"]
            }
        else:
            # Not a crisis but high distress (e.g. panic attack, extreme anxiety).
            # The crisis_handler was triggered by the intensity router, NOT the pre-screener.
            # We must generate a supportive response here because the pipeline skips
            # response_generator after crisis_handler.
            emotion = state.get("fused_emotion", state.get("emotion", "anxiety"))
            print(f"[NODE: CRISIS_HANDLER] 💙 High-distress (non-crisis) detected — generating supportive response (emotion: {emotion})")

            # Read the actual techniques selected by technique_selector so the response
            # text references the exact same names shown in the UI cards.
            techniques_by_category = state.get("recommended_techniques_by_category", {})
            technique_names = []
            for cat, tech in techniques_by_category.items():
                name = tech.get("name") if isinstance(tech, dict) else None
                if name:
                    technique_names.append(name)

            if technique_names:
                tech_list = " and ".join(f"**{n}**" for n in technique_names[:2])
                technique_mention = f"I've also pulled up {tech_list} for you below — they're great for moments like this."
            else:
                technique_mention = "I've pulled up some grounding exercises below that can really help in moments like this."

            if "anxiety" in emotion or "fear" in emotion:
                supportive_response = (
                    "I can feel how intense this is for you right now. Panic attacks are terrifying in the moment, but they are temporary and they will pass. 💙\n\n"
                    f"{technique_mention}\n\n"
                    "For right now — breathe in slowly through your nose for 4 counts, hold for 4, and breathe out for 6. Focus only on that breath.\n\n"
                    "You're safe. I'm right here with you. Tell me how you're feeling right now."
                )
            elif "anger" in emotion:
                supportive_response = (
                    "I can sense you're in a really overwhelming place right now. It's okay to feel this way. 💙\n\n"
                    f"{technique_mention}\n\n"
                    "Let's take a moment — try breathing deeply a few times and give yourself permission to step back. I'm here with you."
                )
            else:
                supportive_response = (
                    "I can see you're going through something really intense right now. I'm here with you. 💙\n\n"
                    f"{technique_mention}\n\n"
                    "Take a slow, deep breath with me. You don't have to face this alone. What's happening for you right now?"
                )

            return {
                "crisis_level": final_crisis_level,
                "crisis_detected": False,
                "final_response": supportive_response,
            }
        
    except Exception as e:
        print(f"[NODE: CRISIS_HANDLER] ❌ Error: {e}")
        
        # Fallback crisis response - ALWAYS provide resources
        fallback_response = """I hear you, and I'm concerned about what you've shared. Please know that you matter.

🆘 **Please reach out now:**
- **988 Suicide & Crisis Lifeline**: Call or text **988** (24/7)
- **Crisis Text Line**: Text **HOME** to **741741**

You don't have to face this alone. These are real people ready to help right now. 💙"""
        
        return {
            "crisis_level": "medium",
            "crisis_detected": True,
            "crisis_resources": {},
            "final_response": fallback_response,
            "tools_used": state.get("tools_used", []) + ["crisis_fallback"]
        }


def _generate_high_risk_response(resources: dict) -> str:
    """Generate response for high-risk crisis situations"""
    hotline = resources.get("primary_hotline", {})
    text_line = resources.get("text_line", {})
    
    return f"""I hear you, and I'm really glad you reached out to me right now. What you're feeling is serious, and you deserve immediate support from someone trained to help.

🆘 **Please reach out right now:**
- **{hotline.get('name', '988 Suicide & Crisis Lifeline')}**: Call or text **{hotline.get('number', '988')}** (available 24/7)
- **{text_line.get('name', 'Crisis Text Line')}**: {text_line.get('action', 'Text HOME to 741741')}

These are real people who genuinely care and are ready to listen right now. You're not alone, and there is help available.

I'm here with you too. Would you like to stay and talk while you consider reaching out to them? 💙"""


def _generate_medium_risk_response(resources: dict) -> str:
    """Generate response for medium-risk situations"""
    hotline = resources.get("primary_hotline", {})
    text_line = resources.get("text_line", {})
    
    return f"""I can hear that you're going through something really difficult right now. Thank you for trusting me with this.

If you're having thoughts of hurting yourself, please know that support is available:
- **{hotline.get('name', '988 Suicide & Crisis Lifeline')}**: Call or text **{hotline.get('number', '988')}**
- **{text_line.get('name', 'Crisis Text Line')}**: {text_line.get('action', 'Text HOME to 741741')}

I'm here to listen and support you. What's been weighing on you the most? 💙"""
