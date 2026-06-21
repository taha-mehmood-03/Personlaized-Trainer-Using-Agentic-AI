"""
Nodes Package — registered LangGraph graph nodes for the mental health agent.

Architecture v7.0 (SentiMind v7):
  1. parallel_intake            — Crisis, context, mood, and intent work run concurrently
  2. analysis_and_planning      — Fused emotion, cognitive, trend, planner, activation
  3. response_pipeline          — Fused technique and role selection
  4. optimized_response_generator — Single LLM response
  5. crisis_handler             — Safety response with resources
  6. parallel_persist           — Background profile/session/outcome persistence

Inline pipeline sub-components (called from within the nodes above) live in:
  mental_health_wellness/pipeline/
"""

# ── Registered graph nodes ────────────────────────────────────────────────────
from .crisis_handler import handle_crisis
from .optimized_response_generator import generate_response
from .analysis_and_planning import run_analysis_and_planning
from .response_pipeline import run_response_pipeline
from .conversation_context_resolver import commit_conversation_context, extract_last_question

# ── Pipeline sub-components (re-exported for backwards-compat) ────────────────
from ..pipeline.context_loader import load_user_context
from ..pipeline.mood_analyzer_node import analyze_mood
from ..pipeline.voice_preprocessing import preprocess_voice_input
from ..pipeline.emotion_fusion_node import fuse_emotions
from ..pipeline.trend_analyzer_node import analyze_emotional_trends
from ..pipeline.conversation_planner_node import conversation_planner_node
from ..pipeline.outcome_tracker_node import track_outcome
from ..pipeline.cognitive_distortion_node import detect_cognitive_distortions
from ..pipeline.behavioral_activation_node import activate_behavioral_intervention
from ..pipeline.psych_profile_updater import update_psych_profile
from ..pipeline.role_selector import select_agent_role
from ..pipeline.session_saver import save_session
from ..pipeline.technique_selector_node import select_technique

# ── Background service (re-exported for backwards-compat) ─────────────────────
from ..services.proactive_monitor import check_and_notify

__all__ = [
    # Registered nodes
    "handle_crisis",
    "generate_response",
    "run_analysis_and_planning",
    "run_response_pipeline",
    "commit_conversation_context",
    "extract_last_question",
    # Pipeline sub-components
    "load_user_context",
    "analyze_mood",
    "preprocess_voice_input",
    "fuse_emotions",
    "analyze_emotional_trends",
    "conversation_planner_node",
    "track_outcome",
    "detect_cognitive_distortions",
    "activate_behavioral_intervention",
    "update_psych_profile",
    "select_agent_role",
    "save_session",
    "select_technique",
    # Background service
    "check_and_notify",
]
