"""Small deterministic signals for short conversational turns.

These helpers intentionally do not decide the whole route. They only separate
surface-positive language ("thanks", "okay") from actual consent or outcome
feedback, then callers combine that signal with the active conversation state.
"""

from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def plain_text(text: str) -> str:
    return re.sub(r"[^\w\s]", " ", normalize_text(text)).strip()


def words(text: str) -> list[str]:
    return re.findall(r"\b[\w']+\b", normalize_text(text))


def is_short_turn(text: str, max_words: int = 8) -> bool:
    token_count = len(words(text))
    return 0 < token_count <= max_words


_GRATITUDE_PHRASES = {
    "thanks",
    "thank you",
    "thank u",
    "thx",
    "ty",
    "appreciate it",
    "thanks a lot",
    "thank you so much",
    "thanks for it",
    "thank you for it",
}

_AFFIRMATION_PHRASES = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "ok",
    "okay",
    "sure",
    "alright",
    "sounds good",
    "go ahead",
    "go for it",
    "please do",
    "yes please",
    "yes plz",
    "yes pls",
    "yes sure",
    "sure yes",
    "okay sure",
    "ok sure",
    "lets do it",
    "let us do it",
    "lets try",
    "let us try",
    "share it",
    "please share",
    "please share it",
    "show me",
    "guide me",
    "walk me through",
}

_NEGATIVE_FEEDBACK_PHRASES = {
    "didn't help",
    "did not help",
    "doesn't help",
    "does not help",
    "not helpful",
    "not useful",
    "not working",
    "doesn't work",
    "does not work",
    "didn't work",
    "did not work",
    "not for me",
    "doesn't suit me",
    "does not suit me",
    "didn't land",
    "did not land",
    "made it worse",
}

_POSITIVE_OUTCOME_PHRASES = {
    "helped",
    "helping",
    "worked",
    "working",
    "made a difference",
    "feel better",
    "feeling better",
    "felt better",
    "calmer",
    "more calm",
    "less anxious",
    "less stressed",
    "relieved",
    "relief",
    "useful",
    "helpful",
}

_EXERCISE_DENIAL_PHRASES = {
    "no exercises",
    "no exercise",
    "no techniques",
    "no technique",
    "dont want exercises",
    "dont want exercise",
    "dont want techniques",
    "dont want technique",
    "do not want exercises",
    "do not want exercise",
    "do not want techniques",
    "do not want technique",
    "stop suggesting exercises",
    "stop suggesting techniques",
    "just listen",
    "just want to vent",
    "just want to talk",
}

_EXERCISE_BROWSE_PHRASES = {
    "list exercises",
    "list techniques",
    "show me all exercises",
    "show me all techniques",
    "show me exercises",
    "show me techniques",
    "what exercises do you have",
    "what techniques do you have",
    "what exercises are available",
    "what techniques are available",
    "browse exercises",
    "browse techniques",
    "all exercises",
    "all techniques",
}


def has_gratitude(text: str) -> bool:
    clean = plain_text(text)
    return any(phrase in clean for phrase in _GRATITUDE_PHRASES)


def is_gratitude_only(text: str) -> bool:
    clean = plain_text(text)
    if not clean:
        return False
    if clean in _GRATITUDE_PHRASES:
        return True
    removable = set()
    for phrase in _GRATITUDE_PHRASES | {"ok", "okay", "yes", "yeah", "yep", "alright", "sure"}:
        removable.update(phrase.split())
    remaining = [token for token in clean.split() if token not in removable]
    return not remaining and has_gratitude(text)


def is_affirmation(text: str) -> bool:
    clean = plain_text(text)
    if not clean:
        return False
    if clean in _AFFIRMATION_PHRASES:
        return True
    if is_short_turn(clean, 6):
        return any(re.search(rf"\b{re.escape(phrase)}\b", clean) for phrase in _AFFIRMATION_PHRASES)
    return False


def is_bare_affirmation(text: str) -> bool:
    return is_affirmation(text) and not has_gratitude(text) and not has_positive_outcome_signal(text)


