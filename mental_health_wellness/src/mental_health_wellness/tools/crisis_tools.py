"""
Crisis Tools - Safety assessment and resources with country-aware hotlines
"""

from langchain_core.tools import tool
from typing import Dict, Any, Optional

# Global crisis resources by country/region
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
            "name": "Aman Samaji Organization",
            "number": "+92-316-1550000",
            "available": "24/7",
            "call_text": "Call",
            "language": "Urdu & English"
        },
        "secondary_hotline": {
            "name": "AASRA Crisis Line",
            "number": "+92-333-2435639",
            "available": "24/7",
            "call_text": "Call",
            "language": "Urdu & English"
        },
        "tertiary_hotline": {
            "name": "Pakistan Mental Health Network",
            "number": "+92-42-37180109",
            "available": "Office Hours",
            "call_text": "Call"
        },
        "text_line": {
            "name": "Crisis Support via WhatsApp",
            "action": "WhatsApp Aman: +92-316-1550000",
            "available": "24/7",
            "supported": True
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


def get_crisis_resources(country_code: str = "US") -> Dict[str, Any]:
    """
    Get crisis resources for a specific country.
    Defaults to US resources if country not found.
    
    Args:
        country_code: ISO 3166-1 alpha-2 country code (e.g., 'US', 'PK', 'GB')
    
    Returns:
        Dictionary containing country-specific crisis resources
    """
    return CRISIS_RESOURCES_BY_COUNTRY.get(country_code.upper(), CRISIS_RESOURCES_BY_COUNTRY["US"])


@tool
def handle_crisis(message: str = "", reason: str = "General concern", country_code: Optional[str] = None) -> dict:
    """
    Assess crisis risk AND provide country-specific resources if needed.
    Use this tool IMMEDIATELY if you detect any intent of self-harm, suicide, or severe distress.
    
    Args:
        message: The user's message that triggered the crisis flag
        reason: Brief reason for flagging
        country_code: Optional ISO country code (e.g., 'US', 'PK', 'GB'). Defaults to 'US'
        
    Returns:
        Dictionary containing risk level, action, and country-specific resources.
    """
    try:
        print(f"[CRISIS_TOOL]  CRISIS HANDLER CALLED: {reason}")
        
        # Get country-specific resources (default to US if not provided)
        country = country_code or "US"
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
        fallback_resources = get_crisis_resources(country_code or "US")
        return {
            "risk_level": "high",
            "crisis_detected": True,
            "error": str(e),
            "action": "escalate",
            "reason": "Error in crisis detection - escalating for safety",
            "resources": fallback_resources
        }
