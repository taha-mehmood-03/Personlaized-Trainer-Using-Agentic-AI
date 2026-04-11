"""
Parallel Persist Node — SentiMind v5.2 Latency Optimization

Runs all 3 post-response write nodes concurrently via asyncio.gather:
  - Psych Profile Updater (DB upsert, ~100ms)
  - Session Saver (DB write + mood log, ~100-200ms)
  - Outcome Tracker (DB write, ~30-80ms)

WHY THIS IS SAFE:
  All 3 nodes are WRITE-ONLY side-effect nodes that:
  - Read from the SAME frozen state (set by response_generator)
  - Write to DIFFERENT database tables
  - Write to DIFFERENT state keys

  The only subtle dependency: session_saver sets session_start_emotion
  and technique_delivery_emotion baselines that outcome_tracker reads.
  BUT outcome_tracker reads these from the PREVIOUS turn's state
  (already merged by LangGraph before this turn). On the current turn,
  saver is writing NEW baselines for the NEXT turn while tracker reads
  OLD baselines from the PREVIOUS turn — so they are independent.

BEFORE (sequential ~300ms):
  response → profile (100ms) → saver (100ms) → outcome (80ms) → END

AFTER (parallel ~120ms):
  response → parallel_persist (max(100, 100, 80) = ~120ms) → END
"""

import asyncio
from ..agent.state import MentalHealthState
from .psych_profile_updater import psych_profile_updater_node
from .session_saver import session_saver_node
from .outcome_tracker_node import outcome_tracker_node


async def parallel_persist_node(state: MentalHealthState) -> dict:
    """
    Run all post-response persistence operations concurrently.

    Returns: merged dict of all 3 nodes' state updates.
    Failures in any node are caught and logged — never crashes the pipeline.
    """
    print("\n[NODE: PARALLEL_PERSIST] ⚡ Running profile + saver + outcome concurrently...")

    profile_result, saver_result, outcome_result = await asyncio.gather(
        psych_profile_updater_node(state),
        session_saver_node(state),
        outcome_tracker_node(state),
        return_exceptions=True,
    )

    merged = {}

    # Profile updater
    if isinstance(profile_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST] ⚠️ Profile updater failed: {str(profile_result)[:100]}")
    elif profile_result:
        merged.update(profile_result)

    # Session saver
    if isinstance(saver_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST] ⚠️ Session saver failed: {str(saver_result)[:100]}")
        merged.update({
            "session_saved": False,
            "saved_session_id": None,
            "save_errors": [f"Parallel persist error: {str(saver_result)[:80]}"],
        })
    elif saver_result:
        merged.update(saver_result)

    # Outcome tracker
    if isinstance(outcome_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST] ⚠️ Outcome tracker failed: {str(outcome_result)[:100]}")
    elif outcome_result:
        merged.update(outcome_result)

    errors = merged.get("save_errors", [])
    print(f"[NODE: PARALLEL_PERSIST] ✅ Complete | "
          f"Saved: {merged.get('session_saved', '?')} | "
          f"Errors: {len(errors)}")

    return merged
