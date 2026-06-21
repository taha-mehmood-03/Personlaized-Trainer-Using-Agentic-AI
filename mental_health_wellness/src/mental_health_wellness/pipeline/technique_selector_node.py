"""
Technique Selector Node - Deterministic Python-based technique selection

ARCHITECTURE NODE 3:
Purpose: Select best technique for detected emotion using database queries
Runs AFTER mood analyzer node, BEFORE response generator
No LLM call - pure database logic
"""

from ..agent.state import MentalHealthState
from ..tools.technique_tools import recommend_technique
from ..techniques.emotion_metadata import NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
from ..utils.distress_anchor import (
    LOW_SIGNAL_EMOTIONS,
    NEGATIVE_EMOTIONS,
    anchored_negative_emotion,
    distress_anchor_value,
    has_active_therapeutic_thread,
    is_short_consent_turn,
)

import time


_LOW_SIGNAL_EMOTIONS = {"neutral", "joy", "surprise"}

_TECHNIQUE_QUERY_FIELDS = (
    "primary_concern",
    "concern_duration",
    "triggering_subject",
    "triggering_context",
    "functional_impact",
    "core_belief",
    "active_issue_source",
    "active_thread_summary",
)


def _clean_context_value(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "unknown", "not specified", "n/a"}:
        return ""
    return " ".join(text.split())[:240]


# Human-readable phrases for the remaining signal a complement technique targets.
# Used to build pending_complement_signal so the agent can name the concrete issue
# ("an exercise for the racing thoughts") instead of a vague "something else".
_COMPLEMENT_SIGNAL_PHRASES = {
    "rumination": "the looping thoughts",
    "racing_thoughts": "the racing thoughts",
    "obsessive_thoughts": "the intrusive thoughts",
    "worry": "the worry",
    "catastrophizing": "the worst-case thinking",
    "fear_of_failure": "the fear of failing",
    "feeling_disrespected": "the feeling of being disrespected",
    "anger": "the anger that's still sitting with you",
    "resentment": "the resentment",
    "shame": "the shame",
    "guilt": "the guilt",
    "self_criticism": "the harsh self-talk",
    "self_blame": "the self-blame",
    "hopelessness": "the hopelessness",
    "low_mood": "the low mood",
    "loneliness": "the loneliness",
    "avoidance": "the avoidance",
    "procrastination": "the procrastination",
}

# Context tags → phrase, checked before sub-emotions when present.
_COMPLEMENT_CONTEXT_PHRASES = {
    "teacher_conflict": "the situation with your teacher",
    "school_conflict": "what happened at school",
    "family_conflict": "the conflict at home",
    "relationship_conflict": "the relationship strain",
    "work_stress": "the pressure at work",
    "social_humiliation": "feeling humiliated",
    "bedtime_rumination": "the night-time overthinking",
    "sleep_difficulty": "the trouble sleeping",
    "nighttime_worry": "the night-time worry",
}


def _describe_complement_signal(complement: dict, state: MentalHealthState) -> str:
    """
    Build a concrete, human-readable description of the remaining concern the
    complement technique addresses (different from the acute signal the primary
    just handled). Prefers a triggering context, then the complement's own target
    sub-emotions, then the user's secondary emotions, then the category.
    """
    contexts = [str(c).lower() for c in (state.get("detected_contexts") or []) if c]
    for ctx in contexts:
        if ctx in _COMPLEMENT_CONTEXT_PHRASES:
            return _COMPLEMENT_CONTEXT_PHRASES[ctx]

    # The complement's own target sub-emotions (DB metadata) describe what it treats.
    comp_targets = [
        str(s).lower()
        for s in (complement.get("matched_sub_emotions")
                  or complement.get("targetSubEmotions")
                  or complement.get("target_sub_emotions")
                  or [])
        if s
    ]
    secondary = [str(s).lower() for s in (state.get("secondary_sub_emotions") or []) if s]
    primary_sub = str(state.get("primary_sub_emotion") or "").lower()
    behaviors = [str(b).lower() for b in (state.get("detected_behaviors") or []) if b]

    for signal in (*comp_targets, primary_sub, *secondary, *behaviors):
        if signal in _COMPLEMENT_SIGNAL_PHRASES:
            return _COMPLEMENT_SIGNAL_PHRASES[signal]

    # Category-based fallback.
    category = str(complement.get("category") or "").lower()
    if category in {"cbt", "journaling"}:
        return "the thoughts that are still weighing on you"
    if category == "behavioral activation":
        return "getting some momentum back"
    if category == "dbt":
        return "the intensity of the emotion underneath"
    return "what's still sitting with you"


