"""
Crisis Tools - Safety assessment and resources with country-aware hotlines
"""

from langchain_core.tools import tool
from typing import Dict, Any, Optional

# Global crisis resources by country/region
DEFAULT_CRISIS_COUNTRY = "PK"


CRISIS_RESOURCES_BY_COUNTRY: Dict[str, Dict[str, Any]] = {
    "US": {
        "primary_hotline": {
            "name": "988 Suicide & Crisis Lifeline",
            "number": "988",
            "available": "24/7",
            "call_text": "Call or text"
        },
        "text_line": {
            "name": "Crisis Text Line",
            "action": "Text HOME to 741741",
            "available": "24/7",
            "supported": True
        },
        "international": {
            "name": "International Association for Suicide Prevention",
            "website": "https://www.iasp.info/resources/Crisis_Centres/"
        }
    },
    "CA": {
        "primary_hotline": {
            "name": "Canada Suicide Prevention Service",
            "number": "1-833-456-4566",
            "available": "24/7",
            "call_text": "Call or text"
        },
        "text_line": {
            "name": "Crisis Text Line Canada",
            "action": "Text HELLO to 741741",
            "available": "24/7",
            "supported": True
        }
    },
    "PK": {
        "primary_hotline": {
            "name": "Umang Pakistan Mental Health Helpline",
            "number": "+92-311-7786264",
            "available": "24/7",
            "call_text": "Call",
            "language": "Urdu & English"
        },
        "secondary_hotline": {
            "name": "Rescue / Ambulance",
            "number": "1122",
            "available": "24/7",
            "call_text": "Call",
            "language": "Pakistan emergency service"
        },
        "tertiary_hotline": {
            "name": "Police Emergency",
            "number": "15",
            "available": "24/7",
            "call_text": "Call",
        },
        "emergency_service": {
            "name": "Edhi Ambulance",
            "number": "115",
            "available": "24/7",
            "call_text": "Call",
        },
        "text_line": {
            "name": "Crisis Support via WhatsApp",
            "action": "WhatsApp Umang: +92-311-7786264",
            "available": "24/7",
            "supported": True
        },
        "international": {
            "name": "International Association for Suicide Prevention",
            "website": "https://www.iasp.info/resources/Crisis_Centres/"
        },
        "message": (
            "If someone is in immediate physical danger in Pakistan, call Rescue/Ambulance 1122, "
            "Police 15, or Edhi Ambulance 115. For mental-health crisis support, contact Umang at "
            "+92-311-7786264."
        ),
        "disclaimer": {
            "text": (
                "SentiMind is supportive wellness software, not an emergency response service. "
                "Use local emergency services for immediate danger."
            )
        }
    },
    "GB": {
        "primary_hotline": {
            "name": "Samaritans UK",
            "number": "116 123",
            "available": "24/7",
            "call_text": "Call"
        },
        "text_line": {
            "name": "Crisis Text Line UK",
            "action": "Text SHOUT to 85258",
            "available": "24/7",
            "supported": True
        }
    },
    "AU": {
        "primary_hotline": {
            "name": "Lifeline Australia",
            "number": "13 11 14",
            "available": "24/7",
            "call_text": "Call"
        },
        "text_line": {
            "name": "Crisis Text Line Australia",
            "action": "Text 0466 423 111",
            "available": "24/7",
            "supported": True
        }
    }
}


def get_crisis_resources(country_code: str = DEFAULT_CRISIS_COUNTRY) -> Dict[str, Any]:
    """
    Get crisis resources for a specific country.
    Defaults to Pakistan resources if country not found.
    
    Args:
        country_code: ISO 3166-1 alpha-2 country code (e.g., 'US', 'PK', 'GB')
    
    Returns:
        Dictionary containing country-specific crisis resources
    """
    normalized = (country_code or DEFAULT_CRISIS_COUNTRY).upper()
    return CRISIS_RESOURCES_BY_COUNTRY.get(
        normalized,
        CRISIS_RESOURCES_BY_COUNTRY[DEFAULT_CRISIS_COUNTRY],
    )


@tool
def handle_crisis(message: str = "", reason: str = "General concern", country_code: Optional[str] = None) -> dict:
    """
    Assess crisis risk AND provide country-specific resources if needed.
    Use this tool IMMEDIATELY if you detect any intent of self-harm, suicide, or severe distress.
    
    Args:
        message: The user's message that triggered the crisis flag
        reason: Brief reason for flagging
        country_code: Optional ISO country code (e.g., 'US', 'PK', 'GB'). Defaults to 'PK'
        
    Returns:
        Dictionary containing risk level, action, and country-specific resources.
    """
    try:
        print(f"[CRISIS_TOOL]  CRISIS HANDLER CALLED: {reason}")
        
        # Get country-specific resources (default to Pakistan if not provided)
        country = country_code or DEFAULT_CRISIS_COUNTRY
        resources = get_crisis_resources(country)
        print(f"[CRISIS_TOOL]  Using resources for: {country}")
        
        # Add international resource as fallback
        if "international" not in resources:
            resources["international"] = {
                "name": "International Association for Suicide Prevention",
                "website": "https://www.iasp.info/resources/Crisis_Centres/"
            }
        
        resources["message"] = f"Please reach out to these resources. Your life matters, and trained counselors are available 24/7 to help you through this. (Resources for {country})"

        # The Agent has already decided this IS a crisis by calling this tool.
        # We confirm high risk and return resources immediately.
        return {
            "risk_level": "high",
            "crisis_detected": True,
            "country_code": country,
            "keywords_found": ["Agent Flagged"],
            "action": "escalate",
            "reason": reason or "User or agent indicated crisis",
            "resources": resources
        }

    except Exception as e:
        print(f"[CRISIS_TOOL]  Error in handle_crisis: {str(e)[:100]}")
        # Always escalate on error - safety first
        fallback_resources = get_crisis_resources(country_code or DEFAULT_CRISIS_COUNTRY)
        return {
            "risk_level": "high",
            "crisis_detected": True,
            "error": str(e),
            "action": "escalate",
            "reason": "Error in crisis detection - escalating for safety",
            "resources": fallback_resources
        }
