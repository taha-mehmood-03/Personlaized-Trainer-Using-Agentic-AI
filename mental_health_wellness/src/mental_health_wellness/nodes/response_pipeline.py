"""
Response Pipeline Fused Node  SentiMind v6.0 Latency Optimization

Merges 2 separate graph nodes into a SINGLE LangGraph node to eliminate
2 checkpoint serialization events per message.

Sub-nodes called INLINE:
  1. technique_selector_node   DB query for best technique  (async, ~50ms)
  2. role_selector_node        pure Python role logic        (sync, <1ms)

The crisis routing conditional edge that was previously after technique_selector
now runs after this fused node (same logic, same state keys).
"""

from ..agent.state import MentalHealthState
from ..pipeline.technique_selector_node import select_technique
from ..pipeline.role_selector import select_agent_role


async def run_response_pipeline(state: MentalHealthState) -> dict:
    """
    FUSED NODE: technique_selector + role_selector.

    Runs both sub-nodes inline and merges their state updates.
    This eliminates 2 LangGraph checkpoint events.

    Returns: merged dict of both sub-nodes' outputs.
    """
    print("\n[NODE: RESPONSE_PIPELINE]  Running fused pipeline (technique + role)...")

    merged = {}

    #  1. Technique Selector (async, DB query ~50ms) 
    # Reads: conversation_strategy, technique_readiness, fused_emotion, fused_intensity, user_id
    # Writes: recommended_technique, recommended_techniques_by_category, alternative_techniques
    try:
        technique_result = await select_technique(state)
        merged.update(technique_result)
    except Exception as e:
        print(f"[RESPONSE_PIPELINE]  Technique selector failed: {str(e)[:100]}")
        merged.update({
            "recommended_technique": {},
            "recommended_techniques_by_category": {},
            "alternative_techniques": [],
        })

    # Create merged state view so role_selector sees technique results
    state_with_technique = {**state, **merged}

    #  2. Role Selector (sync, <1ms) 
    # Reads: crisis_detected, fused_intensity, fused_emotion, emotional_trend, conversation_phase
    # Writes: agent_role
    try:
        role_result = select_agent_role(state_with_technique)
        merged.update(role_result)
    except Exception as e:
        print(f"[RESPONSE_PIPELINE]  Role selector failed: {str(e)[:100]}")
        merged.update({"agent_role": "coach"})

    print(f"[NODE: RESPONSE_PIPELINE]  Fused complete | "
          f"Technique: {merged.get('recommended_technique', {}).get('name', 'none')} | "
          f"Role: {merged.get('agent_role', '?')}")

    return merged
