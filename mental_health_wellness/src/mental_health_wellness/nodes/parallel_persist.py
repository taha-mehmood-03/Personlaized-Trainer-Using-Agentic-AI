"""
Parallel Persist Node  SentiMind v5.2 Latency Optimization

Runs post-response write nodes in the background:
  - Psych Profile Updater (DB upsert, ~100ms)
  - Session Saver (DB write + mood log, ~100-200ms)
  - Outcome Tracker (DB write, ~30-80ms)
  - Long-Term Analytics (snapshot + aggregate dashboard refresh)

WHY THIS IS SAFE:
  All 3 nodes are WRITE-ONLY side-effect nodes that:
  - Read from the SAME frozen state (set by optimized_response_generator)
  - Write to DIFFERENT database tables
  - Write to DIFFERENT state keys

  The only subtle dependency: session_saver sets session_start_emotion
  and technique_delivery_emotion baselines that outcome_tracker reads.
  BUT outcome_tracker reads these from the PREVIOUS turn's state
  (already merged by LangGraph before this turn). On the current turn,
  saver is writing NEW baselines for the NEXT turn while tracker reads
  OLD baselines from the PREVIOUS turn  so they are independent.

BEFORE (sequential ~300ms):
  response  profile (100ms)  saver (100ms)  outcome (80ms)  END

AFTER (parallel ~120ms):
  response  parallel_persist (max(100, 100, 80) = ~120ms)  END
"""

import asyncio
import os
from ..agent.state import MentalHealthState
from .psych_profile_updater import update_psych_profile
from .session_saver import save_session, update_structured_session_handoff
from .outcome_tracker_node import track_outcome
from .long_term_analytics_node import update_long_term_analytics


async def _update_profile_with_background_distortion(state: MentalHealthState) -> dict:
    """
    Enrich profile analytics with cognitive distortion detection after the user
    already has a response. This keeps the LLM distortion call off the latency
    path while preserving long-term personalization data.
    """
    background_distortion = (
        os.getenv("SENTIMIND_BACKGROUND_LLM_ENABLED", "0").lower() in {"1", "true", "yes", "on"}
        or os.getenv("SENTIMIND_BACKGROUND_DISTORTION", "0").lower() in {"1", "true", "yes", "on"}
    )
    if not background_distortion or state.get("all_distortions"):
        return await update_psych_profile(state)

    try:
        from .cognitive_distortion_node import detect_cognitive_distortions

        distortion_result = await detect_cognitive_distortions(state)
        enriched_state = {**state, **(distortion_result or {})}
        if distortion_result and distortion_result.get("all_distortions"):
            print("[NODE: PARALLEL_PERSIST]  Background distortion enriched profile state")
        return await update_psych_profile(enriched_state)
    except Exception as e:
        print(f"[NODE: PARALLEL_PERSIST]  Background distortion skipped: {str(e)[:100]}")
        return await update_psych_profile(state)


async def run_parallel_persist(state: MentalHealthState) -> dict:
    """
    Run post-response persistence operations in the background.

    The first three writers can run concurrently. The analytics refresh then
    runs after session_saver has had a chance to create the turn's message and
    mood log, so dashboard aggregates are not one turn behind.

    Returns: merged dict of all nodes' state updates.
    Failures in any node are caught and logged  never crashes the pipeline.
    """
    print("\n[NODE: PARALLEL_PERSIST]  Running profile + saver + outcome concurrently...")

    profile_result, saver_result, outcome_result = await asyncio.gather(
        _update_profile_with_background_distortion(state),
        save_session(state),
        track_outcome(state),
        return_exceptions=True,
    )

    merged = {}

    # Profile updater
    if isinstance(profile_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST]  Profile updater failed: {str(profile_result)[:100]}")
    elif profile_result:
        merged.update(profile_result)

    # Session saver
    if isinstance(saver_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST]  Session saver failed: {str(saver_result)[:100]}")
        merged.update({
            "session_saved": False,
            "saved_session_id": None,
            "save_errors": [f"Parallel persist error: {str(saver_result)[:80]}"],
        })
    elif saver_result:
        merged.update(saver_result)

    # Outcome tracker
    if isinstance(outcome_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST]  Outcome tracker failed: {str(outcome_result)[:100]}")
    elif outcome_result:
        merged.update(outcome_result)

    analytics_result = await update_long_term_analytics({**state, **merged})
    if isinstance(analytics_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST]  Analytics refresh failed: {str(analytics_result)[:100]}")
    elif analytics_result:
        merged.update(analytics_result)

    handoff_result = await update_structured_session_handoff({**state, **merged})
    if isinstance(handoff_result, Exception):
        print(f"[NODE: PARALLEL_PERSIST]  Session handoff failed: {str(handoff_result)[:100]}")
    elif handoff_result:
        merged.update(handoff_result)

    errors = merged.get("save_errors", [])
    print(f"[NODE: PARALLEL_PERSIST]  Complete | "
          f"Saved: {merged.get('session_saved', '?')} | "
          f"Analytics: {merged.get('analytics_updated', False)} | "
          f"Errors: {len(errors)}")

    return merged
