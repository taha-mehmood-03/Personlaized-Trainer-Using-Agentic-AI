# Dynamic Context Gathering and Solution Request Handling

## What This Changes

Adds a two-tier lifecycle (`SOLUTION_REQUESTED` and `IMMEDIATE_REGULATION_REQUEST`), a quantitative context sufficiency gate, question budget enforcement, user-goal-aware technique selection, and hard stop rules on repeated context questions.

---

## Architecture Flow

```
User message
↓
turn_signals
    is_immediate_regulation_request()
    is_solution_requested()
    detect_user_goal()  → latest_user_need
    has_medical_warning_signal()
↓
_context_is_enough()  — uses problem signals, NOT message count
↓
conversation_planner_node
    immediate_regulation_request → start_grounding_now (0 questions, bypass permission)
    solution_requested + context_is_enough → offer_one_technique or goal-specific task
    solution_requested + NOT enough → give safe step + ask_one_missing_context_question
    question_budget enforced (0 or 1)
    consent override: exercise_consent="allowed" vs "unknown"
↓
technique_selector_node
    receives: solution_requested, immediate_regulation_request, latest_user_need, response_task
    latest_user_need boosts category scoring
↓
response_generator
    hard rules 26-29: ordering, question budget, medical safety guard, no repeat questions
↓
outcome_tracker  (after FOLLOW_UP stage)
```

---

## Key Design Decisions

> [!IMPORTANT]
> `IMMEDIATE_REGULATION_REQUEST` bypasses **both** the context gate and the permission gate. No "Would you like to try?" is ever asked. Help begins in the same message.

> [!IMPORTANT]
> `_context_is_enough()` checks what the system knows about the problem, not how many messages were exchanged. Message count alone is weak — the agent may have spent 4 turns gathering nothing meaningful.

> [!WARNING]
> Consent override distinguishes two cases: explicit exercise request → `exercise_consent="allowed"`, `solution_preference="exercise_requested"`; "what should I do?" → `exercise_consent="unknown"`, `solution_preference="advice_allowed"`. This prevents offering a full guided exercise when the user only asked for advice.

---

## Proposed Changes

---

### Component 1: State Schema

#### [MODIFY] [state.py](file:///E:/FYP/mental_health_wellness/src/mental_health_wellness/agent/state.py)

New fields in `MentalHealthState`:

```python
solution_requested: bool
immediate_regulation_request: bool
exercises_reopened: bool
latest_user_need: Optional[str]
user_goal: Optional[str]
question_count_since_disclosure: int
last_assistant_asked_question: bool
context_missing_reason: Optional[str]
question_budget: int
```

New defaults in `get_initial_state()`:

```python
solution_requested=False,
immediate_regulation_request=False,
exercises_reopened=False,
latest_user_need=None,
user_goal=None,
question_count_since_disclosure=0,
last_assistant_asked_question=False,
context_missing_reason=None,
question_budget=1,
```

---

### Component 2: Turn Signals Utility

#### [MODIFY] [turn_signals.py](file:///E:/FYP/mental_health_wellness/src/mental_health_wellness/utils/turn_signals.py)

**A. `is_immediate_regulation_request(text)`**

Returns True if the message contains body distress signals combined with an urgency or action signal (e.g. "help me calm", "right now", "please").

Body distress: chest tight/pain, can't breathe, heart racing, hands shaking, panic, dizzy, faint, trembling, "something bad is going to happen".

Urgency/action: "right now", "right away", "immediately", "now", "please", "help me calm", "calm me down", "ground me".

**B. `is_solution_requested(text)`**

Returns True for any explicit request for help, solution, therapy, technique, exercise, plan, or guidance. Excludes bare gratitude, "ok", "thanks", bare affirmations, short context answers.

Covers: "what should I do", "how can you help", "give me a plan", "fix this", "I need something right now", "tell me what to do", "where do I start", "I need a plan", "help me cope", "give me something to try", "what exercise should I do".

**C. `detect_user_goal(text, state) -> Optional[str]`**

Maps message content to a canonical user goal string:

| Pattern | Goal string |
|---|---|
| Body symptoms / panic | `"calm_body_now"` |
| Social connection / reaching out | `"reach_out_to_friend"` |
| Communication / messaging someone | `"write_simple_message"` |
| Overwhelmed / don't know next step | `"know_where_to_start"` |
| Night overthinking / rumination | `"stop_overthinking_at_night"` |
| Academic / project structure | `"break_project_into_steps"` |
| Reflective / understanding emotion | `"understand_my_emotion"` |
| Sleep | `"sleep_better"` |

