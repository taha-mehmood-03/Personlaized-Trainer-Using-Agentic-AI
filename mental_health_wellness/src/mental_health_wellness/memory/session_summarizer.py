"""
Layer 2: Session Summarizer Memory
ChatGPT-style session summaries with rolling window.

Generates concise summaries of past sessions using Groq LLM and stores them
in the Prisma SessionSummary table. Max 15 summaries  oldest deleted first.
"""

import asyncio
from datetime import datetime
from typing import Optional

MAX_SUMMARIES = 15


async def summarize_session(
    user_id: str,
    session_id: str,
    messages: list,
    emotion: str = "neutral",
    techniques: list = None,
    outcome: str = "neutral"
) -> None:
    """
    Generate a concise session summary using Groq LLM and save to DB.
    Must always be called via asyncio.create_task()  never awaited directly.

    Args:
        user_id: User identifier
        session_id: Session being summarized
        messages: LangGraph messages list (HumanMessage/AIMessage)
        emotion: Dominant emotion detected this session
        techniques: List of technique names used
        outcome: "helped", "neutral", or "no_change"
    """
    try:
        from ..db.client import get_prisma_client
        from ..llm.groq_llm import get_llm_manager
        from langchain_core.messages import HumanMessage as LCHuman

        techniques = techniques or []

        # Extract ONLY user messages for summarization (per spec)
        user_texts = []
        for msg in messages:
            role = getattr(msg, "type", None) or getattr(msg, "role", "")
            if role in ("human", "user"):
                content = getattr(msg, "content", "")
                if content and content.strip():
                    user_texts.append(content.strip())

        if not user_texts:
            return

        combined = "\n".join(f"- {t}" for t in user_texts[-10:])  # Last 10 user turns

        # Build LLM summary
        manager = get_llm_manager()
        llm = manager.get_llm()

        prompt = f"""You are a clinical session note writer for a mental health chatbot.
Write a concise session summary based ONLY on these user messages.

User messages:
{combined}

Return a JSON object with:
- "title": 5-word session title (e.g. "Managing Work Deadline Anxiety")
- "summary": 2 sentence digest of what the user discussed and any resolution

Return ONLY valid JSON: {{"title": "...", "summary": "..."}}"""

        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        # Parse JSON
        import json
        try:
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw.strip())
            title = parsed.get("title", "Session Summary")[:100]
            summary = parsed.get("summary", "User discussed their feelings.")[:500]
        except Exception:
            title = f"Session - {emotion.capitalize()}"
            summary = f"User discussed issues related to {emotion}."

        prisma = await get_prisma_client()

        # Enforce rolling window  delete oldest if at limit
        current_count = await prisma.sessionsummary.count(where={"userId": user_id})
        if current_count >= MAX_SUMMARIES:
            oldest = await prisma.sessionsummary.find_first(
                where={"userId": user_id},
                order={"createdAt": "asc"}
            )
            if oldest:
                await prisma.sessionsummary.delete(where={"id": oldest.id})
                print(f"[MEMORY:SUMMARIES]  Deleted oldest summary to make room")

        # Save new summary
        tech_names = [str(t) for t in techniques] if techniques else []
        await prisma.sessionsummary.create(data={
            "userId": user_id,
            "sessionId": session_id,
            "title": title,
            "summary": summary,
            "emotion": emotion,
            "techniques": tech_names,
            "outcome": outcome,
        })

        print(f"[MEMORY:SUMMARIES]  Saved session summary: '{title}'")

    except Exception as e:
        print(f"[MEMORY:SUMMARIES]  summarize_session failed (non-fatal): {str(e)[:150]}")


async def get_session_summaries(user_id: str) -> str:
    """
    Retrieve past session summaries for a user, formatted for prompt injection.

    Returns:
        Formatted string of past sessions, or empty string.
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        summaries = await prisma.sessionsummary.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"},
            take=MAX_SUMMARIES
        )

        if not summaries:
            return ""

        lines = ["RECENT SESSION HISTORY (most recent first):"]
        for s in summaries:  # Already ordered desc (newest first) from the DB query
            date_str = s.createdAt.strftime("%b %d") if s.createdAt else "Recent"
            lines.append(f" {date_str}  {s.title}")
            lines.append(f"  {s.summary}")
            parts = [f"Emotion: {s.emotion}"]
            if s.techniques:
                parts.append(f"Techniques: {', '.join(s.techniques)}")
            parts.append(f"Outcome: {s.outcome}")
            lines.append(f"  {' | '.join(parts)}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[MEMORY:SUMMARIES]  get_session_summaries failed (non-fatal): {str(e)[:120]}")
        return ""
