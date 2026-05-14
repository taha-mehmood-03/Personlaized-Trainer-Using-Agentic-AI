"""
Layer 3: Sliding Window Memory
Current session context management  no DB needed.

Keeps a trimmed view of the current session messages within token budget.
Preserves the first message (context anchor) + most recent messages.
"""

from typing import List

MAX_MESSAGES = 20


def build_sliding_window(messages: list, max_messages: int = MAX_MESSAGES) -> list:
    """
    Build a trimmed message list staying within the max token budget.

    Strategy:
    - If total messages <= max: return all
    - Else: keep first message (context anchor) + most recent (max-1) messages

    Args:
        messages: LangGraph message list (HumanMessage / AIMessage objects)
        max_messages: Maximum number of messages to keep

    Returns:
        Trimmed message list
    """
    if not messages:
        return []

    if len(messages) <= max_messages:
        return messages

    # Keep first message as context anchor + most recent
    return [messages[0]] + messages[-(max_messages - 1):]


def format_window_for_prompt(messages: list) -> str:
    """
    Format a message list as a readable conversation window for the LLM prompt.

    Returns:
        Formatted string like:
        CURRENT SESSION:
        You: I feel anxious about my exam
        SentiMind: I hear you. Exam stress can feel really overwhelming...
        Or empty string if no messages.
    """
    if not messages:
        return ""

    lines = ["CURRENT SESSION:"]
    for msg in messages:
        # Support both LangGraph message objects and raw dicts
        role = getattr(msg, "type", None) or getattr(msg, "role", "")
        content = getattr(msg, "content", "") or msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")

        if not content:
            continue

        # Truncate long messages to avoid token bloat
        text = str(content).strip()
        if len(text) > 200:
            text = text[:197] + "..."

        if role in ("human", "user"):
            lines.append(f"You: {text}")
        elif role in ("ai", "assistant"):
            lines.append(f"SentiMind: {text}")

    if len(lines) == 1:  # Only header, no messages
        return ""

    return "\n".join(lines)
