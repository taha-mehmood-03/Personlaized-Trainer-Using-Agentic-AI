"""
Layer 1: Explicit Facts Memory
ChatGPT-style explicit fact extraction and retrieval.

Extracts structured facts from user messages using Groq LLM and persists them
to the Prisma UserFact table. Max 33 facts per user (like ChatGPT's memory limit).
"""

import json
import asyncio
from typing import Optional

MAX_FACTS = 33
FACT_CATEGORIES = {"identity", "preference", "goal", "clinical", "context"}


async def extract_and_save_facts(
    user_id: str,
    message: str,
    session_id: str = ""
) -> None:
    """
    Extract facts from a user message and save new ones to the DB.
    Runs as a background asyncio.create_task() — never blocks the pipeline.

    Rules:
    - Only extract clear, lasting facts (not momentary emotions)
    - Skip duplicates (case-insensitive match)
    - Respect MAX_FACTS = 33 limit
    - Never crash the pipeline — all errors logged and swallowed
    """
    try:
        from ..db.client import get_prisma_client
        from ..llm.groq_llm import get_llm_manager

        # Use a cheap fast model for fact extraction
        manager = get_llm_manager()
        llm = manager.get_llm()

        prompt = f"""You are a memory extraction system for a mental health chatbot.
Extract ONLY clear, lasting personal facts from this user message. Return a JSON array of objects.

Message: "{message}"

Rules:
- Only extract facts that are stable and meaningful (name, job, goals, health conditions, preferences)
- Do NOT extract momentary emotions or things said once (e.g. "feeling sad today")
- Return [] if no extractable facts present
- Each fact must have: "fact" (one sentence) and "category" (one of: identity, preference, goal, clinical, context)
- Maximum 3 facts per message

Return ONLY valid JSON like: [{{"fact": "User name is Alex", "category": "identity"}}]"""

        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        # Parse JSON safely
        try:
            # Strip markdown code fences if present
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            facts = json.loads(raw.strip())
            if not isinstance(facts, list):
                facts = []
        except Exception:
            return  # Malformed JSON — skip silently

        if not facts:
            return

        prisma = await get_prisma_client()

        # Get current fact count
        current_count = await prisma.userfact.count(where={"userId": user_id})
        if current_count >= MAX_FACTS:
            print(f"[MEMORY:FACTS] ⚠️ At limit ({MAX_FACTS} facts). Skipping extraction.")
            return

        # Get existing facts for dedup check
        existing = await prisma.userfact.find_many(where={"userId": user_id})
        existing_texts = {f.fact.lower().strip() for f in existing}

        saved = 0
        for item in facts:
            if not isinstance(item, dict):
                continue
            fact_text = item.get("fact", "").strip()
            category = item.get("category", "context").lower()
            if category not in FACT_CATEGORIES:
                category = "context"

            if not fact_text:
                continue

            # Skip near-duplicates
            if fact_text.lower() in existing_texts:
                continue

            # Check limit again before each save
            if current_count + saved >= MAX_FACTS:
                break

            await prisma.userfact.create(data={
                "userId": user_id,
                "fact": fact_text,
                "category": category,
            })
            existing_texts.add(fact_text.lower())
            saved += 1

        if saved > 0:
            print(f"[MEMORY:FACTS] ✅ Saved {saved} new fact(s) for user {user_id[:12]}...")

    except Exception as e:
        print(f"[MEMORY:FACTS] ⚠️ extract_and_save_facts failed (non-fatal): {str(e)[:120]}")


async def get_user_facts(user_id: str) -> str:
    """
    Retrieve all stored facts for a user, formatted for prompt injection.

    Returns:
        Formatted string like:
        WHAT I KNOW ABOUT YOU:
        • User name is Taha Khan  [identity]
        • User prefers direct communication  [preference]
        Or empty string if no facts.
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        facts = await prisma.userfact.find_many(
            where={"userId": user_id},
            order={"createdAt": "asc"}
        )

        if not facts:
            return ""

        # Group by category for cleaner output
        by_category: dict[str, list[str]] = {}
        for f in facts:
            cat = f.category or "context"
            by_category.setdefault(cat, []).append(f.fact)

        lines = ["WHAT I KNOW ABOUT YOU:"]
        # Priority order: identity first
        for cat in ["identity", "preference", "goal", "clinical", "context"]:
            for fact in by_category.get(cat, []):
                lines.append(f"• {fact}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[MEMORY:FACTS] ⚠️ get_user_facts failed (non-fatal): {str(e)[:120]}")
        return ""
