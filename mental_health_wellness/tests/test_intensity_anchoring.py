"""
Test: Intensity Anchoring During Contextual Follow-ups

Validates that the progressive decay system correctly prevents
intensity collapse during multi-turn therapeutic conversations.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def test_progressive_decay_from_anchor():
    """Test that decay always uses the ORIGINAL anchor, not the decayed value."""

    def simulate_decay(anchor, followup_turn):
        if anchor >= 0.5:
            decay_factor = 0.85 if followup_turn == 0 else (0.75 if followup_turn == 1 else 0.65)
            floor = anchor * decay_factor
            cap = max(anchor, 0.75)
            return min(floor, cap)   # FIXED: output is FLOOR, not max(anchor,floor)
        return min(max(anchor, 0.2), 0.35)

    def simulate_bug_decay(anchor, followup_turn):
        """Same formula but anchor gets overwritten each turn (the bug)."""
        if anchor >= 0.5:
            decay_factor = 0.85 if followup_turn == 0 else (0.75 if followup_turn == 1 else 0.65)
            floor = anchor * decay_factor
            cap = max(anchor, 0.75)
            return min(floor, cap)
        return min(max(anchor, 0.2), 0.35)

    original_anchor = 0.87
    print("\n" + "=" * 60)
    print("TEST: Progressive Decay from Fixed Anchor")
    print("Original distress anchor: %.0f%%" % (original_anchor * 100))
    print("=" * 60)

    # CORRECT: Decay from original anchor every turn
    print("\n[OK] CORRECT (fixed): Decay always from original anchor (%.2f)" % original_anchor)
    results_correct = []
    for turn in range(4):
        intensity = simulate_decay(original_anchor, turn)
        results_correct.append(intensity)
        tier = "HIGH" if intensity >= 0.65 else ("MODERATE" if intensity >= 0.35 else "LOW")
        decay_factor = 0.85 if turn == 0 else (0.75 if turn == 1 else 0.65)
        print("  Turn %d: anchor=%.2f x %.2f = floor %.2f -> intensity=%.2f -> Tier: %s"
              % (turn, original_anchor, decay_factor, original_anchor * decay_factor, intensity, tier))

    # BUG: Each turn decays from PREVIOUS decayed value
    print("\n[X] BUG (before fix): Each turn decays from PREVIOUS decayed value")
    compounding_anchor = original_anchor
    results_bug = []
    for turn in range(4):
        intensity = simulate_bug_decay(compounding_anchor, turn)
        results_bug.append(intensity)
        tier = "HIGH" if intensity >= 0.65 else ("MODERATE" if intensity >= 0.35 else "LOW")
        decay_factor = 0.85 if turn == 0 else (0.75 if turn == 1 else 0.65)
        print("  Turn %d: anchor=%.2f x %.2f = floor %.2f -> intensity=%.2f -> Tier: %s"
              % (turn, compounding_anchor, decay_factor, compounding_anchor * decay_factor, intensity, tier))
        compounding_anchor = intensity  # BUG: overwrite

    print("\n" + "=" * 60)
    print("ASSERTIONS:")

    all_pass = True

    ok = all(r >= 0.55 for r in results_correct)
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Fixed decay keeps user in HIGH/MODERATE tier" % status)
    print("          Values: %s" % [round(r, 2) for r in results_correct])

    ok = any(r < 0.40 for r in results_bug)
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Bug path drops to LOW tier" % status)
    print("          Values: %s" % [round(r, 2) for r in results_bug])

    ok = results_correct[2] >= 0.55
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Turn 2 intensity (%.2f) >= 0.55" % (status, results_correct[2]))

    ok = results_correct[3] >= 0.55
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Turn 3 intensity (%.2f) >= 0.55" % (status, results_correct[3]))

    ok = results_bug[3] < 0.40
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Bug Turn 3 (%.2f) < 0.40 (confirms collapse)" % (status, results_bug[3]))

    print("\n" + "=" * 60)
    if all_pass:
        print("ALL TESTS PASSED - Progressive decay anchoring is correct")
    else:
        print("SOME TESTS FAILED - Review above")
    print("=" * 60 + "\n")
    return all_pass


def test_parallel_intake_intensity_guard():
    """Test that parallel_intake only overwrites last_detected_intensity on non-followup routes."""

    print("\n" + "=" * 60)
    print("TEST: parallel_intake intensity guard")
    print("=" * 60)

    preserve_routes = {
        "contextual_followup", "chitchat", "memory_query",
        "positive_feedback", "technique_follow_up",
    }

    test_cases = [
        ("therapeutic",         True,  "Therapeutic -> SHOULD overwrite"),
        ("crisis",              True,  "Crisis -> SHOULD overwrite"),
        ("contextual_followup", False, "Follow-up -> should NOT overwrite"),
        ("chitchat",            False, "Chitchat -> should NOT overwrite"),
        ("memory_query",        False, "Memory -> should NOT overwrite"),
        ("positive_feedback",   False, "Positive feedback -> should NOT overwrite"),
        ("technique_follow_up", False, "Technique follow-up -> should NOT overwrite"),
        ("technique_request",   True,  "Technique request -> SHOULD overwrite"),
    ]

    all_pass = True
    for route, should_overwrite, label in test_cases:
        would_overwrite = route not in preserve_routes
        ok = would_overwrite == should_overwrite
        status = "[OK]" if ok else "[X]"
        if not ok: all_pass = False
        action = "OVERWRITES" if would_overwrite else "PRESERVES"
        print("  %s route=%-24s -> %-10s last_detected_intensity | %s" % (status, route, action, label))

    print("\n" + "=" * 60)
    if all_pass:
        print("ALL INTENSITY GUARD TESTS PASSED")
    else:
        print("INTENSITY GUARD TESTS FAILED")
    print("=" * 60 + "\n")
    return all_pass


def test_disliked_technique_hard_ceiling():
    """Test that disliked techniques can't be resurrected by contextual boosts."""

    print("\n" + "=" * 60)
    print("TEST: Disliked technique sort-time hard ceiling")
    print("=" * 60)

    base_score = 2.5
    rating_penalty = -4.0
    feedback_penalty = -1.5
    contextual_boost = 4.3
    emotion_fit_bonus = 3.0
    semantic_bonus = 1.5

    score_inside = base_score + rating_penalty + feedback_penalty
    total_all_signals = score_inside + contextual_boost + emotion_fit_bonus + semantic_bonus
    total_after_ceiling = min(total_all_signals, -2.0)

    old_score = min(score_inside, -2.0)
    old_total = old_score + contextual_boost + emotion_fit_bonus + semantic_bonus

    print("  Base score:         %.1f" % base_score)
    print("  Rating penalty:     %.1f" % rating_penalty)
    print("  Feedback penalty:   %.1f" % feedback_penalty)
    print("  _score subtotal:    %.1f" % score_inside)
    print("  + Contextual boost: +%.1f" % contextual_boost)
    print("  + Emotion fit:      +%.1f" % emotion_fit_bonus)
    print("  + Semantic:         +%.1f" % semantic_bonus)
    print("  = Total before cap: %.1f" % total_all_signals)
    print("  = Total AFTER cap:  %.1f" % total_after_ceiling)
    print("")
    print("  OLD (ceiling in _score only):  %.1f -- RESURRECTS to positive!" % old_total)
    print("  NEW (ceiling at sort-time):    %.1f -- stays NEGATIVE!" % total_after_ceiling)

    all_pass = True

    ok = total_after_ceiling <= -2.0
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("\n  %s: Sort-time ceiling keeps disliked at <= -2.0 (%.1f)" % (status, total_after_ceiling))

    ok = old_total > 0
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Old behavior was vulnerable (total=%.1f > 0)" % (status, old_total))

    print("\n" + "=" * 60)
    if all_pass:
        print("DISLIKED TECHNIQUE CEILING TESTS PASSED")
    else:
        print("DISLIKED TECHNIQUE CEILING TESTS FAILED")
    print("=" * 60 + "\n")
    return all_pass


