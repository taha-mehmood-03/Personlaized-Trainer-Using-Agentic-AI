"""
Role Selector Node - Personalize agent behavior based on emotion intensity

ARCHITECTURE NODE 4.5:
Purpose: Select agent role to adapt communication style to user's emotional state
Runs AFTER crisis detection but BEFORE response generation
Bridges gap between crisis routing and personalized support

KEY INSIGHT:
The agent's role (friend, coach, trainer, crisis_support) determines HOW to respond,
not WHAT tools to use. Tools are already selected by the agentic agent (node 3).
This node only determines the communication style and depth of guidance.

ROLE DEFINITIONS:
- Friend (intensity < 0.4): Listen only, validate feelings, NO exercise recommendations
  - "I see you're dealing with this. That's tough. How are you holding up?"
  - Focus: Emotional validation and connection
  
- Coach (0.4 ≤ intensity < 0.7): Validate + advise + optional exercise suggestion
  - "I understand. Here's what we can try together..."
  - Focus: Balanced support with gentle guidance
  
- Trainer (intensity ≥ 0.7): Validate + strongly recommend + guide through exercise
  - "Let's work through this. Here's exactly what we'll do..."
  - Focus: Active engagement and structured support
  
- Crisis Support (crisis_detected = true): Emergency resources, hotline numbers, safety
  - "I'm concerned about your safety. Here's immediate help..."
  - Focus: Crisis de-escalation and professional resources

DECISION LOGIC:
```
IF crisis_detected:
    role = "crisis_support"
ELIF intensity < 0.4:
    role = "friend"
ELIF intensity < 0.7:
    role = "coach"
ELSE:
    role = "trainer"
```
"""

from ..agent.state import MentalHealthState


def role_selector_node(state: MentalHealthState) -> dict:
    """
    ROLE SELECTOR NODE - Determine agent communication style.
    
    PROCESS:
    1. Check if crisis detected → crisis_support role
    2. Check emotional trend → escalate if worsening
    3. Get emotion intensity (prefer fused)
    4. Map intensity to role (friend/coach/trainer)
    5. Store role in state for response generator
    """
    
    try:
        # ============================================
        # EXTRACT DECISION INPUTS
        # ============================================
        
        crisis_detected = state.get("crisis_detected", False)
        intensity = state.get("fused_intensity", state.get("intensity", 0.5))
        emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        crisis_level = state.get("crisis_level", "low")
        trend = state.get("emotional_trend", "stable")
        phase = state.get("conversation_phase", "venting")

        if crisis_detected:
            agent_role = "crisis_support"
            print(f"[NODE:ROLE] 🚨 crisis_support (crisis_detected=True, level={crisis_level})")
        elif trend == "worsening" and intensity >= 0.6 and phase != "reflection":
            # Worsening + high intensity BUT not in reflection — user needs active support
            agent_role = "trainer"
            print(f"[NODE:ROLE] 📉 trainer (worsening trend + intensity={intensity:.0%}, phase={phase})")
        elif phase == "reflection":
            # User is actively reflecting — coach is appropriate, trainer would interrupt
            agent_role = "coach" if intensity >= 0.4 else "friend"
            print(f"[NODE:ROLE] 🤔 {agent_role} (reflection phase — listening mode, intensity={intensity:.0%})")
        elif intensity < 0.4:
            agent_role = "friend"
            print(f"[NODE:ROLE] 🤝 friend (intensity={intensity:.0%} < 0.4, low distress)")
        elif intensity < 0.7:
            agent_role = "coach"
            print(f"[NODE:ROLE] 👨‍🏫 coach (0.4 ≤ intensity={intensity:.0%} < 0.7)")
        else:
            agent_role = "trainer"
            print(f"[NODE:ROLE] 💪 trainer (intensity={intensity:.0%} ≥ 0.7, high distress)")

        print(f"[NODE:ROLE] 📊 Final: {agent_role.upper()} | Emotion: {emotion} | Phase: {phase} | Trend: {trend}")
        return {"agent_role": agent_role}
    
    except Exception as e:
        print(f"[NODE:ROLE] ❌ Error: {str(e)}")
        return {"agent_role": "coach"}