def _build_technique_need_query(
    *,
    user_message: str,
    emotion: str,
    intensity: float,
    primary_sub_emotion: str,
    secondary_sub_emotions: list[str],
    detected_symptoms: list[str],
    detected_behaviors: list[str],
    detected_contexts: list[str],
    state: MentalHealthState,
) -> str:
    """
    Build the semantic retrieval query for DB exercise selection.

    The latest message may be only "yes sure" after follow-up consent. This
    query carries forward the clinical/context formulation so pgvector reranking
    selects an exercise for the actual condition, not the short acceptance text.
    """
    parts: list[str] = [
        f"emotion: {emotion}",
        f"intensity: {float(intensity or 0.0):.2f}",
    ]
    if primary_sub_emotion:
        parts.append(f"primary feeling: {primary_sub_emotion}")
    if secondary_sub_emotions:
        parts.append(f"secondary feelings: {', '.join(secondary_sub_emotions[:4])}")
    if detected_symptoms:
        parts.append(f"symptoms: {', '.join(detected_symptoms[:6])}")
    if detected_behaviors:
        parts.append(f"behaviors: {', '.join(detected_behaviors[:6])}")
    if detected_contexts:
        parts.append(f"context tags: {', '.join(detected_contexts[:6])}")

    distortion_type = _clean_context_value(state.get("distortion_type"))
    if distortion_type:
        parts.append(f"thinking pattern: {distortion_type}")

    for field in _TECHNIQUE_QUERY_FIELDS:
        value = _clean_context_value(state.get(field))
        if value:
            parts.append(f"{field.replace('_', ' ')}: {value}")

    latest = _clean_context_value(user_message)
    if latest and latest.lower() not in {"yes", "yeah", "yep", "sure", "yes sure", "ok", "okay"}:
        parts.append(f"latest message: {latest}")

    return " | ".join(dict.fromkeys(parts))[:1800]