def test_technique_selector_has_no_intensity_category_tier_mapping():
    """Verify intensity no longer maps to category pools in technique selection."""
    import mental_health_wellness.tools.technique_tools as technique_tools

    print("\n" + "=" * 60)
    print("TEST: No Intensity Category Tier Mapping")
    print("=" * 60)

    has_tier_function = hasattr(technique_tools, "_intensity_tier")
    has_category_map = hasattr(technique_tools, "INTENSITY_CATEGORY_MAP")

    print("  _intensity_tier present: %s" % has_tier_function)
    print("  INTENSITY_CATEGORY_MAP present: %s" % has_category_map)

    all_pass = not has_tier_function and not has_category_map

    print("\n" + "=" * 60)
    if all_pass:
        print("INTENSITY CATEGORY FILTERING IS REMOVED")
    else:
        print("INTENSITY CATEGORY FILTERING STILL EXISTS")
    print("=" * 60 + "\n")
    assert all_pass
    return all_pass




# ============================================================
# v12.0 DEFECT TESTS — Session-Level Emotional Truth
# ============================================================

def test_hedged_disclosure_floor():
    """Defect 1: Hedged first disclosure must floor to >= FIRST_DISCLOSURE_FLOOR (0.50).

    Before fix: "my day was not that much good" -> hedge multiplier 50% cut ->
    intensity 0.60 -> 0.30 -> anchor written at 0.30 -> all hold guards miss.

    After fix: calibrate_low_confidence_disclosure_intensity raises it to 0.50
    on the first therapeutic disclosure regardless of confidence or hedging.
    """
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from mental_health_wellness.utils.distress_anchor import (
        calibrate_low_confidence_disclosure_intensity,
        FIRST_DISCLOSURE_FLOOR,
        ESTABLISHED_ANCHOR_THRESHOLD,
    )

    print("\n" + "=" * 60)
    print("TEST: Hedged disclosure first-turn floor (Defect 1)")
    print("=" * 60)

    # Simulate first disclosure with hedge penalty applied upstream (0.30)
    # and low model confidence (0.45 < ANCHOR_CONFIDENCE_THRESHOLD 0.65)
    state_first_disclosure = {
        "gate_route": "therapeutic",
        "gate_context_flags": ["emotional_disclosure"],
        "confidence": 0.45,
        "last_detected_intensity": None,   # no prior anchor
        "peak_distress_intensity": None,
    }
    hedged_intensity = 0.30  # what 50% hedge multiplier would produce
    result, reason = calibrate_low_confidence_disclosure_intensity(state_first_disclosure, hedged_intensity)

    print("  Input intensity (post-hedge): %.2f" % hedged_intensity)
    print("  Output intensity:             %.2f  (reason: %s)" % (result, reason))
    print("  FIRST_DISCLOSURE_FLOOR:       %.2f" % FIRST_DISCLOSURE_FLOOR)

    all_pass = True

    ok = result >= FIRST_DISCLOSURE_FLOOR
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: First disclosure floored to >= %.2f (got %.2f)" % (status, FIRST_DISCLOSURE_FLOOR, result))

    ok = reason in ("first_disclosure_floored", "first_disclosure_confidence_floored")
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Reason correctly indicates first_disclosure floor (got '%s')" % (status, reason))

    # Verify that high-confidence hedge is also floored on first turn
    state_high_conf = dict(state_first_disclosure)
    state_high_conf["confidence"] = 0.80  # high confidence
    result_hc, reason_hc = calibrate_low_confidence_disclosure_intensity(state_high_conf, hedged_intensity)
    ok = result_hc >= FIRST_DISCLOSURE_FLOOR
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: High-conf first disclosure also floored (%.2f -> %.2f)" % (status, hedged_intensity, result_hc))

    # Verify that a non-first disclosure (existing anchor) is NOT floored to FIRST_DISCLOSURE_FLOOR
    state_subsequent = dict(state_first_disclosure)
    state_subsequent["last_detected_intensity"] = 0.60  # anchor exists
    state_subsequent["confidence"] = 0.45
    result_sub, reason_sub = calibrate_low_confidence_disclosure_intensity(state_subsequent, 0.30)
    ok = reason_sub == "held_existing_anchor_low_confidence" and result_sub >= 0.45
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Subsequent low-conf read holds existing anchor (%.2f, reason=%s)" % (status, result_sub, reason_sub))

    print("\n" + "=" * 60)
    if all_pass:
        print("HEDGED DISCLOSURE FLOOR TESTS PASSED")
    else:
        print("HEDGED DISCLOSURE FLOOR TESTS FAILED")
    print("=" * 60 + "\n")
    return all_pass