def is_technique_acceptance_reply(text: str) -> bool:
    """Affirmation strong enough to accept an offered exercise.

    "ok thanks" is intentionally excluded. It is an acknowledgement unless the
    user also says yes/sure/try/share/guide/go ahead.
    """
    clean = plain_text(text)
    if not clean or is_no_thanks(clean):
        return False
    strong_tokens = {"yes", "yeah", "yep", "yup", "sure"}
    if strong_tokens & set(clean.split()):
        return True
    strong_phrases = (
        "go ahead",
        "go for it",
        "please do",
        "please share",
        "share it",
        "show me",
        "guide me",
        "walk me through",
        "lets try",
        "let us try",
        "lets do it",
        "let us do it",
    )
    return any(phrase in clean for phrase in strong_phrases)


def has_positive_outcome_signal(text: str) -> bool:
    clean = plain_text(text)
    if not clean:
        return False
    return any(phrase in clean for phrase in _POSITIVE_OUTCOME_PHRASES)


def has_negative_feedback_signal(text: str) -> bool:
    clean = plain_text(text)
    if not clean:
        return False
    return any(phrase in clean for phrase in _NEGATIVE_FEEDBACK_PHRASES)


def is_explicit_exercise_request(text: str) -> bool:
    """True when the user wants a practical exercise now, not just more talk.

    This deliberately excludes global exercise refusals, negative feedback
    about a previous exercise, and broad browse/list requests.
    """
    clean = plain_text(text)
    if not clean:
        return False
    if any(phrase in clean for phrase in _EXERCISE_DENIAL_PHRASES):
        return False
    if has_negative_feedback_signal(clean):
        return False
    if any(phrase in clean for phrase in _EXERCISE_BROWSE_PHRASES):
        return False

    action_request = re.search(
        r"\b(give|share|suggest|recommend|teach|start|begin|do|try|practice|guide|walk)\b"
        r".{0,50}\b(exercise|exercises|technique|techniques|breathing|grounding|meditation|mindfulness|relaxation)\b",
        clean,
    )
    if action_request:
        return True

    reverse_action_request = re.search(
        r"\b(exercise|exercises|technique|techniques|breathing|grounding|meditation|mindfulness|relaxation)\b"
        r".{0,50}\b(now|please|plz|pls|together)\b",
        clean,
    )
    if reverse_action_request:
        return True

    try_something_request = re.search(
        r"\b(want|wanna|would like|like|need|ready)\b.{0,35}\btry something\b",
        clean,
    )
    suggestion_request = any(
        phrase in clean
        for phrase in (
            "what do you suggest",
            "what do you recommend",
            "suggest something",
            "recommend something",
            "something that might help",
            "something practical",
            "something i can try",
            "something to try",
        )
    )
    if try_something_request and suggestion_request:
        return True

    if any(
        phrase in clean
        for phrase in (
            "give me something to try",
            "please give me something to try",
            "can we try something",
            "lets try something",
            "let us try something",
        )
    ):
        return True

    return any(
        phrase in clean
        for phrase in (
            "walk me through it",
            "guide me through it",
            "lets do it",
            "let us do it",
            "get on with it",
        )
    ) and any(
        word in clean
        for word in (
            "exercise",
            "exercises",
            "technique",
            "techniques",
            "breathing",
            "grounding",
            "meditation",
            "mindfulness",
            "relaxation",
        )
    )


def is_no_thanks(text: str) -> bool:
    clean = plain_text(text)
    return clean in {"no thanks", "no thank you", "nah thanks", "no thx", "no ty"}


def is_polite_acknowledgement(text: str) -> bool:
    """True for short acknowledgement/gratitude without outcome feedback."""
    if has_positive_outcome_signal(text) or has_negative_feedback_signal(text):
        return False
    clean = plain_text(text)
    if clean in {"ok", "okay", "alright", "got it", "i see", "makes sense"}:
        return True
    return is_gratitude_only(text)


