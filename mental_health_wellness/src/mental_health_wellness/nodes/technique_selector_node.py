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
    2. Get detected emotion from mood analyzer (or fused emotion)
    3. Query database for best techniques per category
    4. Select single primary technique
    5. Store structured technique data in state
    
    No LLM involved - pure database queries
    
    Input State:
        - emotion: From mood analyzer
        - fused_emotion: From emotion fusion (preferred)
        - conversation_strategy: From planner
        - technique_readiness: From planner
        - user_id: For personalization (avoid recently recommended)
    
    Output State:
        - recommended_technique: Single best technique dict
        - recommended_techniques_by_category: All 6 categories with best technique
    """
    
    try:
        # ============================================
        # PLANNER GATING: Respect conversation strategy
        # ============================================
        strategy = state.get("conversation_strategy", "validate_only")
        readiness = state.get("technique_readiness", 0.0)
        
        skip_strategies = {"validate_only", "ask_question", "encourage_reflection"}
        if strategy in skip_strategies:
            print(f"[TECHNIQUE] ⏭️ Skipping (planner strategy: {strategy}, readiness: {readiness:.0%})")
            return {
                "recommended_technique": {},
                "recommended_techniques_by_category": {}
            }
        
        # Prefer fused emotion, fall back to raw text emotion
        emotion = state.get("fused_emotion", state.get("emotion", "neutral"))
        user_id = state.get("user_id", "")
        
        print(f"\n[TECHNIQUE] 🎯 Selecting for emotion: {emotion.upper()} (strategy: {strategy})")

        # ============================================
        # FIX: CHITCHAT/NO_ACTION BYPASS (Audit Finalization)
        # If the planner decided on no_action (e.g., casual greeting or grocery list),
        # there is absolutely no need to query the database for CBT techniques.
        # This saves ~1.5-3.5 seconds of query latency on neutral messages.
        # ============================================
        if strategy == "no_action":
            print(f"[TECHNIQUE] ⏭️  Skipping technique search (strategy: no_action — casual conversation)")
            return {
                "recommended_technique": {},
                "recommended_techniques_by_category": {}
            }

        # Decide if we MIGHT use a technique
        # We load them anyway if readiness is high enough, even for 'reframe'
        if strategy in ["validate_only", "ask_question"] and readiness < 0.6:
            print(f"[TECHNIQUE] ⏭️  Skipping (strategy indicates not ready for technique)")
            return {
                "recommended_technique": {},
                "recommended_techniques_by_category": {}
            }
            
        start_time = time.time()
        
        # Get all best techniques by category
        techniques_by_category = await recommend_technique.ainvoke({
            "emotion": emotion,
            "user_id": user_id
        })
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # Select primary technique (highest rated from available)
        recommended_technique = {}
        if techniques_by_category:
            # Get first (best rated) technique
            primary_technique = next(iter(techniques_by_category.values()))
            recommended_technique = primary_technique
            
            print(f"[TECHNIQUE] ✅ {recommended_technique.get('name', 'Unknown')} ({recommended_technique.get('category', 'Unknown')}) | Time: {elapsed_ms}ms")
        else:
            print(f"[TECHNIQUE] ⚠️ No techniques found for {emotion}")
        
        return {
            "recommended_technique": recommended_technique,
            "recommended_techniques_by_category": techniques_by_category
        }
        
    except Exception as e:
        print(f"[TECHNIQUE] ❌ Error: {str(e)[:80]}")
        return {
            "recommended_technique": {},
            "recommended_techniques_by_category": {}
        }
