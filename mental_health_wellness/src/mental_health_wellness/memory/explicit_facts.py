"""
Layer 1: Explicit Facts Memory
ChatGPT-style explicit fact extraction and retrieval.

Extracts structured facts from user messages using Gemini LLM and persists them
to the Prisma UserFact table. Max 33 facts per user (like ChatGPT's memory limit).
Supports CORRECTIONS: if user says "im not X im Y", the wrong fact is deleted
and replaced with the corrected one automatically.
"""

import json
import asyncio
import os
from typing import Optional
from datetime import datetime, timezone, timedelta

MAX_FACTS = 33
FACT_CATEGORIES = {"identity", "preference", "goal", "clinical", "context"}


def _retention_until(days: int = 365):
    return datetime.now(timezone.utc) + timedelta(days=days)


async def extract_and_save_facts(
    user_id: str,
    message: str,
    session_id: str = ""
) -> None:
    """
    Extract facts from a user message and save new ones to the DB.
    Handles CORRECTIONS: if user says "im not X im Y", the wrong fact is deleted.
    Runs as a background asyncio.create_task() -- never blocks the pipeline.

    The LLM is the sole judge of whether a message contains a storable fact.
    Only truly empty / single-token messages are skipped without an LLM call.
    """
    # Skip completely empty messages only — LLM handles everything else
    if not message or not message.strip() or len(message.strip()) < 3:
        return

    background_enabled = (
        os.getenv("SENTIMIND_BACKGROUND_LLM_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
        or os.getenv("SENTIMIND_BACKGROUND_FACT_EXTRACTION", "0").lower() in {"1", "true", "yes", "on"}
    )
    if not background_enabled:
        print("[MEMORY:FACTS] Extraction skipped (background LLM disabled)")
        return

    try:
        from ..db.client import get_prisma_client
        from ..llm.groq_llm import get_llm_manager, message_content_to_text

        manager = get_llm_manager()

        prompt = (
            "You are a memory extraction system for a mental health chatbot.\n"
            "Extract ONLY clear, lasting personal facts from this user message. Return a JSON array of objects.\n\n"
            f"Message: \"{message}\"\n\n"
            "Rules:\n"
            "- Only extract facts that are stable and meaningful (name, job, goals, health conditions, preferences)\n"
            "- Do NOT extract momentary emotions (e.g. feeling sad today)\n"
            "- Return [] if no extractable facts present\n"
            "- Each fact must have:\n"
            "    fact     : one clear sentence (e.g. User name is Taha Mehmood)\n"
            "    category : one of: identity, preference, goal, clinical, context\n"
            "    corrects : (optional) the WRONG value being corrected, as a short string.\n"
            "               ONLY include if user is explicitly correcting a previous statement.\n"
            "               Example: user says im not taram im taha -> corrects: taram\n"
            "- Maximum 3 facts per message\n\n"
            "CORRECTION EXAMPLES:\n"
            "- im not taram im taha mehmood -> [{fact: Users name is Taha Mehmood, category: identity, corrects: taram}]\n"
            "- my name is not sara its samira -> [{fact: Users name is Samira, category: identity, corrects: sara}]\n"
            "- i prefer short replies not long -> [{fact: User prefers short concise responses, category: preference}]\n\n"
            "Return ONLY valid JSON array."
        )

        from langchain_core.messages import HumanMessage
        # FIXED: was llm.invoke() (sync, blocks event loop) → now await ainvoke()
        if hasattr(manager, "ainvoke_gemini_with_rotation"):
            response = await manager.ainvoke_gemini_with_rotation(
                [HumanMessage(content=prompt)],
                model=getattr(manager, "model_mood", None),
                max_tokens=512,
                temperature=0.0,
            )
        else:
            llm = manager.get_llm(model=getattr(manager, "model_mood", None))
            response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = message_content_to_text(response.content if hasattr(response, "content") else response).strip()
        
        try:
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            facts = json.loads(raw.strip())
            if not isinstance(facts, list):
                facts = []
        except Exception:
            return

        if not facts:
            return

        prisma = await get_prisma_client()
        current_count = await prisma.userfact.count(where={"userId": user_id})

        existing = await prisma.userfact.find_many(where={"userId": user_id})
        existing_map = {f.fact.lower().strip(): f.id for f in existing}

        saved = 0
        deleted = 0

        for item in facts:
            if not isinstance(item, dict):
                continue
            fact_text = item.get("fact", "").strip()
            category = item.get("category", "context").lower()
            corrects = item.get("corrects", "").strip().lower()

            if category not in FACT_CATEGORIES:
                category = "context"

            if not fact_text:
                continue

            # Handle correction: delete wrong facts before saving the right one
            if corrects:
                for existing_text, fact_id in list(existing_map.items()):
                    if corrects in existing_text:
                        try:
                            await prisma.userfact.delete(where={"id": fact_id})
                            del existing_map[existing_text]
                            current_count -= 1
                            deleted += 1
                            print(f"[MEMORY:FACTS] Deleted wrong fact (contained {corrects!r}): {existing_text[:60]}")
                        except Exception as del_err:
                            print(f"[MEMORY:FACTS] Could not delete wrong fact: {del_err}")

            # Skip near-duplicates
            if fact_text.lower() in existing_map:
                continue

            if current_count + saved >= MAX_FACTS:
                break

            created_fact = await prisma.userfact.create(data={
                "userId": user_id,
                "fact": fact_text,
                "category": category,
                "sensitivity": "PHI" if category == "clinical" else "SENSITIVE",
                "legalBasis": "HEALTH_CARE" if category == "clinical" else "CONSENT",
                "retentionUntil": _retention_until(2555 if category == "clinical" else 365),
            })
            try:
                from . import store_fact_embedding

                asyncio.create_task(store_fact_embedding(user_id, created_fact.id, fact_text, category))
            except Exception:
                pass
            existing_map[fact_text.lower()] = "new"
            saved += 1

        if saved > 0 or deleted > 0:
            try:
                from ..services.cache_state import invalidate_user_cache

                invalidate_user_cache(user_id)
            except Exception as cache_err:
                print(f"[MEMORY:FACTS] Cache invalidation skipped: {str(cache_err)[:100]}")
            print(f"[MEMORY:FACTS] Facts updated for {user_id[:12]}... | Saved: {saved} | Corrected: {deleted}")

    except Exception as e:
        print(f"[MEMORY:FACTS] extract_and_save_facts failed (non-fatal): {str(e)[:120]}")


async def get_user_facts(user_id: str) -> str:
    """
    Retrieve all stored facts for a user, formatted for prompt injection.
    Deduplicates conflicting facts by semantic key  newest fact wins.

    Returns:
        Formatted string like:
        WHAT I KNOW ABOUT YOU:
        - User name is Taha Mehmood  [identity]
        Or empty string if no facts.
    """
    try:
        from ..db.client import get_prisma_client
        prisma = await get_prisma_client()

        # Fetch newest first so dedup keeps the most recent when there's a conflict
        facts = await prisma.userfact.find_many(
            where={"userId": user_id},
            order={"createdAt": "desc"}
        )

        if not facts:
            return ""

        # Semantic dedup keys  if two facts share the same key word, only keep the newest
        DEDUP_KEYS = ["name", "age", "years old", "job", "work", "profession",
                      "study", "university", "school", "college"]

        seen_keys: set[str] = set()
        deduped_facts: list = []

        for f in facts:
            fact_lower = f.fact.lower()
            matched_key = next((k for k in DEDUP_KEYS if k in fact_lower), None)
            if matched_key:
                if matched_key in seen_keys:
                    # Older conflicting fact  skip it
                    continue
                seen_keys.add(matched_key)
            deduped_facts.append(f)

        # Re-sort to chronological for readable output
        deduped_facts.sort(key=lambda f: f.createdAt)

        by_category: dict[str, list[str]] = {}
        for f in deduped_facts:
            cat = f.category or "context"
            by_category.setdefault(cat, []).append(f.fact)

        lines = ["WHAT I KNOW ABOUT YOU:"]
        for cat in ["identity", "preference", "goal", "clinical", "context"]:
            for fact in by_category.get(cat, []):
                lines.append(f"- {fact}  [{cat}]")

        return "\n".join(lines)

    except Exception as e:
        print(f"[MEMORY:FACTS] get_user_facts failed (non-fatal): {str(e)[:120]}")
        return ""
