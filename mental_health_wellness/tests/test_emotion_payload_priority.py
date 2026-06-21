import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mental_health_wellness.api.helpers import _emotion_payload_from_result


def test_emotion_payload_prefers_fused_emotion_over_raw_mood():
    payload = _emotion_payload_from_result(
        {
            "emotion": "joy",
            "fused_emotion": "anxiety",
            "sentiment": "positive",
            "intensity": 0.2,
            "fused_intensity": 0.62,
            "primary_sub_emotion": "rumination",
        }
    )

    assert payload["emotion"] == "anxiety"
    assert payload["sentiment"] == "NEGATIVE"
    assert payload["intensity"] == 0.62
    assert payload["emotion_label"] == "anxiety / rumination"
