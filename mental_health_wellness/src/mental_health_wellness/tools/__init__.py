from .mood_tools import analyze_mood
from .voice_tools import analyze_voice
from .crisis_tools import handle_crisis
from .technique_tools import recommend_technique
from .user_tools import get_user_history, save_session

__all__ = [
    "analyze_mood",
    "analyze_voice",
    "handle_crisis",
    "recommend_technique",
    "get_user_history",
    "save_session",
    "get_all_tools"
]

def get_all_tools():
    """Return list of all tools for the agent."""
    return [
        analyze_mood,
        analyze_voice,
        recommend_technique,
        get_user_history
    ]