def assistant_offered_technique(text: str, expected_answer_type: str | None = None) -> bool:
    """Detect whether the previous assistant turn asked for exercise consent."""
    if expected_answer_type == "technique_acceptance":
        return True
    lower = normalize_text(text)
    if not lower:
        return False
    offer_markers = (
        "would you like me to share",
        "would you like to try",
        "would you be open to",
        "want to give it a try",
        "want to try it",
        "shall we try",
        "try it together",
        "give it a try",
        "i can share a technique",
        "i can share something",
        "i have something that might help",
        "i have a technique",
        "would you like to do",
        "are you open to trying",
    )
    return any(marker in lower for marker in offer_markers)


def assistant_likely_gave_steps(text: str) -> bool:
    """Detect whether the prior assistant likely already delivered an exercise."""
    lower = normalize_text(text)
    if not lower:
        return False
    step_markers = (
        "step 1",
        "first step",
        "let's begin",
        "lets begin",
        "start by",
        "write down",
        "breathe in",
        "inhale",
        "exhale",
        "set a timer",
        "try this now",
        "we'll do",
        "we will do",
    )
    return any(marker in lower for marker in step_markers)


def last_ai_from_recent_context(recent_context: str) -> str:
    """Best-effort extraction from graph recent_context: 'AI: ... | HUMAN: ...'."""
    if not recent_context:
        return ""
    parts = [part.strip() for part in recent_context.split("|") if part.strip()]
    for part in reversed(parts):
        if part.upper().startswith(("AI:", "AIMESSAGE:", "ASSISTANT:", "SYSTEM:")):
            return part.split(":", 1)[1].strip() if ":" in part else part
    return ""


# =============================================================================
# v13.0: DYNAMIC CONTEXT GATHERING — NEW TURN SIGNAL FUNCTIONS
# =============================================================================

_BODY_DISTRESS_SIGNALS = (
    "chest tight", "chest tightness", "chest pain",
    "can't breathe", "cant breathe", "hard to breathe", "trouble breathing",
    "heart beating fast", "heart racing", "heart pounding", "heart hammering",
    "hands shaking", "body shaking", "trembling", "shaking",
    "panic", "panicking", "having a panic",
    "dizzy", "dizziness", "faint", "fainting", "lightheaded",
    "something bad is going to happen", "feel like i'm dying", "feel like im dying",
    "help me calm", "calm me down", "calm my body", "calm my breathing",
    "help right now", "need help now", "i need to calm",
    "cant calm down", "can't calm down",
    "ground me", "ground myself",
)

_REGULATION_ACTION_SIGNALS = (
    "right now", "right away", "immediately",
    "please help", "please", "help me",
    "now", "asap", "urgent",
    "i can't", "i cant",
    "calm down", "calm me", "calm my",
    "breathe", "breathing",
    "ground", "grounding",
)


def is_immediate_regulation_request(text: str) -> bool:
    """True when the user has acute body distress AND urgency/action signal.

    These users need help immediately — the agent must start a regulation
    technique in the same turn with no permission gate and no context questions.
    """
    clean = normalize_text(text)
    if not clean:
        return False
    has_body_distress = any(sig in clean for sig in _BODY_DISTRESS_SIGNALS)
    if not has_body_distress:
        return False
    has_action = any(sig in clean for sig in _REGULATION_ACTION_SIGNALS)
    return has_action


_SOLUTION_REQUEST_PHRASES = (
    "what should i do",
    "what do i do",
    "what can i do",
    "how can you help",
    "how would you help",
    "how can therapy help",
    "give me a solution",
    "give me a plan",
    "give me a technique",
    "give me an exercise",
    "give me something",
    "can you give me therapy",
    "give me therapy",
    "fix this",
    "help me fix",
    "i need something right now",
    "tell me what to do",
    "any advice",
    "need advice",
    "i need help",
    "help me please",
    "please help me",
    "what should i try",
    "what exercise should i do",
    "i want to try it",
    "give me something to try",
    "suggest something",
    "can you suggest",
    "where do i start",
    "i dont know where to start",
    "i don't know where to start",
    "i need a plan",
    "help me cope",
    "how do i cope",
    "what can help me",
    "what will help",
    "help me with this",
    "can you help me with this",
)


