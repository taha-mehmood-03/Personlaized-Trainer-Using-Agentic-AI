"""
State Definition - Custom state for the mental health agent
"""

import operator
from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class MentalHealthState(TypedDict):
    """
    Complete state schema for the mental health agent.
    Each field is updated by specific nodes.
    """
    
    # ============================================
    # CORE MESSAGE HISTORY
    # ============================================
    messages: Annotated[list[BaseMessage], add_messages]
    
    # ============================================
    # USER IDENTIFICATION
    # ============================================
    user_id: str
    session_id: str
    
    # ============================================
    # USER CONTEXT (from context_loader inside parallel_intake)
    # ============================================
    is_new_user: bool
    session_count: int
    most_common_emotion: str
    user_preferences: dict
    chat_history: list[dict]  # Previous conversation messages for context
    memory_context: str  # Semantically retrieved relevant memories
    
    # ============================================
    # INTENT CLASSIFICATION (from smart gate / parallel intake)
    # ============================================
    # DEPRECATED: `intent` is never written by any current node.
    # Use `prefetched_intent` (dict) from parallel_intake / smart_gate instead.
    intent: str  # "casual", "emotional", "crisis", "technique_request", "check_in"
    # DEPRECATED: `skip_intervention` is never set to True by any current node.
    # Gate-aware chitchat bypass is handled via prefetched_intent.source == "smart_gate".
    skip_intervention: bool
    
    # ============================================
    # MOOD ANALYSIS (from parallel intake)
    # ============================================
    emotion: str        # anger, fear, sadness, joy, neutral, surprise, disgust, anxiety
    sentiment: str      # positive, negative, neutral
    intensity: float    # 0.0 - 1.0
    confidence: float   # 0.0 - 1.0
    
    # ============================================
    # CRISIS DETECTION (from crisis_handler_node)
    # ============================================
    crisis_level: str           # "low", "medium", "high"
    crisis_detected: bool
    crisis_resources: dict
    
    # ============================================
    # AGENT ROLE (from role_selector_node - NEW)
    # ============================================
    agent_role: str  # "friend", "coach", "trainer", "crisis_support"
    
    # ============================================
    # TECHNIQUE (from technique_provider_node)
    # ============================================
    recommended_technique: dict
    recommended_techniques_by_category: dict  # All 6 categories with best technique each
    alternative_techniques: list[dict]        # Top 2 alternatives for escape hatch
    
    # ============================================
    # RESPONSE (from optimized_response_generator)
    # ============================================
    final_response: str
    
    # ============================================
    # VOICE ANALYSIS (from voice module)
    # ============================================
    voice_emotion: str
    voice_arousal: float
    voice_valence: float
    voice_confidence: float
    voice_distress_index: float   # Psychoacoustic composite distress score (0-1)
    voice_pause_density: float    # Proportion of silent frames (hesitancy indicator)
    voice_mfcc_vector: list       # 13-dim MFCC mean vector from torchaudio/librosa
    has_voice: bool
    voice_processed: bool         # True once voice_preprocessing_node has run
    voice_features: Optional[dict]  # Voice analysis data dict for emotion_fusion_node
    audio_file_path: Optional[str]  # Path to voice audio file for analysis
    audio_bytes: Optional[bytes]    # Raw audio bytes (alternative to file path)
    transcription: str              # ASR output from Whisper (set by voice_preprocessing_node)
    
    # ============================================
    # EXPLAINABILITY
    # ============================================
    technique_reasoning: str
    
    # ============================================
    # EMOTIONAL TREND (from trend_analyzer_node)
    # ============================================
    emotional_trend: str          # "improving", "worsening", "stable"
    trend_window: list[dict]      # last N {emotion, intensity} snapshots
    
    # ============================================
    # CONVERSATION STRATEGY (from conversation_planner_node)
    # ============================================
    conversation_strategy: str    # "validate_only", "ask_question", "reframe", "suggest_technique", "encourage_reflection"
    conversation_phase: str       # "venting", "reflection", "solution", "recovery"
    technique_readiness: float    # 0.0-1.0 readiness score
    
    # ============================================
    # EMOTION FUSION (from emotion_fusion_node)
    # ============================================
    fused_emotion: str            # weighted text+voice emotion
    fused_intensity: float        # weighted text+voice intensity
    
    # ============================================
    # SESSION INTELLIGENCE
    # ============================================
    session_summary: str          # running summary of conversation
    session_message_count: int    # messages in current session

    # ============================================
    # v3: COGNITIVE DISTORTION DETECTION (Node 2b)
    # ============================================
    distortion_type:        Optional[str]       # None or e.g. "catastrophizing"
    distortion_confidence:  float               # 0.0-1.0
    distortion_explanation: Optional[str]       # human-readable explanation
    all_distortions:        list[str]           # all detected distortion types

    # ============================================
    # v3: BEHAVIORAL ACTIVATION ENGINE (Node 3b)
    # ============================================
    micro_action:           Optional[str]       # recommended real-world action
    micro_action_rationale: Optional[str]       # why this action was chosen
    micro_action_category:  Optional[str]       # physical | social | cognitive | ...

    # ============================================
    # v3: PSYCHOLOGICAL PROFILE ENGINE (Node 5b)
    # ============================================
    psych_profile:          dict                # PsychProfile DB model as dict
    proactive_alert:        Optional[str]       # hint from proactive monitor

    # ============================================
    # METADATA
    # ============================================
    tools_used: list[str]
    processing_time_ms: int

    # ============================================
    # AUDIT FIX FIELDS
    # ============================================
    historical_mood: str            # FIX 1b: cross-session mood from user_stats (metadata only, NOT current emotion)
    session_start_emotion: Optional[str]    # FIX 5: within-session emotion baseline (captured at turn 1)
    session_start_intensity: Optional[float] # FIX 5: within-session intensity baseline (captured at turn 1)
    crisis_pre_screened: bool       # FIX 1 NEW: True if crisis_pre_screener ran (whether crisis found or not)
    technique_delivery_emotion: Optional[str]   # FIX 4 NEW: emotion at exact moment technique was delivered
    technique_delivery_intensity: Optional[float]  # FIX 4 NEW: intensity at exact moment technique was delivered

    # ============================================
    # v5.3: PREFETCHED INTENT (from parallel_intake)
    # ============================================
    # Intent pre-check runs concurrently with crisis screening + intake + mood.
    # conversation_planner reads this and skips its own LLM call when available.
    prefetched_intent: Optional[dict]   # {"intent": str, "confidence": float, "source": str} or None

    # ============================================
    # v5.4: GATE ROUTE (from smart_pipeline_gate in graph.py)
    # ============================================
    # Set before the graph runs. Allows nodes (e.g., parallel_intake) to skip
    # expensive LLM calls that the gate has already made redundant.
    # Values: "chitchat" | "therapeutic" | "" (not yet set)
    gate_route: str

    # ============================================
    # v9.0: CLINICAL SEVERITY (PHQ-9/GAD-7)
    # ============================================
    clinical_severity: str            # "minimal"|"mild"|"moderate"|"moderately_severe"|"severe"
    clinical_phq9_score: int          # estimated PHQ-9 total (0-27)
    clinical_gad7_score: int          # estimated GAD-7 total (0-21)
    clinical_indicators: list[str]    # detected clinical indicators (items scoring >= 2)
    clinical_confidence: float        # 0.0-1.0 confidence in clinical assessment


