"""
Nodes Package - All pipeline nodes for the mental health agent

Architecture v7.0 nodes (SentiMind v7 - Pure LLM-First):
  1.  intake_node                    - Load user context & history + psych profile
  2.  mood_analyzer_node             - LLM emotion detection
  3.  emotion_fusion_node            - Merge text + voice emotion
  4.  cognitive_distortion_node      - LLM semantic distortion analysis
  5.  trend_analyzer_node            - Emotional trajectory tracking
  6.  conversation_planner_node      - Strategic decision-maker
  7.  behavioral_activation_node     - Real-world micro-action recommender
  8.  technique_selector_node        - Database technique selection
  9.  crisis_handler_node            - LLM-based crisis detection & response
  10. role_selector_node             - Communication style selection
  11. optimized_response_generator_node - Single LLM response
  12. psych_profile_updater_node     - Persistent psychology model updater
  13. session_saver_node             - Persist conversation data
  14. outcome_tracker_node           - Technique effectiveness
  15. proactive_monitor              - Background mood trend analyser

v7.0 CHANGES (Complete LLM Integration):
  - All ML models replaced with LLM (except voice feature extraction)
  - DistilBERT → LLM emotion classification
  - Keyword patterns → LLM semantic understanding
  - Cognitive distortions: LLM-only analysis (replaced keyword patterns)
  - Voice features (wav2vec2, MFCC) retained for audio analysis only
"""

from .intake import load_user_context
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

# SentiMind v3.0 — New intelligent subsystems
from .cognitive_distortion_node import detect_cognitive_distortions
from .behavioral_activation_node import activate_behavioral_intervention
from .psych_profile_updater import update_psych_profile
from .proactive_monitor import check_and_notify

# SentiMind v6.0 — Fused latency-optimized nodes
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
