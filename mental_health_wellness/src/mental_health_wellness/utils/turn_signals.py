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
