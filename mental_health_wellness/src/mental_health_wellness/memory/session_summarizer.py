"""
Layer 2: Session Summarizer Memory
ChatGPT-style session summaries with rolling window.

Generates concise summaries of past sessions using Gemini LLM and stores them
in the Prisma SessionSummary table. Max 15 summaries  oldest deleted first.
"""

import asyncio
import os
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
    Generate a concise session summary using Gemini LLM and save to DB.
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
        background_enabled = (
            os.getenv("SENTIMIND_BACKGROUND_LLM_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
            or os.getenv("SENTIMIND_BACKGROUND_SESSION_SUMMARY", "0").lower() in {"1", "true", "yes", "on"}
        )
        if not background_enabled:
            print("[MEMORY:SUMMARIES] Summary skipped (background LLM disabled)")
            return

        from ..db.client import get_prisma_client
        from ..llm.groq_llm import get_llm_manager, message_content_to_text
        from langchain_core.messages import HumanMessage as LCHuman

        techniques = techniques or []

        # Extract ONLY user messages for summarization (per spec)
        user_texts = []
        for msg in messages:
            role = getattr(msg, "type", None) or getattr(msg, "role", "")
            if role in ("human", "user"):
                content = message_content_to_text(getattr(msg, "content", ""))
                if content and content.strip():
                    user_texts.append(content.strip())

        if not user_texts:
            return

        combined = "\n".join(f"- {t}" for t in user_texts[-10:])  # Last 10 user turns

        # Build LLM summary
        manager = get_llm_manager()
        prompt = f"""You are a clinical session note writer for a mental health chatbot.
Write a concise session summary based ONLY on these user messages.

User messages:
{combined}

Return a JSON object with:
- "title": 5-word session title (e.g. "Managing Work Deadline Anxiety")
- "summary": 2 sentence digest of what the user discussed and any resolution

Return ONLY valid JSON: {{"title": "...", "summary": "..."}}"""

        from langchain_core.messages import HumanMessage
        if hasattr(manager, "invoke_gemini_with_rotation"):
            response = manager.invoke_gemini_with_rotation(
                [HumanMessage(content=prompt)],
                model=getattr(manager, "model_mood", None),
                max_tokens=512,
                temperature=0.0,
                response_format={"type": "json_object"},
                response_format_models=[
                    getattr(manager, "model_mood", None),
                    getattr(manager, "model_alt", None),
                ],
            )
        else:
            llm = manager.get_llm(model=getattr(manager, "model_mood", None))
            response = llm.invoke([HumanMessage(content=prompt)])
        raw = message_content_to_text(response.content if hasattr(response, "content") else response).strip()

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
        created_summary = await prisma.sessionsummary.create(data={
            "userId": user_id,
            "sessionId": session_id,
            "title": title,
            "summary": summary,
            "emotion": emotion,
            "techniques": tech_names,
            "outcome": outcome,
        })
        try:
            from . import store_session_summary_embedding

            asyncio.create_task(store_session_summary_embedding(
                user_id=user_id,
                session_id=session_id,
                summary_id=created_summary.id,
                title=title,
                summary=summary,
                emotion=emotion,
            ))
        except Exception:
            pass

        try:
            from ..services.cache_state import invalidate_user_cache

            invalidate_user_cache(user_id, session_id=session_id)
        except Exception as cache_err:
            print(f"[MEMORY:SUMMARIES] Cache invalidation skipped: {str(cache_err)[:100]}")

        print(f"[MEMORY:SUMMARIES]  Saved session summary: '{title}'")

    except Exception as e:
        print(f"[MEMORY:SUMMARIES]  summarize_session failed (non-fatal): {str(e)[:150]}")


async def get_session_summaries(user_id: str, exclude_session_id: str | None = None) -> str:
    """
    Retrieve past session summaries for a user, formatted for prompt injection.

    Args:
        user_id: The user whose summaries to load.
        exclude_session_id: If provided, summaries from this session are excluded.
                            Pass the current session_id to prevent the active session
                            from contaminating its own gate/context with its own history.

    Returns:
        Formatted string of past sessions, or empty string.
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        where: dict = {"userId": user_id}
        if exclude_session_id:
            where["sessionId"] = {"not": exclude_session_id}

        summaries = await prisma.sessionsummary.find_many(
            where=where,
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