async def select_technique(state: MentalHealthState) -> dict:
    """
    TECHNIQUE SELECTOR NODE - Deterministic technique selection.

    Process:
    1. Check planner strategy - skip if user not ready
    2. Get detected emotion + intensity from state (prefers fused values)
    3. Query database for top-3 techniques (intensity-routed, unused-first)
    4. primary = top 1, alternatives = items 2 & 3
    5. Store all in state for SSE streaming to frontend

    No LLM involved - pure database queries

    Output State:
        - recommended_technique:           Single best technique dict
        - recommended_techniques_by_category: {category: technique} (single entry, for UI compat)
        - alternative_techniques:          List of up to 2 alternative dicts
    """

    try:
        # --- Planner gating ---
        strategy = state.get("conversation_strategy", "validate_only")
        readiness = state.get("technique_readiness", 0.0)
        stage = state.get("conversation_stage", "DISCOVERY")
        needs_technique = state.get("needs_technique", False)
        intent = state.get("intent", "")
        gate_route = state.get("gate_route", "")
        gate_flags = state.get("gate_context_flags") or []
        current_emotion = str(state.get("fused_emotion", state.get("emotion", "neutral")) or "neutral")
        current_intensity = float(state.get("fused_intensity", state.get("intensity", 0.5)) or 0.0)
        messages = state.get("messages", [])
        user_message = messages[-1].content if messages else ""
        short_consent_turn = is_short_consent_turn(gate_route, gate_flags, user_message)
        anchored_emotion = anchored_negative_emotion(state)
        anchor_intensity = distress_anchor_value(state)

        emotion = current_emotion
        # Emotion priority for technique selection (v12.0):
        # 1. Short consent/acceptance turns inherit the anchored negative emotion.
        # 2. If the current emotion is low-signal (neutral/joy) but a negative
        #    emotion anchor exists AND a therapeutic thread is active, inherit the
        #    anchored emotion.  Without this, a "yes share it" turn that reads as
        #    neutral would query for NEUTRAL techniques even after intensity is
        #    correctly floored - fixing intensity without fixing the emotion label
        #    still selects techniques for a calm person.
        # 3. Current negative emotion stays current.
        # 4. Otherwise keep the current emotion.
        if short_consent_turn and anchored_emotion in NEGATIVE_EMOTIONS:
            emotion = anchored_emotion
        elif current_emotion.lower() in LOW_SIGNAL_EMOTIONS and anchored_emotion in NEGATIVE_EMOTIONS and has_active_therapeutic_thread(state):
            emotion = anchored_emotion
            print(
                f"[TECHNIQUE] Emotion inherited from anchor: "
                f"{current_emotion.upper()} -> {emotion.upper()} "
                f"(low-signal turn with active therapeutic thread)"
            )
        elif current_emotion.lower() in NEGATIVE_EMOTIONS:
            emotion = current_emotion

        intensity = max(current_intensity, anchor_intensity)
        # v12.0: Thread-aware intensity floor for technique selection.
        # If the selector is about to fire (needs_technique=True) and intensity is
        # still low-signal despite emotion inheritance, apply a 0.45 floor when a
        # therapeutic thread is known.  This is the last-resort catch for cases
        # where all three upstream fixes still couldn't write a meaningful anchor.
        if needs_technique and intensity < 0.45 and has_active_therapeutic_thread(state):
            intensity = 0.45
            print(
                f"[TECHNIQUE] Thread-aware intensity floor applied: "
                f"{current_intensity:.0%} -> 0.45 (therapeutic thread active, needs_technique=True)"
            )

        primary_sub_emotion = (state.get("primary_sub_emotion") or "").lower()
        distortion_type = (state.get("distortion_type") or "").lower()
        secondary_sub_emotions = [
            str(item).lower() for item in (state.get("secondary_sub_emotions") or []) if item
        ]
        detected_symptoms = [
            str(item).lower() for item in (state.get("detected_symptoms") or []) if item
        ]
        detected_behaviors = [
            str(item).lower() for item in (state.get("detected_behaviors") or []) if item
        ]
        detected_contexts = [
            str(item).lower() for item in (state.get("detected_contexts") or []) if item
        ]

        context_ready_override = any(
            flag in gate_flags
            for flag in ("context_complete", "no_more_details", "followup_limit_reached")
        )
        has_action_signal = any(
            flag in gate_flags
            for flag in ("therapeutic_action_ready", "help_request", "explicit_technique_request", "accept_technique")
        )

        _empty = {
            "recommended_technique": {},
            "recommended_techniques_by_category": {},
            "alternative_techniques": [],
            "technique_area": state.get("technique_area") or [],
            "technique_plan_mode": state.get("technique_plan_mode") or "single",
            "technique_series": [],
        }

        def _selection_fields() -> dict:
            return {
                "technique_selection_emotion": emotion,
                "technique_selection_intensity": float(intensity),
            }

        # ============================================
        # v11.0: CONSENT HARD GATE (belt-and-suspenders)
        # Runs before ANY other check. If the user has denied exercise consent
        # or is in listen-only mode, never fetch a technique from the DB.
        # This overrides even needs_technique=True from the planner.
        # ============================================
        exercise_consent = state.get("exercise_consent", "unknown")
        solution_preference = state.get("solution_preference", "unknown")
        response_task = state.get("response_task", "")
        is_permission_recheck = (response_task == "ask_permission_before_technique")

        # ============================================
        # SERIES COMPLEMENT PROMOTION
        # The planner routed to offer_complement_technique because a complement was
        # queued and the user accepted it. Promote the queued technique directly —
        # no fresh re-selection — so the SAME exercise that was offered gets delivered
        # (was previously replaced by an unrelated fresh pick).
        # ============================================
        if response_task == "offer_complement_technique":
            _comp = state.get("pending_complement_technique") or (
                (state.get("alternative_techniques") or [None])[0]
            )
            if _comp and isinstance(_comp, dict) and _comp.get("name"):
                cat_name = _comp.get("category", "Recommended")
                print(f"[ACCEPT_COMPLEMENT] Promoting queued complement: {_comp['name']}")
                return {
                    "recommended_technique": _comp,
                    "recommended_techniques_by_category": {cat_name: _comp},
                    "alternative_techniques": [_comp],
                    "latest_recommended_technique": _comp,
                    "technique_series": [_comp],
                    "technique_plan_mode": "single",
                    # Consumed — clear so it isn't re-offered next turn.
                    "pending_complement_technique": None,
                    "pending_complement_signal": None,
                    **_selection_fields(),
                }

        # v12.0: PRE-SELECT on permission turn.
        # Run full selection now so the right technique is locked in state.
        # We store it in pending_recommended_technique and return _empty (no
        # sidebar display yet) so the UI only shows it after consent.
        if is_permission_recheck:
            pending_already = state.get("pending_recommended_technique")
            if pending_already and isinstance(pending_already, dict) and pending_already.get("name"):
                # Tier 1: gate flags (fast path)
                _gate_flags_sel = list(state.get("gate_context_flags") or [])
                _has_new_context = any(f in _gate_flags_sel for f in {
                    "context_detail_answer",
                    "rich_context_answer",
                    "new_emotional_disclosure",
                })
                if _has_new_context:
                    print(
                        f"[TECHNIQUE_PENDING] New context flags {[f for f in _gate_flags_sel if f in {'context_detail_answer','rich_context_answer','new_emotional_disclosure'}]} "
                        f"— re-selecting despite pending '{pending_already['name']}'"
                    )
                else:
                    # Tier 2: deep clinical signal diff (emotion, sub-emotions, symptoms, behaviors)
                    _snap = state.get("pending_technique_context_snapshot") or {}
                    _cur_symptoms  = set(state.get("detected_symptoms") or [])
                    _snap_symptoms = set(_snap.get("detected_symptoms") or [])
                    _cur_sub  = {state.get("primary_sub_emotion", "")} | set(state.get("secondary_sub_emotions") or [])
                    _snap_sub = {_snap.get("primary_sub_emotion", "")} | set(_snap.get("secondary_sub_emotions") or [])
                    _cur_beh  = set(state.get("detected_behaviors") or [])
                    _snap_beh = set(_snap.get("detected_behaviors") or [])
                    _cur_emo  = state.get("fused_emotion") or state.get("emotion", "")
                    _snap_emo = _snap.get("emotion", "")

                    _new_symptoms  = _cur_symptoms - _snap_symptoms
                    _new_sub       = _cur_sub - _snap_sub - {"", None}
                    _new_behaviors = _cur_beh - _snap_beh
                    _emotion_shift = (_cur_emo != _snap_emo) and bool(_cur_emo) and bool(_snap_emo)

                    if _new_symptoms or _new_sub or _new_behaviors or _emotion_shift:
                        _changes: list[str] = []
                        if _new_symptoms:  _changes.append(f"symptoms={_new_symptoms}")
                        if _new_sub:       _changes.append(f"sub_emotions={_new_sub}")
                        if _new_behaviors: _changes.append(f"behaviors={_new_behaviors}")
                        if _emotion_shift: _changes.append(f"emotion={_snap_emo}→{_cur_emo}")
                        print(
                            f"[TECHNIQUE_PENDING] Clinical signals changed {_changes} "
                            f"— re-selecting despite pending '{pending_already['name']}'"
                        )
                        _has_new_context = True
                    else:
                        print(
                            f"[TECHNIQUE_PENDING] Already stored '{pending_already['name']}' - no new context, skipping re-select"
                        )
                        return _empty
            # Fall through to the full selection logic below, but remember to
            # stash the result instead of returning it directly.
            # We set a flag so the post-selection code knows to reroute.
            _pre_select_for_pending = True
        else:
            _pre_select_for_pending = False

        if (
            exercise_consent in {"denied_hard", "denied_soft"}
            or solution_preference == "listen_only"
        ):
            # v14.0: acute physical distress overrides prior consent denial — the user
            # needs grounding now even if they previously declined exercises.
            _imm_reg_override = (
                state.get("immediate_regulation_request")
                or response_task == "start_grounding_now"
            )
            if _imm_reg_override:
                print(
                    f"[TECHNIQUE] CONSENT GATE OVERRIDDEN for immediate regulation "
                    f"(exercise_consent={exercise_consent}) — acute distress takes priority"
                )
            else:
                print(
                    f"[TECHNIQUE] CONSENT GATE BLOCKED - "
                    f"exercise_consent={exercise_consent}, solution_preference={solution_preference}, response_task={response_task}"
                )
                return _empty

        if not needs_technique:
            print(f"[TECHNIQUE] Skipping (needs_technique=false, stage={stage}, intent={intent})")
            return _empty

        if (
            primary_sub_emotion in NO_TECHNIQUE_BY_DEFAULT_SUB_EMOTIONS
            and intent not in {"technique_request", "accept_technique"}
            and not has_action_signal
        ):
            print(
                f"[TECHNIQUE] Skipping (sub-emotion '{primary_sub_emotion}' is empathy/conversation-first)"
            )
            return _empty

        if (
            gate_route == "contextual_followup"
            and intent == "contextual_followup"
            and str(emotion).lower() in _LOW_SIGNAL_EMOTIONS
            and float(intensity or 0.0) < 0.35
            and not has_action_signal
        ):
            print(
                "[TECHNIQUE] Skipping (low-signal contextual follow-up; "
                "context_complete does not imply exercise readiness)"
            )
            return _empty

        if (
            gate_route in {"memory_query", "contextual_followup", "chitchat", "positive_feedback"}
            and intent not in {"technique_request", "accept_technique"}
            and not context_ready_override
        ):
            print(f"[TECHNIQUE] Skipping (gate route blocks techniques: gate={gate_route}, intent={intent})")
            return _empty

        if (
            gate_route == "technique_follow_up"
            and ("reject_technique" in gate_flags or "technique_rejection" in gate_flags)
        ):
            print("[TECHNIQUE] Skipping (technique rejection follow-up)")
            return _empty

        if stage in {"DISCOVERY", "UNDERSTANDING"} or intent in {"asking_opinion", "memory_query", "reject_technique", "positive_feedback"}:
            print(f"[TECHNIQUE] Skipping (stage/intent blocks techniques: stage={stage}, intent={intent})")
            return _empty

        if intent == "contextual_followup" and not context_ready_override:
            print(f"[TECHNIQUE] Skipping (contextual follow-up still gathering context)")
            return _empty

        # v13.0: Context sufficiency gate.
        # If the planner hasn't gathered enough formulation slots yet, do not
        # fire a technique. Direct requests (intent=technique_request / accept_technique)
        # and explicit action signals always bypass this gate.
        context_sufficiency = float(state.get("context_sufficiency") or 0.0)
        if (
            context_sufficiency < 0.65
            and intent not in {"technique_request", "accept_technique"}
            and not has_action_signal
            and not context_ready_override
        ):
            print(
                f"[TECHNIQUE] Skipping (context_sufficiency={context_sufficiency:.0%} < 65%; "
                "more context needed before technique selection)"
            )
            return _empty

        if intent == "accept_technique":
            # v12.0: check pending_recommended_technique FIRST - this is the
            # technique pre-selected when we asked permission. Using it avoids
            # re-running selection from a weak 'yes' context.
            _pending = state.get("pending_recommended_technique")
            if _pending and isinstance(_pending, dict) and _pending.get("name"):
                cat_name = _pending.get("category", "Recommended")
                print(
                    f"[ACCEPT_TECHNIQUE] Promoting pending '{_pending['name']}' - "
                    f"no re-selection needed. Reason: {state.get('pending_technique_reason', 'pre-selected')}"
                )
                return {
                    "recommended_technique": _pending,
                    "recommended_techniques_by_category": {cat_name: _pending},
                    "alternative_techniques": [],
                    "latest_recommended_technique": _pending,
                    # clear pending slot once promoted
                    "pending_recommended_technique": None,
                    "pending_technique_reason": None,
                    "pending_technique_created_at_turn": None,
                    "pending_technique_context_snapshot": None,
                    **_selection_fields(),
                }

            # Fallback: try active_technique / latest_recommended_technique
            latest = state.get("active_technique") or state.get("latest_recommended_technique") or {}
            if latest and latest.get("name"):
                cat_name = latest.get("category", "Recommended")
                print(f"[ACCEPT_TECHNIQUE] Reusing in-session technique: {latest.get('name')}")
                return {
                    "recommended_technique": latest,
                    "recommended_techniques_by_category": {cat_name: latest},
                    "alternative_techniques": [],
                    "latest_recommended_technique": latest,
                    **_selection_fields(),
                }

            # Nothing found - fall through to fresh selection with best available context
            print(
                "[ACCEPT_TECHNIQUE] No pending or active technique found - "
                "running fresh selection (context-anchored path)"
            )

        # `rejected` must be defined before the reuse-check below so it's
        # always in scope when referenced after recommend_technique returns.
        rejected = state.get("latest_rejected_technique") or {}

        # v11.1: BUG FIX - Do NOT reuse stale technique when asking permission.
        # During ask_permission_before_technique the agent is checking whether the
        # user WANTS a technique - pre-loading the old technique would surface it
        # in the sidebar prematurely and confuse the consent flow.
        if response_task != "ask_permission_before_technique":
            latest = state.get("active_technique") or state.get("latest_recommended_technique") or {}
            latest_name = (latest.get("name") or "").strip().lower() if isinstance(latest, dict) else ""
            rejected_name = (rejected.get("name") or "").strip().lower() if isinstance(rejected, dict) else ""
            if latest_name and latest_name != rejected_name:
                cat_name = latest.get("category", "Recommended")
                print(f"[TECHNIQUE] Reusing in-session technique: {latest.get('name')}")
                return {
                    "recommended_technique": latest,
                    "recommended_techniques_by_category": {cat_name: latest},
                    "alternative_techniques": [],
                    "latest_recommended_technique": latest,
                    **_selection_fields(),
                }

        skip_strategies = {"validate_only", "ask_question", "encourage_reflection", "no_action"}
        if strategy in skip_strategies:
            print(f"[TECHNIQUE] Skipping (strategy: {strategy}, readiness: {readiness:.0%})")
            return _empty

        # --- Inputs ---
        user_id = state.get("user_id", "")
        print(
            f"[TECHNIQUE] intensity={current_intensity:.0%} "
            f"elevated_to_anchor={intensity:.0%} for tier selection"
        )
        if short_consent_turn and current_emotion.lower() in LOW_SIGNAL_EMOTIONS and emotion != current_emotion:
            print(
                f"[TECHNIQUE] emotion={current_emotion.upper()} "
                f"anchored_to={emotion.upper()} for consent selection"
            )

        technique_need_query = _build_technique_need_query(
            user_message=user_message,
            emotion=str(emotion),
            intensity=float(intensity or 0.0),
            primary_sub_emotion=primary_sub_emotion,
            secondary_sub_emotions=secondary_sub_emotions,
            detected_symptoms=detected_symptoms,
            detected_behaviors=detected_behaviors,
            detected_contexts=detected_contexts,
            state=state,
        )

        _bar = "─" * 64
        print(f"\n┌{_bar}┐")
        print(f"│  TECHNIQUE SELECTOR  — context snapshot")
        print(f"├{_bar}┤")
        print(f"│  Emotion    : {emotion.upper():<20}  Intensity : {intensity:.0%}")
        print(f"│  Sub-emotion: {primary_sub_emotion or 'n/a':<20}  Strategy  : {strategy}")
        print(f"│  Readiness  : {readiness:.0%}")
        if secondary_sub_emotions:
            print(f"│  Secondary  : {', '.join(secondary_sub_emotions)}")
        if detected_symptoms:
            print(f"│  Symptoms   : {', '.join(detected_symptoms)}")
        if detected_behaviors:
            print(f"│  Behaviors  : {', '.join(detected_behaviors)}")
        if detected_contexts:
            print(f"│  Contexts   : {', '.join(detected_contexts)}")
        if distortion_type:
            print(f"│  Distortion : {distortion_type}")
        print(f"│  Query(220) : {technique_need_query[:220]}")
        print(f"└{_bar}┘")

        start_time = time.time()

        # Fetch a safe semantic shortlist. The response LLM can choose the final
        # exercise from these candidates without adding another model call.
        top3: list = await recommend_technique.ainvoke({
            "emotion": emotion,
            "intensity": intensity,
            "user_id": user_id,
            # Issue 3 fix: pass clinical indicators so contraindicatedFlags
            # safety filter actually fires (was always empty before).
            "clinical_indicators": state.get("clinical_indicators") or [],
            "query": technique_need_query,
            "primary_sub_emotion": primary_sub_emotion,
            "secondary_sub_emotions": secondary_sub_emotions,
            "detected_symptoms": detected_symptoms,
            "detected_behaviors": detected_behaviors,
            "detected_contexts": detected_contexts,
            "distortion_type": distortion_type,
            "allow_general_fallback": intent in {"technique_request", "accept_technique"} or has_action_signal,
            "limit": 8,
        })

        elapsed_ms = int((time.time() - start_time) * 1000)

        if not top3:
            print(f"[TECHNIQUE] No candidates found for {emotion} ({elapsed_ms}ms)")
            return _empty

        rejected_name = (rejected.get("name") or "").strip().lower() if isinstance(rejected, dict) else ""
        filtered = [
            t for t in top3
            if not rejected_name or (t.get("name") or "").strip().lower() != rejected_name
        ]
        if not filtered:
            print(f"[TECHNIQUE] All candidates rejected ({rejected_name})")
            return _empty

        # v11.0: Filter out techniques that match suppressed topic labels
        from .consent_parser import get_suppressed_topic_labels

        suppressed_labels = get_suppressed_topic_labels(state)
        if suppressed_labels:
            _lower_labels = [lbl.lower() for lbl in suppressed_labels]
            pre_filter_count = len(filtered)
            filtered = [
                t for t in filtered
                if not any(
                    lbl in (t.get("name") or "").lower()
                    or lbl in (t.get("description") or "").lower()
                    or lbl in (t.get("category") or "").lower()
                    for lbl in _lower_labels
                )
            ]
            dropped = pre_filter_count - len(filtered)
            if dropped:
                print(
                    f"[TECHNIQUE] Dropped {dropped} technique(s) matching suppressed labels: "
                    f"{suppressed_labels}"
                )
            if not filtered:
                print("[TECHNIQUE] All candidates suppressed - skipping")
                return _empty

        # ============================================
        # v13.0: RERANK & FILTER CANDIDATES BY USER GOAL
        # Boost category scoring when latest_user_need is set.
        # Force breathing/grounding for immediate_regulation_request.
        # ============================================
        latest_user_need = state.get("latest_user_need")
        immediate_regulation_request = state.get("immediate_regulation_request", False)
        response_task = state.get("response_task", "")

        _GOAL_CATEGORY_BOOST = {
            "calm_body_now": ["breathing", "grounding"],
            "reach_out_to_friend": ["behavioral_activation", "social_skills"],
            "write_simple_message": ["behavioral_activation", "social_skills"],
            "know_where_to_start": ["behavioral_activation", "cbt"],
            "break_project_into_steps": ["behavioral_activation", "cbt"],
            "stop_overthinking_at_night": ["dbt", "mindfulness", "cbt"],
            "sleep_better": ["mindfulness", "breathing"],
        }

        if immediate_regulation_request or response_task == "start_grounding_now":
            # v13.2: Series-aware filter — when planner set technique_plan_mode="series" (multi-domain symptoms),
            # keep breathing as primary AND include best cognitive/CBT technique as complement.
            _imm_series = str(state.get("technique_plan_mode") or "single").lower() == "series"
            physical_techs = [t for t in filtered if (t.get("category") or "").lower() in ("breathing", "grounding")]
            cognitive_techs = [t for t in filtered if (t.get("category") or "").lower() not in ("breathing", "grounding")]

            if _imm_series and physical_techs and cognitive_techs:
                filtered = physical_techs[:1] + cognitive_techs[:1]
                print("[TECHNIQUE] v13.2: Immediate regulation SERIES — breathing/grounding + cognitive complement")
            elif physical_techs:
                filtered = physical_techs
                print("[TECHNIQUE] v13.0: Filtered shortlist to breathing/grounding only (single immediate regulation)")
            else:
                print("[TECHNIQUE] v13.0: No breathing/grounding in shortlist, prioritizing at top")
                filtered = sorted(
                    filtered,
                    key=lambda x: 0 if (x.get("category") or "").lower() in ("breathing", "grounding") else 1
                )
        elif latest_user_need in _GOAL_CATEGORY_BOOST:
            boosted_categories = _GOAL_CATEGORY_BOOST[latest_user_need]

            def _sort_key(t):
                cat = (t.get("category") or "").lower()
                for idx, b_cat in enumerate(boosted_categories):
                    if b_cat in cat:
                        return idx
                return len(boosted_categories)

            filtered = sorted(filtered, key=_sort_key)
            print(f"[TECHNIQUE] v13.0: Reranked candidates for user need '{latest_user_need}' using categories: {boosted_categories}")

        technique_candidates = filtered[:8]

        # ── SEMANTIC SEARCH RESULTS log ────────────────────────────────
        _sbar = "─" * 64
        print(f"\n┌{_sbar}┐")
        print(f"│  SEMANTIC SEARCH RESULTS  ({elapsed_ms}ms) — {len(top3)} raw hits, {len(filtered)} after filter")
        print(f"├{_sbar}┤")
        for _ri, _rc in enumerate(technique_candidates, 1):
            _rc_reasons = "; ".join((_rc.get("score_reasons") or [])[:3]) or "semantic match"
            _rc_int = f"{_rc.get('min_intensity', 0):.0%}–{_rc.get('max_intensity', 1):.0%}"
            print(f"│  {_ri:>2}. {_rc.get('name', '?'):<35} [{_rc.get('category', '?')}]")
            print(f"│      Reasons : {_rc_reasons[:80]}")
            print(f"│      Intensity: {_rc_int}")
        print(f"└{_sbar}┘")
        # ───────────────────────────────────────────────────────────────

        primary = technique_candidates[0]

        technique_plan_mode = str(state.get("technique_plan_mode") or "single").lower()
        technique_area = [
            str(area).strip()
            for area in (state.get("technique_area") or [])
            if str(area or "").strip()
        ][:4]
        series_allowed = (
            technique_plan_mode == "series"
            or bool(state.get("series_requested"))
        )
        raw_alternatives = technique_candidates[1:3] if series_allowed else []

        # Diversity enforcement: prefer a complement that targets a DIFFERENT primary signal
        # so the two techniques address distinct aspects of the user's emotional state.
        if raw_alternatives and series_allowed:
            primary_top_sub = str(primary.get("matched_sub_emotions", [None])[0]
                                  if primary.get("matched_sub_emotions")
                                  else (primary.get("targetSubEmotions") or [None])[0] or "").lower()
            diverse_alt = next(
                (
                    t for t in raw_alternatives
                    if str(
                        (t.get("matched_sub_emotions") or t.get("targetSubEmotions") or [None])[0] or ""
                    ).lower() != primary_top_sub
                ),
                raw_alternatives[0],  # fallback to highest-scored if no diversity found
            )
            alternatives = [diverse_alt]
            if diverse_alt.get("name") != raw_alternatives[0].get("name"):
                print(
                    f"[TECHNIQUE]  Diversity swap: {raw_alternatives[0].get('name')} → "
                    f"{diverse_alt.get('name')} (different signal cluster)"
                )
        else:
            alternatives = raw_alternatives

        # v14.0: Series mode safety net — if diversity filter or DB shortage left
        # alternatives empty, use the second candidate as-is so series mode doesn't
        # silently degrade to single-exercise delivery.
        if series_allowed and not alternatives and len(technique_candidates) > 1:
            alternatives = [technique_candidates[1]]
            print("[TECHNIQUE] Series fallback: diversity filter emptied alternatives — using 2nd candidate")

        cat_name = primary.get("category", "Recommended")
        _top_reason = (
            "; ".join(primary.get("score_reasons", [])) or
            f"best match for {emotion.lower()} at {intensity:.0%} intensity"
        )
        _bar2 = "─" * 64
        print(f"\n┌{_bar2}┐")
        print(f"│  TECHNIQUE SELECTION RESULT  ({elapsed_ms}ms)")
        print(f"├{_bar2}┤")
        print(f"│  ★ SELECTED : {primary.get('name')} [{cat_name}]")
        print(f"│    Reason   : {_top_reason[:90]}")
        if alternatives:
            print(f"│  Shortlist  :")
            for _i, _alt in enumerate(technique_candidates, start=1):
                _marker = "★" if _alt.get("name") == primary.get("name") else " "
                _alt_reasons = "; ".join((_alt.get("score_reasons") or [])[:2]) or "semantic match"
                print(f"│    {_i}. {_marker} {_alt.get('name')} [{_alt.get('category','?')}]  — {_alt_reasons[:60]}")
        print(f"└{_bar2}┘")

        if _pre_select_for_pending:
            _bar3 = "─" * 64
            print(f"\n┌{_bar3}┐")
            print(f"│  TECHNIQUE PRE-SELECTED (pending consent)")
            print(f"│  Exercise : {primary['name']} [{cat_name}]")
            print(f"│  Reason   : {_top_reason[:90]}")
            print(f"│  Status   : stored as pending — awaiting user permission")
            print(f"└{_bar3}┘")
            return {
                **_empty,
                "pending_recommended_technique": primary,
                "pending_technique_reason": _top_reason,
                "pending_technique_created_at_turn": state.get("session_message_count", 0),
                "technique_candidates": technique_candidates,
                "pending_technique_context_snapshot": {
                    "emotion": state.get("fused_emotion") or state.get("emotion", ""),
                    "primary_sub_emotion": state.get("primary_sub_emotion", ""),
                    "secondary_sub_emotions": sorted(list(state.get("secondary_sub_emotions") or [])),
                    "detected_symptoms": sorted(list(state.get("detected_symptoms") or [])),
                    "detected_behaviors": sorted(list(state.get("detected_behaviors") or [])),
                    "intensity": float(state.get("fused_intensity") or state.get("intensity") or 0.0),
                },
            }

        # Build category dict: primary first, then alternatives (keyed uniquely)
        _rec_by_cat: dict = {cat_name: primary}
        for _idx, _alt in enumerate(alternatives):
            _alt_cat = _alt.get("category", f"Alternative_{_idx + 1}")
            # Avoid key collision if same category - suffix with index
            _key = _alt_cat if _alt_cat not in _rec_by_cat else f"{_alt_cat}_{_idx + 1}"
            _rec_by_cat[_key] = _alt

        technique_series = [primary, *alternatives] if series_allowed else [primary]

        # Queue the complement as an explicit, persisted pending object so it can be
        # surfaced deterministically after the primary and reused consistently when the
        # user accepts it or raises the signal it targets (instead of a fresh re-select).
        _pending_complement = None
        _pending_complement_signal = None
        if series_allowed and alternatives:
            _pending_complement = alternatives[0]
            _pending_complement_signal = _describe_complement_signal(_pending_complement, state)
            print(
                f"[TECHNIQUE] Complement queued: {_pending_complement.get('name')} "
                f"→ targets '{_pending_complement_signal}'"
            )

        return {
            "recommended_technique": primary,
            "recommended_techniques_by_category": _rec_by_cat,
            "alternative_techniques": alternatives,
            "technique_candidates": technique_candidates,
            "latest_recommended_technique": primary,
            "technique_area": technique_area,
            "technique_plan_mode": "series" if series_allowed else "single",
            "technique_series": technique_series,
            "pending_complement_technique": _pending_complement,
            "pending_complement_signal": _pending_complement_signal,
            **_selection_fields(),
        }

    except Exception as e:
        print(f"[TECHNIQUE] Error: {str(e)[:80]}")
        return {
            "recommended_technique": {},
            "recommended_techniques_by_category": {},
            "alternative_techniques": [],
        }
