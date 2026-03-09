"""
Nodes Package - All pipeline nodes for the mental health agent

Architecture v5.0 nodes (SentiMind v3):
  1.  intake_node                    - Load user context & history + psych profile
  2.  mood_analyzer_node             - DistilBERT emotion detection
  3.  emotion_fusion_node            - Merge text + voice emotion
  4.  cognitive_distortion_node      - CBT distortion pattern detector       [v3 NEW]
  5.  trend_analyzer_node            - Emotional trajectory tracking
  6.  conversation_planner_node      - Strategic decision-maker
  7.  behavioral_activation_node     - Real-world micro-action recommender    [v3 NEW]
  8.  technique_selector_node        - Database technique selection
  9.  crisis_handler_node            - Crisis detection & response
  10. role_selector_node             - Communication style selection
  11. optimized_response_generator_node - Single LLM response
  12. psych_profile_updater_node     - Persistent psychology model updater    [v3 NEW]
  13. session_saver_node             - Persist conversation data
  14. outcome_tracker_node           - Technique effectiveness
  15. proactive_monitor              - Background mood trend analyser         [v3 NEW]
"""

from .intake import intake_node
from .crisis_handler import crisis_handler_node
from .role_selector import role_selector_node
from .session_saver import session_saver_node
from .mood_analyzer_node import mood_analyzer_node
from .technique_selector_node import technique_selector_node
from .optimized_response_generator import optimized_response_generator_node
from .voice_preprocessing import voice_preprocessing_node

# Intelligence nodes (v4.0)
from .emotion_fusion_node import emotion_fusion_node
from .trend_analyzer_node import trend_analyzer_node
from .conversation_planner_node import conversation_planner_node
from .outcome_tracker_node import outcome_tracker_node

# SentiMind v3.0 — New intelligent subsystems
from .cognitive_distortion_node import cognitive_distortion_node
from .behavioral_activation_node import behavioral_activation_node
from .psych_profile_updater import psych_profile_updater_node
from .proactive_monitor import check_and_notify

__all__ = [
    "intake_node",
    "mood_analyzer_node",
    "emotion_fusion_node",
    "cognitive_distortion_node",
    "trend_analyzer_node",
    "conversation_planner_node",
    "behavioral_activation_node",
    "technique_selector_node",
    "crisis_handler_node",
    "role_selector_node",
    "optimized_response_generator_node",
    "psych_profile_updater_node",
    "session_saver_node",
    "outcome_tracker_node",
    "voice_preprocessing_node",
    "check_and_notify",
]