Returns `None` if goal is unclear.

**D. `has_medical_warning_signal(text) -> bool`**

Returns True for: "chest pain", "severe chest", "chest hurts", "fainting", "about to faint", "losing consciousness", "cant breathe at all", "severe dizziness".

---

### Component 3: Conversation Planner Node

#### [MODIFY] [conversation_planner_node.py](file:///E:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/conversation_planner_node.py)

**A. New helper: `_context_is_enough(state, emotion, intensity) -> bool`**

```python
def _context_is_enough(state: dict, emotion: str, intensity: float) -> bool:
    has_emotion = (emotion or "neutral").lower() not in ("neutral", "")
    has_intensity = float(intensity or 0) > 0.20
    has_problem_signal = bool(
        state.get("primary_concern")
        or state.get("active_issue_source")
        or state.get("detected_contexts")
        or state.get("detected_behaviors")
        or state.get("detected_symptoms")
        or state.get("primary_sub_emotion")
        or state.get("distortion_type")
    )
    has_goal_signal = bool(
        (state.get("user_goal") or "").strip()
        or (state.get("latest_user_need") or "").strip()
    )
    explicit_solution = bool(state.get("solution_requested"))
    return has_emotion and has_intensity and (
        has_problem_signal or has_goal_signal or explicit_solution
    )
```

**B. New helper: `_infer_context_missing_reason(state, emotion, intensity) -> Optional[str]`**

Returns one of: `"vague_disclosure"`, `"missing_trigger"`, `"missing_user_goal"`, `"missing_safety_status"`, or `None`.

**C. New helper: `_goal_to_response_task(user_goal, immediate_regulation, solution_requested) -> Optional[str]`**

```python
def _goal_to_response_task(user_goal, immediate_regulation, solution_requested):
    if immediate_regulation:
        return "start_grounding_now"
    mapping = {
        "reach_out_to_friend":       "offer_low_pressure_message",
        "write_simple_message":      "offer_low_pressure_message",
        "know_where_to_start":       "give_tiny_first_step",
        "break_project_into_steps":  "give_tiny_first_step",
        "stop_overthinking_at_night":"offer_overthinking_tool",
    }
    if user_goal in mapping:
        return mapping[user_goal]
    if solution_requested:
        return "give_tiny_first_step"
    return None
```

**D. Consent override block** (runs early, before `_listen_only_mode` is enforced):

```python
immediate_regulation_request = is_immediate_regulation_request(current_message)
solution_requested = (
    is_solution_requested(current_message)
    or "solution_requested" in context_flags
    or state.get("solution_requested", False)
)
latest_user_need = (
    detect_user_goal(current_message, state)
    or state.get("latest_user_need")
)
exercises_reopened = False
_consent_was_blocked = (
    exercise_consent in ("denied_soft", "denied_hard")
    or solution_preference == "listen_only"
)
if _consent_was_blocked:
    if immediate_regulation_request or is_explicit_exercise_request(current_message):
        exercise_consent = "allowed"
        solution_preference = "exercise_requested"
        exercises_reopened = True
        _listen_only_mode = False
    elif solution_requested:
        exercise_consent = "unknown"
        solution_preference = "advice_allowed"
        _listen_only_mode = False
```

**E. `IMMEDIATE_REGULATION_REQUEST` early-exit routing block** (runs before chitchat gate and before main stage machine):

```python
if immediate_regulation_request and not crisis_detected:
    print("[NODE: PLANNER] IMMEDIATE_REGULATION_REQUEST — bypassing context gate and permission")
    return {
        "conversation_strategy": "suggest_technique",
        "conversation_stage": "INTERVENTION",
        "conversation_phase": "venting",
        "technique_readiness": 1.0,
        "needs_technique": True,
        "response_task": "start_grounding_now",
        "intent": intent,
        "crisis_detected": False,
        "session_message_count": user_msg_count,
        "gate_context_flags": merged_flags,
        "gate_emotional_register": gate_emotional_register,
        "gate_intensity_hint": float(intensity),
        "latest_referenced_entity": referenced_entity,
        "compact_analysis": compact_analysis,
        "solution_requested": True,
        "immediate_regulation_request": True,
        "exercises_reopened": exercises_reopened,
        "exercise_consent": "allowed",
        "solution_preference": "exercise_requested",
        "question_budget": 0,
        "question_count_since_disclosure": 0,
        "latest_user_need": latest_user_need or "calm_body_now",
        "context_missing_reason": None,
        **context_updates,
    }
```

