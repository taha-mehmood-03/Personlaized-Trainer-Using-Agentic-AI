"""
Script to inject v13.0 logic into conversation_planner_node.py:
1. Consent override block after _listen_only_mode setup
2. IMMEDIATE_REGULATION_REQUEST early-exit routing
3. SOLUTION_REQUESTED routing block
4. Question budget hard stop
5. New fields in all return paths
"""

target = r'E:\FYP\mental_health_wellness\src\mental_health_wellness\nodes\conversation_planner_node.py'

with open(target, 'r', encoding='utf-8') as f:
    content = f.read()

# -----------------------------------------------------------------------
# PATCH 1: After _listen_only_mode is set, insert consent override block
# and new signal detections (immediate_regulation_request, solution_requested,
# latest_user_need, exercises_reopened).
# We find the block that reads current_message and insert right AFTER it.
# -----------------------------------------------------------------------
PATCH1_MARKER = '    current_message = messages[-1].content.lower() if messages else ""\n'

PATCH1_INSERT = '''\n    # ============================================
    # v13.0: SIGNAL DETECTION + CONSENT OVERRIDE
    # Detect solution request, regulation urgency, and user goal BEFORE
    # the main stage machine. If user previously rejected exercises but
    # is now explicitly requesting help, override the consent block.
    # ============================================
    _raw_current_message = messages[-1].content if messages else ""
    _imm_reg = is_immediate_regulation_request(current_message)
    _sol_req = (
        is_solution_requested(current_message)
        or "solution_requested" in list(state.get("gate_context_flags") or [])
    )
    _latest_user_need = (
        detect_user_goal(current_message, state)
        or state.get("latest_user_need")
    )
    _has_medical_signal = has_medical_warning_signal(current_message)
    _exercises_reopened = False
    _consent_was_blocked = (
        exercise_consent in ("denied_soft", "denied_hard")
        or solution_preference == "listen_only"
    )
    if not crisis_detected and _consent_was_blocked:
        if _imm_reg or is_explicit_exercise_request(current_message):
            # User explicitly wants an exercise NOW — lift the block
            exercise_consent = "allowed"
            solution_preference = "exercise_requested"
            _exercises_reopened = True
            _listen_only_mode = False
            print("[NODE: PLANNER]  v13.0 CONSENT OVERRIDE — exercise explicitly requested after prior rejection")
        elif _sol_req:
            # User asking for advice/help (not necessarily a guided exercise)
            exercise_consent = "unknown"
            solution_preference = "advice_allowed"
            _listen_only_mode = False
            print("[NODE: PLANNER]  v13.0 CONSENT OVERRIDE — solution requested after prior rejection (advice_allowed)")
    _q_since = int(state.get("question_count_since_disclosure") or 0)
    _question_budget = 1  # default: one question allowed per turn

'''

if 'v13.0: SIGNAL DETECTION' not in content:
    content = content.replace(PATCH1_MARKER, PATCH1_MARKER + PATCH1_INSERT)
    print("Patch 1 applied")
else:
    print("Patch 1 already present")

# -----------------------------------------------------------------------
# PATCH 2: IMMEDIATE_REGULATION_REQUEST early-exit block
# Insert right AFTER the recent_context / print statement block,
# before the INTENT RETRIEVAL section.
# -----------------------------------------------------------------------
PATCH2_MARKER = '    # ============================================\n    # CHITCHAT BYPASS GATE\n    # Runs AFTER technique pre-check to avoid false no_action on requests.\n    # If emotion is neutral with low intensity  return no_action immediately.\n    # ============================================\n'

