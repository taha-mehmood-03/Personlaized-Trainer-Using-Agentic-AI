"""
Memory Builder  Combiner for distinct memory layers.

Storage roles:
  - Prisma/Supabase Postgres remains the source of truth for messages,
    explicit facts, summaries, analytics, and audits.
  - The lightweight local recall store is optional background context only.

Prompt roles:
  - Local recall can answer specific recall needs when available.
  - Prisma facts provide stable user preferences/identity/goals.
  - Prisma summaries are only injected for broad history questions or when
    local recall has no specific match, avoiding duplicated context.
  - Sliding window is current-session context only.
"""

import asyncio


def _is_broad_history_query(message: str) -> bool:
    """True when summaries are more useful than specific semantic snippets."""
    text = (message or "").lower()
    markers = (
        "last time",
        "previous",
        "before",
        "past session",
        "past sessions",
        "history",
        "what did we talk",
        "what have we talked",
        "summarize",
        "recap",
        "remember",
        "do you know me",
    )
    return any(marker in text for marker in markers)


async def build_full_memory_context(
    user_id: str,
    current_messages: list,
    include_window: bool = True,
    current_message: str = "",
    session_id: str = "",
) -> str:
    """
    Build complete memory context from all 3 layers for LLM prompt injection.

    Args:
        user_id: User identifier
        current_messages: Current session LangGraph messages list
        include_window: Whether to include sliding window (Layer 3)
        session_id: Current session ID to exclude from semantic cross-session
            recall. Current-session turns already live in LangGraph state.

    Returns:
        Single formatted string ready to inject into state['memory_context'].
        Never raises  returns empty string on any failure.
    """
    try:
        from .explicit_facts import get_user_facts
        from .session_summarizer import get_session_summaries
        from . import get_memory_context_for_prompt
        from .sliding_window import build_sliding_window, format_window_for_prompt

        # Fetch facts + summaries + local recall concurrently for speed.
        # We decide which sections to inject after retrieval, so storage remains
        # complete while prompt context stays non-duplicative.
        facts_task = asyncio.create_task(get_user_facts(user_id))
        summaries_task = asyncio.create_task(get_session_summaries(user_id))
        semantic_task = (
            asyncio.create_task(get_memory_context_for_prompt(
                user_id,
                current_message,
                max_memories=3,
                exclude_session_id=session_id or None,
            ))
            if current_message and current_message.strip()
            else None
        )

        facts_context = await facts_task
        summaries_context = await summaries_task
        semantic_context = await semantic_task if semantic_task else ""
        include_summaries = (
            bool(summaries_context)
            and (not semantic_context or _is_broad_history_query(current_message))
        )

        # Layer 3: Sliding window (synchronous  no DB)
        window_context = ""
        if include_window and current_messages:
            trimmed = build_sliding_window(current_messages)
            window_context = format_window_for_prompt(trimmed)

        # Combine non-empty sections. Do not include both specific semantic recall
        # and generic session summaries unless the user is explicitly asking for
        # broad history; that prevents the same old session from appearing twice.
        sections = []
        if semantic_context and semantic_context.strip():
            sections.append(semantic_context)
        if include_summaries:
            sections.append(summaries_context)
        if facts_context and facts_context.strip():
            sections.append(facts_context)
        if window_context and window_context.strip():
            sections.append(window_context)

        if not sections:
            return ""

        combined = "\n\n".join(sections)
        combined += "\n\nUse above as context. Do not repeat verbatim. Only reference if directly relevant."

        return combined

    except Exception as e:
        print(f"[MEMORY:BUILDER]  build_full_memory_context failed (non-fatal): {str(e)[:150]}")
        return ""
