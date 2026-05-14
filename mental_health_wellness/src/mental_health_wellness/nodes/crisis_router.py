"""
Crisis Router Node - Conditional routing based on crisis detection

ARCHITECTURE NODE 4:
Purpose: Route to Crisis Handler or Response Generator based on crisis risk
Runs AFTER agentic agent analysis

Decision:
  - If crisis_detected = True AND crisis_risk in ["medium", "high"]
     Route to Crisis Handler node
  - Else
     Route to Response Generator node
"""

from ..agent.state import MentalHealthState


async def route_crisis(state: MentalHealthState) -> dict:
    """
    CRISIS ROUTER - Conditional routing node.
    
    PURPOSE:
    Check if crisis was detected during agentic analysis.
    Route to appropriate next node:
      - Crisis Handler (for medium/high risk)
      - Response Generator (for low risk)
    
    Input State:
        - crisis_detected: Boolean flag from agentic agent
        - crisis_level: Risk level string ("low", "medium", "high")
        - emotion: Detected emotion
        - recommended_technique: Technique to suggest (if any)
    
    Output State:
        - route_to: Either "crisis_handler" or "response_generator"
        - crisis_routing_info: Debug info about routing decision
    """
    print(f"\n[NODE: CRISIS_ROUTER]  Evaluating crisis routing")
    
    # Extract crisis information from state
    crisis_detected = state.get("crisis_detected", False)
    crisis_level = state.get("crisis_level", "low")
    
    print(f"[NODE: CRISIS_ROUTER] Crisis detected: {crisis_detected}, Level: {crisis_level}")
    
    # ============================================
    # ROUTING DECISION LOGIC
    # ============================================
    
    # Route to Crisis Handler if:
    # 1. crisis_detected flag is True
    # 2. AND crisis_level is medium or high
    
    if crisis_detected and crisis_level in ["medium", "high"]:
        route_to = "crisis_handler"
        print(f"[NODE: CRISIS_ROUTER]  ROUTING TO CRISIS HANDLER")
    else:
        route_to = "response_generator"
        print(f"[NODE: CRISIS_ROUTER]  Routing to response generator (low risk)")
    
    return {
        "route_to": route_to,
        "crisis_routing_info": {
            "crisis_detected": crisis_detected,
            "crisis_level": crisis_level,
            "routing_decision": route_to
        }
    }
