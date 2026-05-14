"""
Memory Builder  Combiner for all 3 memory layers.

Builds the complete memory_context string injected into every LLM prompt.
Combines:
  Layer 1: Explicit facts (Prisma UserFact)
  Layer 2: Session summaries (Prisma SessionSummary)
  Layer 3: Sliding window (current session messages, in-memory)
"""

import asyncio


async def build_full_memory_context(
    user_id: str,
    current_messages: list,
    include_window: bool = True
) -> str:
    """
    Build complete memory context from all 3 layers for LLM prompt injection.

    Args:
        user_id: User identifier
        current_messages: Current session LangGraph messages list
        include_window: Whether to include sliding window (Layer 3)

    Returns:
        Single formatted string ready to inject into state['memory_context'].
        Never raises  returns empty string on any failure.
    """
    try:
        from .explicit_facts import get_user_facts
        from .session_summarizer import get_session_summaries
        from .sliding_window import build_sliding_window, format_window_for_prompt

        # Fetch Layer 1 + Layer 2 concurrently for speed
        facts_task = asyncio.create_task(get_user_facts(user_id))
        summaries_task = asyncio.create_task(get_session_summaries(user_id))

        facts_context = await facts_task
        summaries_context = await summaries_task

        # Layer 3: Sliding window (synchronous  no DB)
        window_context = ""
        if include_window and current_messages:
            trimmed = build_sliding_window(current_messages)
            window_context = format_window_for_prompt(trimmed)

        # Combine non-empty sections
        # Session summaries FIRST so LLM reads cross-session context before current facts
        sections = [s for s in [summaries_context, facts_context, window_context] if s.strip()]

        if not sections:
            return ""

        combined = "\n\n".join(sections)
        combined += "\n\nUse above as context. Do not repeat verbatim. Only reference if directly relevant."

        return combined

    except Exception as e:
        print(f"[MEMORY:BUILDER]  build_full_memory_context failed (non-fatal): {str(e)[:150]}")
        return ""
