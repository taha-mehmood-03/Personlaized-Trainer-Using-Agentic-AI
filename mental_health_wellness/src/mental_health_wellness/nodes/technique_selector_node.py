"""
Technique Selector Node - Deterministic Python-based technique selection

ARCHITECTURE NODE 3:
Purpose: Select best technique for detected emotion using database queries
Runs AFTER mood analyzer node, BEFORE response generator
No LLM call - pure database logic
"""

from ..agent.state import MentalHealthState
from ..tools.technique_tools import recommend_technique
import time


async def technique_selector_node(state: MentalHealthState) -> dict:
    """
    TECHNIQUE SELECTOR NODE - Deterministic technique selection.

    Process:
    1. Check planner strategy — skip if user not ready
    2. Get detected emotion + intensity from state (prefers fused values)
    3. Query database for top-3 techniques (intensity-routed, unused-first)
    4. primary = top 1, alternatives = items 2 & 3
    5. Store all in state for SSE streaming to frontend

    No LLM involved - pure database queries

    Output State:
        - recommended_technique:           Single best technique dict
        - recommended_techniques_by_category: {category: technique} (single entry, for UI compat)
        - alternative_techniques:          List of up to 2 alternative dicts
    """

    try:
        # ── Planner gating ───────────────────────────────────────────────────
        strategy = state.get("conversation_strategy", "validate_only")
        readiness = state.get("technique_readiness", 0.0)

        _empty = {
            "recommended_technique": {},
            "recommended_techniques_by_category": {},
            "alternative_techniques": [],
        }

        skip_strategies = {"validate_only", "ask_question", "encourage_reflection"}
        if strategy in skip_strategies:
            print(f"[TECHNIQUE] ⏭️ Skipping (strategy: {strategy}, readiness: {readiness:.0%})")
            return _empty

        if strategy == "no_action":
            print(f"[TECHNIQUE] ⏭️ Skipping (strategy: no_action — casual conversation)")
            return _empty

        if strategy in ["validate_only", "ask_question"] and readiness < 0.6:
            print(f"[TECHNIQUE] ⏭️ Skipping (not ready, readiness={readiness:.0%})")
            return _empty

        # ── Inputs ───────────────────────────────────────────────────────────
        emotion   = state.get("fused_emotion", state.get("emotion", "neutral"))
        intensity = state.get("fused_intensity", state.get("intensity", 0.5))
        user_id   = state.get("user_id", "")

        print(f"\n[TECHNIQUE] 🎯 emotion={emotion.upper()} intensity={intensity:.0%} strategy={strategy}")

        start_time = time.time()

        # ── Fetch top-3 (list) ───────────────────────────────────────────────
        top3: list = await recommend_technique.ainvoke({
            "emotion":   emotion,
            "intensity": intensity,
            "user_id":   user_id,
        })

        elapsed_ms = int((time.time() - start_time) * 1000)

        if not top3:
            print(f"[TECHNIQUE] ⚠️ No techniques found for {emotion} | Time: {elapsed_ms}ms")
            return _empty

        primary      = top3[0]
        alternatives = top3[1:]          # 0, 1, or 2 items

        cat_name = primary.get("category", "Recommended")
        print(f"[TECHNIQUE] ✅ Primary: {primary.get('name')} ({cat_name}) "
              f"| Alternatives: {[t.get('name') for t in alternatives]} "
              f"| Time: {elapsed_ms}ms")

        return {
            "recommended_technique":            primary,
            "recommended_techniques_by_category": {cat_name: primary},
            "alternative_techniques":            alternatives,
        }

    except Exception as e:
        print(f"[TECHNIQUE] ❌ Error: {str(e)[:80]}")
        return {
            "recommended_technique": {},
            "recommended_techniques_by_category": {},
            "alternative_techniques": [],
        }
