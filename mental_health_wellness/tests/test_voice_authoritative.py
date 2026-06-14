import pytest
import asyncio
from langchain_core.messages import HumanMessage
from mental_health_wellness.agent.state import get_initial_state
from mental_health_wellness.nodes.parallel_intake import run_parallel_intake
from mental_health_wellness.nodes.emotion_fusion_node import fuse_emotions

@pytest.mark.asyncio
async def test_voice_authoritative_flow():
    # Create clean initial state
    state = get_initial_state()
    
    # Populate with voice indicators and route
    state["audio_file_path"] = "mock_audio.wav"
    state["gate_route"] = "therapeutic"
    state["voice_processed"] = True
    state["voice_features"] = {
        "emotion": "anxiety",
        "confidence": 0.85,
        "arousal": 0.75,
        "valence": 0.25,
        "distress_index": 0.80,
        "pause_density": 0.40,
        "primary_sub_emotion": "panic",
        "secondary_sub_emotions": ["hopelessness"],
        "detected_symptoms": ["insomnia"],
        "detected_behaviors": ["crying"],
        "detected_contexts": ["work"],
    }
    
    # Run parallel intake
    merged = await run_parallel_intake(state)
    
    # Now run fuse_emotions with combined state
    combined_state = {**state, **merged}
    
    # Ensure combined_state contains the voice features
    assert combined_state.get("voice_features") is not None
    assert combined_state.get("voice_features")["emotion"] == "anxiety"
    
    fusion_result = fuse_emotions(combined_state)
    
    # Verify Case 0 fusion logic (authoritative voice override)
    assert fusion_result["fused_emotion"] == "anxiety"
    assert fusion_result["fused_intensity"] == 0.75
    assert fusion_result["primary_sub_emotion"] == "panic"
    assert "insomnia" in fusion_result["detected_symptoms"]
    assert "crying" in fusion_result["detected_behaviors"]


@pytest.mark.asyncio
async def test_prefetched_voice_features_skip_text_mood_and_drive_fusion(monkeypatch):
    from mental_health_wellness.nodes import context_loader, mood_analyzer_node

    async def fail_if_text_mood_runs(_state):
        raise AssertionError("text mood analysis should not run when authoritative voice features exist")

    async def fake_load_user_context(state):
        return {
            "is_new_user": True,
            "session_count": 0,
            "most_common_emotion": "neutral",
            "historical_mood": "neutral",
            "user_preferences": {},
            "chat_history": [],
            "memory_context": "",
            "context_ready": True,
            "voice_features": state.get("voice_features"),
            "messages": state.get("messages", []),
            "audio_file_path": state.get("audio_file_path"),
        }

    monkeypatch.setattr(mood_analyzer_node, "analyze_mood", fail_if_text_mood_runs)
    monkeypatch.setattr(context_loader, "load_user_context", fake_load_user_context)

    state = get_initial_state()
    state["user_id"] = "voice-user"
    state["session_id"] = "voice-session"
    state["messages"] = [HumanMessage(content="I'm fine")]
    state["message"] = "I'm fine"
    state["has_voice"] = True
    state["gate_route"] = "therapeutic"
    state["gate_should_skip_mood_analysis"] = True
    state["prefetched_intent"] = {
        "intent": "venting",
        "confidence": 0.91,
        "source": "smart_gate",
    }
    state["voice_features"] = {
        "emotion": "anxiety",
        "sentiment": "negative",
        "intensity": 0.82,
        "confidence": 0.88,
        "arousal": 0.84,
        "valence": 0.18,
        "distress_index": 0.79,
        "pause_density": 0.36,
        "primary_sub_emotion": "panic",
        "secondary_sub_emotions": ["overwhelm"],
        "detected_symptoms": ["shaky_voice"],
        "detected_behaviors": ["withdrawing"],
        "detected_contexts": ["voice_message"],
        "emotion_scores": {"anxiety": 0.88},
        "emotion_reasoning": "voice tone indicates high anxiety despite neutral words",
        "extraction_method": "gemini_audio",
    }

    intake = await run_parallel_intake(state)
    assert intake["emotion"] == "anxiety"
    assert intake["intensity"] == 0.82
    assert intake["primary_sub_emotion"] == "panic"
    assert intake["voice_processed"] is True

    fused = fuse_emotions({**state, **intake})
    assert fused["fused_emotion"] == "anxiety"
    assert fused["fused_intensity"] == 0.82
    assert fused["primary_sub_emotion"] == "panic"
    assert "shaky_voice" in fused["detected_symptoms"]