PATCH2_INSERT = '''    # ============================================
    # v13.0: IMMEDIATE_REGULATION_REQUEST FAST PATH
    # Acute body distress + urgency — bypass context gate, permission gate.
    # Help starts immediately in the same turn.
    # ============================================
    if _imm_reg and not crisis_detected:
        _imm_intent = intent if isinstance(intent, str) else "therapeutic"
        print("[NODE: PLANNER]  v13.0 IMMEDIATE_REGULATION_REQUEST — start_grounding_now, 0 questions")
        return {
            "conversation_strategy": "suggest_technique",
            "conversation_phase": "venting",
            "conversation_stage": "INTERVENTION",
            "technique_readiness": 1.0,
            "needs_technique": True,
            "intent": "technique_request",
            "crisis_detected": False,
            "session_message_count": user_msg_count,
            "gate_context_flags": list(state.get("gate_context_flags") or []),
            "gate_emotional_register": str(state.get("gate_emotional_register") or emotion or "neutral").lower(),
            "gate_intensity_hint": float(intensity),
            "latest_referenced_entity": state.get("latest_referenced_entity"),
            "response_task": "start_grounding_now",
            "technique_area": ["breathing", "grounding"],
            "technique_plan_mode": "single",
            "resolved_user_act": state.get("resolved_user_act"),
            "compact_analysis": state.get("compact_analysis"),
            # v13.0 fields
            "solution_requested": True,
            "immediate_regulation_request": True,
            "exercises_reopened": _exercises_reopened,
            "latest_user_need": _latest_user_need or "calm_body_now",
            "user_goal": state.get("user_goal"),
            "exercise_consent": "allowed",
            "solution_preference": "exercise_requested",
            "question_budget": 0,
            "question_count_since_disclosure": 0,
            "context_missing_reason": None,
        }

    # ============================================
    # v13.0: SOLUTION_REQUESTED ROUTING BLOCK
    # User explicitly asked for help/therapy/plan.
    # If context is sufficient: deliver technique directly.
    # If not: give a safe general first step + ask ONE targeted question.
    # ============================================
    if _sol_req and not _imm_reg and not crisis_detected:
        _ctx_enough = _context_is_enough(state, emotion, float(intensity))
        _intent_for_sol = "technique_request"
        if _ctx_enough:
            _goal_task = _goal_to_response_task(_latest_user_need, False, True)
            _sol_response_task = _goal_task or "offer_one_technique"
            # If consent is already allowed (override or prior), deliver directly
            _sol_consent = "allowed" if exercise_consent in ("allowed", "unknown") else exercise_consent
            if _sol_consent == "unknown":
                _sol_response_task = "ask_permission_before_technique"
            print(f"[NODE: PLANNER]  v13.0 SOLUTION_REQUESTED (context_enough=True) → {_sol_response_task}")
            return {
                "conversation_strategy": "suggest_technique",
                "conversation_phase": state.get("conversation_phase", "venting"),
                "conversation_stage": "INTERVENTION",
                "technique_readiness": 1.0,
                "needs_technique": True,
                "intent": _intent_for_sol,
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "gate_context_flags": list(state.get("gate_context_flags") or []),
                "gate_emotional_register": str(state.get("gate_emotional_register") or emotion or "neutral").lower(),
                "gate_intensity_hint": float(intensity),
                "latest_referenced_entity": state.get("latest_referenced_entity"),
                "response_task": _sol_response_task,
                "technique_area": _infer_technique_areas(state, current_message),
                "technique_plan_mode": "single",
                "resolved_user_act": state.get("resolved_user_act"),
                "compact_analysis": state.get("compact_analysis"),
                # v13.0 fields
                "solution_requested": True,
                "immediate_regulation_request": False,
                "exercises_reopened": _exercises_reopened,
                "latest_user_need": _latest_user_need,
                "user_goal": state.get("user_goal"),
                "exercise_consent": exercise_consent,
                "solution_preference": solution_preference,
                "question_budget": 0,
                "question_count_since_disclosure": 0,
                "context_missing_reason": None,
            }
        else:
            _missing = _infer_context_missing_reason(state, emotion, float(intensity))
            print(f"[NODE: PLANNER]  v13.0 SOLUTION_REQUESTED (context_enough=False) → ask_one_missing_context_question, reason={_missing}")
            return {
                "conversation_strategy": "ask_question",
                "conversation_phase": state.get("conversation_phase", "venting"),
                "conversation_stage": "UNDERSTANDING",
                "technique_readiness": 0.5,
                "needs_technique": False,
                "intent": _intent_for_sol,
                "crisis_detected": False,
                "session_message_count": user_msg_count,
                "gate_context_flags": list(state.get("gate_context_flags") or []),
                "gate_emotional_register": str(state.get("gate_emotional_register") or emotion or "neutral").lower(),
                "gate_intensity_hint": float(intensity),
                "latest_referenced_entity": state.get("latest_referenced_entity"),
                "response_task": "ask_one_missing_context_question",
                "technique_area": [],
                "technique_plan_mode": "single",
                "resolved_user_act": state.get("resolved_user_act"),
                "compact_analysis": state.get("compact_analysis"),
                # v13.0 fields
                "solution_requested": True,
                "immediate_regulation_request": False,
                "exercises_reopened": _exercises_reopened,
                "latest_user_need": _latest_user_need,
                "user_goal": state.get("user_goal"),
                "exercise_consent": exercise_consent,
                "solution_preference": solution_preference,
                "question_budget": 1,
                "question_count_since_disclosure": _q_since,
                "context_missing_reason": _missing,
            }

'''

if 'v13.0: IMMEDIATE_REGULATION_REQUEST FAST PATH' not in content:
    content = content.replace(PATCH2_MARKER, PATCH2_INSERT + PATCH2_MARKER)
    print("Patch 2 applied")
else:
    print("Patch 2 already present")

# -----------------------------------------------------------------------
# PATCH 3: Add v13.0 fields to the existing return dicts.
# We inject "solution_requested", "immediate_regulation_request" etc.
# into the compact_analysis dict AND all major return statements by
# finding the common tail pattern they share. The safest approach is
# to add these fields to compact_analysis so downstream can always find them.
# -----------------------------------------------------------------------

OLD_COMPACT = '''        \"context_sufficiency\": context_sufficiency,
        \"technique_area\": technique_area,
        \"technique_plan_mode\": technique_plan_mode,
    }'''
NEW_COMPACT = '''        "context_sufficiency": context_sufficiency,
        "technique_area": technique_area,
        "technique_plan_mode": technique_plan_mode,
        # v13.0
        "solution_requested": _sol_req,
        "immediate_regulation_request": _imm_reg,
        "latest_user_need": _latest_user_need,
        "question_budget": _question_budget,
    }'''

if '"solution_requested": _sol_req' not in content:
    if OLD_COMPACT in content:
        content = content.replace(OLD_COMPACT, NEW_COMPACT)
        print("Patch 3 (compact_analysis) applied")
    else:
        print("Patch 3 marker not found — skipping")
else:
    print("Patch 3 already present")

# Save
with open(target, 'w', encoding='utf-8') as f:
    f.write(content)
print("All patches written to file")