def is_solution_requested(text: str) -> bool:
    """True when the user explicitly asks for help, therapy, a technique, a plan,
    or guidance — not just venting or giving context.

    Excludes bare gratitude, affirmations, and short context answers.
    """
    clean = normalize_text(text)
    if not clean:
        return False
    # Exclude pure gratitude/acknowledgement
    if is_gratitude_only(clean):
        return False
    if is_polite_acknowledgement(clean):
        return False
    return any(phrase in clean for phrase in _SOLUTION_REQUEST_PHRASES)


_GOAL_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    # calm_body_now — acute body distress
    (
        ("chest tight", "can't breathe", "cant breathe", "heart racing", "heart pounding",
         "hands shaking", "trembling", "panic", "calm my body", "calm down right now",
         "calm my breathing", "help me breathe", "ground me"),
        "calm_body_now",
    ),
    # sleep_better
    (
        ("can't sleep", "cant sleep", "insomnia", "sleep better", "sleep problem",
         "wake up at night", "lying awake", "mind won't stop at night"),
        "sleep_better",
    ),
    # stop_overthinking_at_night
    (
        ("overthinking at night", "thoughts at night", "mind racing at night",
         "can't stop thinking at night", "cant stop thinking at night",
         "lying awake thinking", "ruminating at night"),
        "stop_overthinking_at_night",
    ),
    # write_simple_message
    (
        ("help me write", "write a message", "what to say", "how to say it",
         "write to my friend", "text my friend", "message my friend",
         "say it simply", "help me word"),
        "write_simple_message",
    ),
    # reach_out_to_friend
    (
        ("reach out", "talk to someone", "talk to a friend", "connect with someone",
         "message someone", "text someone", "contact my friend",
         "how do i talk to people", "how to talk to people"),
        "reach_out_to_friend",
    ),
    # break_project_into_steps
    (
        ("break it down", "break down the project", "step by step", "where to start with",
         "how to start my project", "project plan", "divide the work",
         "fyp", "capstone", "dissertation"),
        "break_project_into_steps",
    ),
    # know_where_to_start
    (
        ("where to start", "don't know where to start", "dont know where to start",
         "don't know how to begin", "dont know how to begin",
         "how to begin", "how do i begin", "what to do first",
         "don't know what to do", "dont know what to do",
         "i'm overwhelmed", "im overwhelmed", "too much"),
        "know_where_to_start",
    ),
    # understand_my_emotion
    (
        ("understand my feelings", "understand what i feel", "why do i feel",
         "why am i feeling", "what is this feeling", "make sense of",
         "understand my emotions", "what does this mean"),
        "understand_my_emotion",
    ),
]


def detect_user_goal(text: str, state: dict | None = None) -> "str | None":
    """Map the user's message to a canonical goal string.

    Returns one of:
        "calm_body_now", "sleep_better", "stop_overthinking_at_night",
        "write_simple_message", "reach_out_to_friend", "break_project_into_steps",
        "know_where_to_start", "understand_my_emotion"
    or None if goal is unclear.
    """
    clean = normalize_text(text)
    if not clean:
        return None
    for patterns, goal in _GOAL_PATTERNS:
        if any(p in clean for p in patterns):
            return goal
    return None


_MEDICAL_WARNING_SIGNALS = (
    "chest pain",
    "severe chest",
    "chest hurts",
    "chest is hurting",
    "fainting",
    "about to faint",
    "going to faint",
    "losing consciousness",
    "cant breathe at all",
    "can't breathe at all",
    "cant breathe properly",
    "can't breathe properly",
    "severe dizziness",
    "very dizzy",
    "extremely dizzy",
    "heart attack",
)


def has_medical_warning_signal(text: str) -> bool:
    """True when the message contains severe body signals that warrant a medical safety line."""
    clean = normalize_text(text)
    if not clean:
        return False
    return any(sig in clean for sig in _MEDICAL_WARNING_SIGNALS)