**F. `SOLUTION_REQUESTED` routing block** (runs after IMMEDIATE_REGULATION_REQUEST, before general stage machine):

```python
if solution_requested and not immediate_regulation_request and not crisis_detected:
    context_enough = _context_is_enough(context_state, emotion, float(intensity))
    if context_enough:
        goal_task = _goal_to_response_task(latest_user_need, False, True)
        return {
            ...,
            "needs_technique": True,
            "conversation_stage": "INTERVENTION",
            "response_task": _final_response_task(
                "technique_request", "suggest_technique", True,
                goal_task or "offer_one_technique", exercise_consent
            ),
            "question_budget": 0,
            "solution_requested": True,
            "immediate_regulation_request": False,
            "latest_user_need": latest_user_need,
            "context_missing_reason": None,
            **context_updates,
        }
    else:
        missing_reason = _infer_context_missing_reason(context_state, emotion, float(intensity))
        return {
            ...,
            "needs_technique": False,
            "conversation_stage": "UNDERSTANDING",
            "response_task": "ask_one_missing_context_question",
            "question_budget": 1,
            "solution_requested": True,
            "immediate_regulation_request": False,
            "latest_user_need": latest_user_need,
            "context_missing_reason": missing_reason,
            **context_updates,
        }
```

**G. Question budget hard stop** (before final return paths):

```python
q_since = state.get("question_count_since_disclosure", 0)
if response_task in ("ask_next_context_question", "ask_one_missing_context_question"):
    q_since += 1
if q_since >= 2 and not context_enough and not crisis_detected and not immediate_regulation_request:
    needs_technique = True
    response_task = "give_tiny_first_step"
    question_budget = 0
    q_since = 0
```

**H. Add to all return paths:**
```python
"solution_requested": solution_requested,
"immediate_regulation_request": immediate_regulation_request,
"exercises_reopened": exercises_reopened,
"latest_user_need": latest_user_need,
"question_budget": question_budget,
"question_count_since_disclosure": q_since,
"context_missing_reason": context_missing_reason,
```

---

### Component 4: Technique Selector Node

#### [MODIFY] [technique_selector_node.py](file:///E:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/technique_selector_node.py)

- Read `latest_user_need`, `solution_requested`, `immediate_regulation_request`, `response_task` from state.

- Add `_GOAL_CATEGORY_BOOST` mapping:
  ```python
  _GOAL_CATEGORY_BOOST = {
      "calm_body_now":              ["breathing", "grounding"],
      "reach_out_to_friend":        ["behavioral_activation", "social_skills"],
      "write_simple_message":       ["behavioral_activation", "social_skills"],
      "know_where_to_start":        ["behavioral_activation", "cbt"],
      "break_project_into_steps":   ["behavioral_activation", "cbt"],
      "stop_overthinking_at_night": ["dbt", "mindfulness", "cbt"],
      "sleep_better":               ["mindfulness", "breathing"],
  }
  # Boost matching categories by +0.25 in scoring when latest_user_need is set
  ```

- When `immediate_regulation_request=True` or `response_task=="start_grounding_now"`:
  - Force shortlist to categories `["breathing", "grounding"]`
  - Skip LLM re-ranking, pick top-scored directly

---

### Component 5: Response Generator Hard Rules

#### [MODIFY] [optimized_response_generator.py](file:///E:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/optimized_response_generator.py)

Inject new context block into system prompt:

```
=== SOLUTION LIFECYCLE CONTEXT ===
SOLUTION_REQUESTED={solution_requested}
IMMEDIATE_REGULATION_REQUEST={immediate_regulation_request}
EXERCISES_REOPENED={exercises_reopened}
LATEST_USER_NEED={latest_user_need}
QUESTION_BUDGET={question_budget}
CONTEXT_MISSING_REASON={context_missing_reason}
MEDICAL_SAFETY_NEEDED={medical_safety_needed}
```

New hard rules 26–29:

**Rule 26 — Response ordering for SOLUTION_REQUESTED:**
```
26. When SOLUTION_REQUESTED=True:
    (1) One sentence of validation.
    (2) Direct helpful action or explanation.
    (3) One concrete next step or technique card.
    (4) One follow-up question ONLY if QUESTION_BUDGET=1.
    NEVER lead with a context-gathering question.
```

