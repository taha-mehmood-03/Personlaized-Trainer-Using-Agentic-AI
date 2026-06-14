"""Direct test of _gate_calibrated_mood function."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from mental_health_wellness.nodes.parallel_intake import _gate_calibrated_mood

state = {
    "gate_route": "contextual_followup",
    "gate_context_flags": [],
    "gate_intensity_hint": None,
    "last_detected_emotion": "sadness",
    "last_detected_intensity": 0.87,
    "primary_sub_emotion": "hopelessness",
    "followup_turn_count": 0,
    "detected_symptoms": [],
    "detected_behaviors": [],
    "detected_contexts": [],
    "messages": [],
}

print("=== Testing _gate_calibrated_mood with high anchor ===\n")

results = []
for turn in range(4):
    state["followup_turn_count"] = turn
    msg = [
        "yeah it is about my work",
        "nobody understands what I go through",
        "I have been dealing with this for months",
        "it makes me feel really alone honestly",
    ][turn]
    r = _gate_calibrated_mood(state, msg)
    results.append(r["intensity"])
    print("Turn %d: intensity=%.2f emotion=%s (msg: %s)" % (turn, r["intensity"], r["emotion"], msg))

print("\n=== Verifying anchor is NOT overwritten ===")
print("last_detected_intensity still = %.2f (should be 0.87)" % state["last_detected_intensity"])

print("\n=== Results ===")
print("Values: %s" % [round(r, 2) for r in results])
all_ok = all(r >= 0.55 for r in results)
print("All intensities >= 0.55 (MODERATE+): %s" % all_ok)
print("RESULT: %s" % ("PASSED" if all_ok else "FAILED"))