def get_initial_state() -> MentalHealthState:
    """
    Create a fresh initial state with sensible defaults.
    Called at the start of each conversation turn.
    """
    return MentalHealthState(
        # Core
        messages=[],
        user_id="",
        session_id="",
        
        # User context
        is_new_user=True,
        session_count=0,
        most_common_emotion="neutral",
        user_preferences={},
        chat_history=[],  # Populated by context_loader inside parallel_intake
        memory_context="",  # Semantically retrieved memories
        
        # Intent
        intent="casual",
        
        # Mood
        emotion="neutral",
        sentiment="neutral",
        intensity=0.5,
        confidence=0.5,
        
        # Crisis
        crisis_level="low",
        crisis_detected=False,
        crisis_resources={},
        
        # Agent role
        agent_role="coach",  # Default to coach role
        
        # Technique
        recommended_technique={},
        recommended_techniques_by_category={},
        alternative_techniques=[],
        technique_formatted="",
        
        # Response
        final_response="",
        
        # Voice
        voice_emotion="neutral",
        voice_arousal=0.5,
        voice_valence=0.5,
        voice_confidence=0.0,
        voice_distress_index=0.0,
        voice_pause_density=0.25,
        voice_mfcc_vector=[],
        has_voice=False,
        voice_processed=False,
        voice_features=None,    # Set by voice_preprocessing_node for emotion_fusion_node
        audio_file_path=None,   # Set by voice endpoint when audio is uploaded
        audio_bytes=None,       # Raw audio bytes (alternative to file path)
        transcription="",       # ASR output from Whisper
        
        # Explainability
        technique_reasoning="",
        
        # Emotional trend
        emotional_trend="stable",
        trend_window=[],
        
        # Conversation strategy
        conversation_strategy="validate_only",
        conversation_phase="venting",
        technique_readiness=0.0,

        # Emotion fusion
        fused_emotion="neutral",
        fused_intensity=0.5,

        # Session intelligence
        session_summary="",
        session_message_count=0,

        # v3: Cognitive Distortion Detection
        distortion_type=None,
        distortion_confidence=0.0,
        distortion_explanation=None,
        all_distortions=[],

        # v3: Behavioral Activation
        micro_action=None,
        micro_action_rationale=None,
        micro_action_category=None,

        # v3: Psychological Profile
        psych_profile={},
        proactive_alert=None,

        # Metadata
        tools_used=[],
        processing_time_ms=0,

        # Audit fix fields
        skip_intervention=False,        # FIX 3: default False, INTENT_CLASSIFIER may set True
        historical_mood="neutral",       # FIX 1b: populated by INTAKE from user_stats
        session_start_emotion=None,      # FIX 5: set on first turn by session_saver
        session_start_intensity=None,    # FIX 5: set on first turn by session_saver
        crisis_pre_screened=False,       # FIX 1: set by crisis_pre_screener_node
        technique_delivery_emotion=None,    # FIX 4: set by session_saver when technique delivered
        technique_delivery_intensity=None,  # FIX 4: set by session_saver when technique delivered

        # v5.3: Prefetched intent from parallel_intake (None on first turn until prefetch completes)
        prefetched_intent=None,

        # v5.4: Gate route set before graph runs by smart_pipeline_gate
        gate_route="",

        # v9.0: Clinical Severity (PHQ-9/GAD-7)
        clinical_severity="minimal",
        clinical_phq9_score=0,
        clinical_gad7_score=0,
        clinical_indicators=[],
        clinical_confidence=0.0,
    )