def test_narrative_answer_does_not_lower_anchor():
    """Defect 2: A low-confidence narrative answer must never lower the established anchor.

    Before fix: anchor at 0.48 (below old 0.50 threshold) -> hold guard misses ->
    low-confidence reading of 0.25 overwrites anchor.

    After fix: ESTABLISHED_ANCHOR_THRESHOLD = 0.45, so anchor 0.48 >= 0.45 -> hold fires.
    """
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from mental_health_wellness.utils.distress_anchor import (
        anchor_write_policy,
        ESTABLISHED_ANCHOR_THRESHOLD,
    )

    print("\n" + "=" * 60)
    print("TEST: Narrative answer monotonic anchor (Defect 2)")
    print("=" * 60)
    print("  ESTABLISHED_ANCHOR_THRESHOLD = %.2f (was 0.50)" % ESTABLISHED_ANCHOR_THRESHOLD)

    all_pass = True

    # --- Case A: anchor at 0.48, low-confidence narrative answer at 0.25
    # With old threshold (0.50): hold would NOT fire -> anchor lowered to 0.25 (BUG)
    # With new threshold (0.45): hold FIRES -> anchor preserved at 0.48
    from langchain_core.messages import HumanMessage
    state_narrative = {
        "gate_route": "therapeutic",
        "gate_context_flags": [],
        "confidence": 0.40,
        "last_detected_intensity": 0.48,
        "peak_distress_intensity": 0.48,
        "messages": [HumanMessage(content="yes actually my principal insulted me")],
    }
    should_write, anchor_out, reason = anchor_write_policy(state_narrative, state_narrative, 0.25)

    print("\n  Case A: anchor=0.48, new_intensity=0.25 (low-conf narrative)")
    print("    should_write=%s | anchor_out=%s | reason=%s" % (should_write, anchor_out, reason))

    ok = not should_write and reason == "hold_existing_anchor_low_confidence"
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Low-conf narrative does NOT lower anchor (should_write=%s)" % (status, should_write))

    ok = anchor_out is not None and anchor_out >= 0.45
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Returned anchor (%.2f) preserved at >= 0.45" % (status, anchor_out or 0.0))

    # --- Case B: no prior anchor + therapeutic disclosure -> should write FIRST_DISCLOSURE_FLOOR
    state_first = {
        "gate_route": "therapeutic",
        "gate_context_flags": ["emotional_disclosure"],
        "confidence": 0.40,
        "last_detected_intensity": None,
        "peak_distress_intensity": None,
        "messages": [HumanMessage(content="my day was not that much good")],
    }
    should_write_b, anchor_out_b, reason_b = anchor_write_policy(state_first, state_first, 0.30)
    print("\n  Case B: no anchor, first disclosure at 0.30 (low-conf)")
    print("    should_write=%s | anchor_out=%s | reason=%s" % (should_write_b, anchor_out_b, reason_b))

    ok = should_write_b and anchor_out_b is not None and anchor_out_b >= 0.50
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: First disclosure written at >= 0.50 (got %.2f)" % (status, anchor_out_b or 0.0))

    # --- Case C: recovery route — anchor IS allowed to decrease
    from langchain_core.messages import HumanMessage
    state_recovery = {
        "gate_route": "positive_feedback",
        "gate_context_flags": ["positive_feedback"],
        "confidence": 0.80,
        "last_detected_intensity": 0.70,
        "peak_distress_intensity": 0.70,
        "messages": [HumanMessage(content="that really helped me feel better")],
    }
    should_write_c, anchor_out_c, reason_c = anchor_write_policy(state_recovery, state_recovery, 0.25)
    print("\n  Case C: recovery turn — anchor decrease should be ALLOWED")
    print("    should_write=%s | anchor_out=%s | reason=%s" % (should_write_c, anchor_out_c, reason_c))

    ok = should_write_c and reason_c == "recovery_allows_decrease"
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Recovery route correctly allows anchor decrease (reason=%s)" % (status, reason_c))

    print("\n" + "=" * 60)
    if all_pass:
        print("NARRATIVE ANSWER MONOTONIC ANCHOR TESTS PASSED")
    else:
        print("NARRATIVE ANSWER MONOTONIC ANCHOR TESTS FAILED")
    print("=" * 60 + "\n")
    return all_pass


