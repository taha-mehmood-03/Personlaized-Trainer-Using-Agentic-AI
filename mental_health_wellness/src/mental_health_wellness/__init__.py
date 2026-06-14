"""
Mental Health Wellness - LangGraph Multi-Node Agent
A compassionate AI mental health support companion

Architecture:
    - Component-based with modular nodes
    - LangGraph StateGraph for conversation flow
    - Gemini LLM with key/model failover
    - PostgreSQL database via Prisma
"""

# Main agent exports
from .agent import (
    chat_with_agent,
    check_agent_health,
    get_agent,
    MentalHealthState,
    get_initial_state
)

# Re-export tools for convenience
from .tools import get_all_tools

__version__ = "2.0.0"
__all__ = [
    "chat_with_agent",
    "check_agent_health", 
    "get_agent",
    "MentalHealthState",
    "get_initial_state",
    "get_all_tools"
]
