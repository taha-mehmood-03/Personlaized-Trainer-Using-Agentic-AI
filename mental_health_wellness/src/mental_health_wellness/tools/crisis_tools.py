"""
Crisis Tools - Safety assessment and resources
"""

from langchain_core.tools import tool


@tool
def handle_crisis(message: str = "", reason: str = "General concern") -> dict:
    """
    Assess crisis risk AND provide resources if needed.
    Use this tool IMMEDIATELY if you detect any intent of self-harm, suicide, or severe distress.
    
    Args:
        message: The user's message that triggered the crisis flag
        reason: Brief reason for flagging
        
    Returns:
        Dictionary containing risk level, action, and resources (if high risk).
    """
    try:
        print(f"[CRISIS_TOOL] 🚨 CRISIS HANDLER CALLED: {reason}")
        
        # Resources data to include if risk is verified
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
            },
            "international": {
                "name": "International Association for Suicide Prevention",
                "website": "https://www.iasp.info/resources/Crisis_Centres/"
            },
            "message": "Please reach out to these resources. Your life matters, and trained counselors are available 24/7 to help you through this."
        }

        # The Agent has already decided this IS a crisis by calling this tool.
        # We confirm high risk and return resources immediately.
        return {
            "risk_level": "high",
            "crisis_detected": True,
            "keywords_found": ["Agent Flagged"],
            "action": "escalate",
            "reason": reason or "User or agent indicated crisis",
            "resources": resources
        }

    except Exception as e:
        print(f"[CRISIS_TOOL] ❌ Error in handle_crisis: {str(e)[:100]}")
        # Always escalate on error - safety first
        return {
            "risk_level": "high",
            "crisis_detected": True,
            "error": str(e),
            "action": "escalate",
            "reason": "Error in crisis detection - escalating for safety",
            "resources": {
                "primary_hotline": {"name": "988", "number": "988"},
                "message": "Immediate help is available. Please call 988."
            }
        }