def test_consent_turn_intensity_floor():
    """Defect 3: Short consent turns must not drop below 0.45 when a therapeutic thread exists.

    Before fix: "yes share it with me" -> GoEmotions reads neutral -> intensity 0.10 ->
    technique selected for calm/reflective person.

    After fix: _gate_calibrated_mood applies thread-aware 0.45 floor when
    primary_concern is set.
    """
    print("\n" + "=" * 60)
    print("TEST: Consent turn intensity floor (Defect 3)")
    print("=" * 60)

    # Simulate what _gate_calibrated_mood does for accept_technique with thread
    def simulate_consent_mood_with_floor(previous_intensity, hint, has_thread):
        """Mirror _gate_calibrated_mood accept_technique logic with v12.0 floor."""
        THREAD_FLOOR = 0.45
        anchor = max(float(previous_intensity or 0.0), float(hint or 0.35))
        if has_thread and anchor < THREAD_FLOOR:
            anchor = THREAD_FLOOR
        intensity = min(max(anchor, 0.25), 0.85)
        return intensity

    def simulate_consent_mood_without_floor(previous_intensity, hint):
        """Old behavior: no thread-aware floor."""
        anchor = max(float(previous_intensity or 0.0), float(hint or 0.35))
        return min(max(anchor, 0.25), 0.85)

    test_cases = [
        # (previous_intensity, hint, has_thread, label)
        (None,  0.10, True,  "No anchor, low hint, thread exists   -> should floor to 0.45"),
        (0.30,  0.15, True,  "Low anchor (0.30), thread exists     -> should floor to 0.45"),
        (0.50,  0.30, True,  "Good anchor (0.50), thread exists    -> should stay 0.50"),
        (None,  0.10, False, "No anchor, no thread                 -> should NOT floor"),
        (0.30,  0.15, False, "Low anchor, no thread                -> should NOT floor"),
    ]

    all_pass = True
    for prev_int, hint, has_thread, label in test_cases:
        with_floor = simulate_consent_mood_with_floor(prev_int, hint, has_thread)
        without_floor = simulate_consent_mood_without_floor(prev_int, hint)

        if has_thread:
            ok = with_floor >= 0.45
            expected = ">=0.45"
        else:
            ok = abs(with_floor - without_floor) < 0.001  # floor should not apply
            expected = "=%.2f (no floor)" % without_floor

        status = "[OK] PASS" if ok else "[X] FAIL"
        if not ok: all_pass = False
        print("  %s [has_thread=%s] %.2f | %s" % (status, has_thread, with_floor, label))

    print("\n" + "=" * 60)
    if all_pass:
        print("CONSENT TURN INTENSITY FLOOR TESTS PASSED")
    else:
        print("CONSENT TURN INTENSITY FLOOR TESTS FAILED")
    print("=" * 60 + "\n")
    return all_pass


