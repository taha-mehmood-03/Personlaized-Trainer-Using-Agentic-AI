"""
Nodes Package - All pipeline nodes for the mental health agent

Architecture v7.0 nodes (SentiMind v7 - Pure LLM-First):
  1.  parallel_intake                - Runs crisis, context, mood, and intent work concurrently
  2.  analysis_and_planning          - Fused emotion, cognitive, trend, planner, activation work
  3.  response_pipeline              - Fused technique and role selection
  4.  optimized_response_generator   - Single LLM response
  5.  crisis_handler                 - Safety response with resources
  6.  parallel_persist               - Background profile/session/outcome persistence

Helper modules:
  - context_loader                   - Loads user preferences and semantic memory for parallel_intake

v7.0 CHANGES (Complete LLM Integration):
  - All ML models replaced with LLM (except voice feature extraction)
  - DistilBERT  LLM emotion classification
  - Keyword patterns  LLM semantic understanding
  - Cognitive distortions: LLM-only analysis (replaced keyword patterns)
  - Voice features (wav2vec2, MFCC) retained for audio analysis only
"""

from .context_loader import load_user_context
from .crisis_handler import handle_crisis
from .role_selector import select_agent_role
from .session_saver import save_session
from .mood_analyzer_node import analyze_mood
from .technique_selector_node import select_technique
from .optimized_response_generator import generate_response
from .voice_preprocessing import preprocess_voice_input

# Intelligence nodes (v4.0)
from .emotion_fusion_node import fuse_emotions
from .trend_analyzer_node import analyze_emotional_trends
from .conversation_planner_node import conversation_planner_node
from .outcome_tracker_node import track_outcome

# SentiMind v3.0  New intelligent subsystems
from .cognitive_distortion_node import detect_cognitive_distortions
from .behavioral_activation_node import activate_behavioral_intervention
from .psych_profile_updater import update_psych_profile
from .proactive_monitor import check_and_notify

# SentiMind v6.0  Fused latency-optimized nodes
from .analysis_and_planning import run_analysis_and_planning
from .response_pipeline import run_response_pipeline

__all__ = [
    "load_user_context",
    "analyze_mood",
    "fuse_emotions",
    "detect_cognitive_distortions",
    "analyze_emotional_trends",
    "conversation_planner_node",
    "activate_behavioral_intervention",
    "select_technique",
    "handle_crisis",
    "select_agent_role",
    "generate_response",
    "update_psych_profile",
    "save_session",
    "track_outcome",
    "preprocess_voice_input",
    "check_and_notify",
    # v6.0 fused nodes
    "run_analysis_and_planning",
    "run_response_pipeline",
]