**Rule 27 — Enforce question budget:**
```
27. Obey QUESTION_BUDGET exactly.
    QUESTION_BUDGET=0: no questions at all — not even after the technique.
    QUESTION_BUDGET=1: one gentle question, at the end only.
    Never ask "What caused this?" / "How long has this been?" / "Where are you right now?"
    when SOLUTION_REQUESTED=True or IMMEDIATE_REGULATION_REQUEST=True.
```

**Rule 28 — IMMEDIATE_REGULATION_REQUEST:**
```
28. When IMMEDIATE_REGULATION_REQUEST=True:
    (1) Begin a grounding or breathing technique immediately. Do NOT ask for permission first.
    (2) Give the first step in this same message.
    (3) If MEDICAL_SAFETY_NEEDED=True, add one short safety line:
        "If this chest tightness feels severe or comes with strong chest pain,
         trouble breathing, or fainting, please seek urgent medical help."
    (4) Zero questions.
    NEVER say "Would you like me to share a technique?" here.
```

**Rule 29 — No repeated context questions:**
```
29. Hard stop on repeat questions:
    - Never ask "What caused this?" if you already asked this session.
    - Never ask another context question after the user said:
      "what should I do", "tell me where to start", "help me calm down",
      "give me your approach", "yes go for it", "just help me".
    - If EXERCISES_REOPENED=True, start with:
      "I know you weren't feeling exercises before — since you're asking now,
       let's try something different."
      Then proceed. Do not re-ask about exercises.
    - If CONTEXT_MISSING_REASON is set, ask exactly one question targeting that gap only.
      missing_trigger → "What's been going on for you lately?"
      missing_user_goal → "Is it more like you want to calm your body, understand what's happening, or take a practical step?"
      vague_disclosure → "Is this feeling more in your chest, your thoughts, or your emotions right now?"
      missing_safety_status → "Are you safe right now?"
```

---

### Component 6: Prompt Constants

#### [MODIFY] [prompts.py](file:///E:/FYP/mental_health_wellness/src/mental_health_wellness/agent/prompts.py)

Add to coach and trainer role guidelines:
- "When the user explicitly asks for help, validate briefly and deliver a direct first helpful action. Do not gather more context first."
- "For body symptoms like chest tightness, shaking, or panic, begin a regulation technique immediately."
- "If the user previously said they don't want exercises but is now asking for one, acknowledge the change warmly then proceed."

---

### Component 7: New Test Files

| File | What it covers |
|---|---|
| `tests/test_solution_requested_routing.py` | SOLUTION_REQUESTED → INTERVENTION, question_budget=0, no context question before help |
| `tests/test_immediate_regulation_request.py` | Body distress + urgency → start_grounding_now, consent=allowed, question_budget=0, medical line |
| `tests/test_question_budget.py` | question_count_since_disclosure >= 2 → hard stop, forced first helpful step |
| `tests/test_consent_override.py` | denied_hard + exercise request → exercises_reopened=True; denied_hard + "what should I do?" → advice_allowed |
| `tests/test_latest_user_goal_technique_selection.py` | latest_user_need="reach_out_to_friend" → behavioral_activation / social_skills category boost |

---

## Manual Test Scenarios

| User message | Expected |
|---|---|
| "My chest feels tight, hands shaky, help me calm down right now" | immediate_regulation_request=True, grounding starts immediately, 0 questions, medical line if needed |
| "I feel lonely. What should I do?" | solution_requested=True, context_is_enough (sub-emotion present), small connection step, max 1 question |
| "I need help saying it to my friend simply" | latest_user_need=write_simple_message, Social Skills / Micro-Connection technique |
| "I don't know where to start" | latest_user_need=know_where_to_start, Graded Task / Tiny First Step |
| "I keep overthinking at night" | latest_user_need=stop_overthinking_at_night, Worry Time / Thought Defusion |
| "I don't want exercises" then "give me something to try" | exercises_reopened=True, warm acknowledgment, then technique |
| "How would you help me?" | Support roadmap + begin one small step, 0 questions first |
| "I don't know what's wrong" | Validate + 1 gentle choice question |

---

## Verification Plan

```bash
pytest tests/test_acceptance_preserves_context.py
pytest tests/test_context_complete_technique_gate.py
pytest tests/test_short_acknowledgement_context.py
pytest tests/test_solution_requested_routing.py
pytest tests/test_immediate_regulation_request.py
pytest tests/test_question_budget.py
pytest tests/test_consent_override.py
pytest tests/test_latest_user_goal_technique_selection.py
```