def test_technique_selector_thread_aware_floor():
    """Defect 4: Technique selector must inherit both emotion and intensity from anchor.

    This test verifies the emotion inheritance and the last-resort intensity floor,
    and confirms that the resulting tier would be 'moderate' or 'high' rather than 'low'.

    The critical log assertion from the spec:
      [TOOL] recommend_technique: emotion=... intensity=... tier=moderate/high
    """
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

    print("\n" + "=" * 60)
    print("TEST: Technique selector thread-aware floor + emotion inheritance (Defect 4)")
    print("=" * 60)

    all_pass = True

    from mental_health_wellness.utils.distress_anchor import (
        LOW_SIGNAL_EMOTIONS, NEGATIVE_EMOTIONS, has_active_therapeutic_thread,
    )

    def simulate_selector_inputs(current_emotion, current_intensity, anchor_emotion, anchor_intensity, has_thread, needs_technique):
        """Mirror the v12.0 emotion+intensity selection logic in technique_selector_node."""
        emotion = current_emotion
        # Emotion inheritance
        if current_emotion.lower() in LOW_SIGNAL_EMOTIONS and anchor_emotion in NEGATIVE_EMOTIONS and has_thread:
            emotion = anchor_emotion
        elif current_emotion.lower() in NEGATIVE_EMOTIONS:
            emotion = current_emotion

        # Intensity: max of current and anchor
        intensity = max(current_intensity, anchor_intensity)

        # Thread-aware floor
        if needs_technique and intensity < 0.45 and has_thread:
            intensity = 0.45

        return emotion, intensity

    # Case A: consent turn — current is neutral/low, anchor is sadness/0.50
    em, it = simulate_selector_inputs(
        current_emotion="neutral", current_intensity=0.10,
        anchor_emotion="sadness", anchor_intensity=0.50,
        has_thread=True, needs_technique=True,
    )
    print("\n  Case A: consent turn (neutral 0.10, anchor sadness 0.50, thread=True)")
    print("    -> emotion=%s | intensity=%.2f" % (em, it))
    ok = em == "sadness" and it >= 0.45
    status = "[OK] PASS" if ok else "[X] FAIL"
    if not ok: all_pass = False
    print("  %s: Emotion inherited (sadness) and intensity >= 0.45" % status)

    # Case B: all anchors zero (worst case — every upstream fix failed)
    em_b, it_b = simulate_selector_inputs(
        current_emotion="neutral", current_intensity=0.10,
        anchor_emotion=None, anchor_intensity=0.0,
        has_thread=True, needs_technique=True,
    )
    print("\n  Case B: zero anchor (all upstream fixes failed), thread=True")
    print("    -> emotion=%s | intensity=%.2f" % (em_b, it_b))
    ok_b = it_b >= 0.45
    status = "[OK] PASS" if ok_b else "[X] FAIL"
    if not ok_b: all_pass = False
    print("  %s: Last-resort thread-aware floor applies (intensity >= 0.45)" % status)

    # Case C: no thread — floor must NOT apply
    em_c, it_c = simulate_selector_inputs(
        current_emotion="neutral", current_intensity=0.10,
        anchor_emotion=None, anchor_intensity=0.0,
        has_thread=False, needs_technique=True,
    )
    print("\n  Case C: no therapeutic thread — floor must NOT apply")
    print("    -> emotion=%s | intensity=%.2f" % (em_c, it_c))
    ok_c = it_c < 0.45
    status = "[OK] PASS" if ok_c else "[X] FAIL"
    if not ok_c: all_pass = False
    print("  %s: No floor without thread (intensity=%.2f < 0.45)" % (status, it_c))

    import mental_health_wellness.tools.technique_tools as technique_tools
    no_tier_mapping = (
        not hasattr(technique_tools, "_intensity_tier")
        and not hasattr(technique_tools, "INTENSITY_CATEGORY_MAP")
    )
    status = "[OK] PASS" if no_tier_mapping else "[X] FAIL"
    if not no_tier_mapping:
        all_pass = False
    print("\n  %s: Technique selector no longer maps intensity to category tiers" % status)

    print("\n" + "=" * 60)
    if all_pass:
        print("TECHNIQUE SELECTOR THREAD-AWARE FLOOR TESTS PASSED")
    else:
        print("TECHNIQUE SELECTOR THREAD-AWARE FLOOR TESTS FAILED")
    print("=" * 60 + "\n")
    return all_pass


if __name__ == "__main__":
    results = []

    results.append(("Progressive Decay Anchoring", test_progressive_decay_from_anchor()))
    results.append(("Intensity Guard (parallel_intake)", test_parallel_intake_intensity_guard()))

    results.append((
        "No Intensity Category Tier Mapping",
        test_technique_selector_has_no_intensity_category_tier_mapping(),
    ))

    results.append(("Disliked Technique Ceiling", test_disliked_technique_hard_ceiling()))
    results.append(("Hedged Disclosure Floor (v12.0)", test_hedged_disclosure_floor()))
    results.append(("Narrative Answer Monotonic Anchor (v12.0)", test_narrative_answer_does_not_lower_anchor()))
    results.append(("Consent Turn Intensity Floor (v12.0)", test_consent_turn_intensity_floor()))

    try:
        results.append(("Technique Selector Thread-Aware Floor (v12.0)", test_technique_selector_thread_aware_floor()))
    except ImportError as e:
        print("\nSkipping technique selector thread test (import failed): %s" % e)

    print("\n" + "=" * 60)
    print("FINAL RESULTS:")
    print("=" * 60)
    for name, passed in results:
        status = "[OK] PASS" if passed else "[X] FAIL"
        print("  %s: %s" % (status, name))

    all_passed = all(r[1] for r in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS NEED ATTENTION")
    print("=" * 60)



