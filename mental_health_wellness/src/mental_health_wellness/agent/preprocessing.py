"""
Message Pre-Processing Module
Detects special message types BEFORE LLM to prevent incorrect tool calling.

This module provides reliable pattern matching for:
- Greetings (prevent crisis_check false positives)
- Exercise/technique requests (ensure recommend_technique is called)
- Cognitive distortions (ensure analyze_mood + cbt_reframe)
- Casual conversations (prevent unnecessary tool calls)
"""

import re
from typing import Dict, List, Tuple, Optional


class MessagePreprocessor:
    """
    Pre-processes user messages to detect intent patterns.
    Returns classification that guides tool selection.
    """
    
    def __init__(self):
        """Initialize pattern dictionaries."""
        # Greeting patterns - should NOT trigger crisis_check
        # NOTE: These only match SHORT greetings. The classify_message method
        # also checks that the message has no emotional content before classifying
        # as a pure greeting.
        self.greeting_patterns = [
            r"^(hi|hello|hey|hey\s+there)\b",
            r"^(hi|hello|hey)\s+sentimind\b",  # "Hello SentiMind", "Hey SentiMind"
            r"^(good\s+(morning|afternoon|evening))",
            r"^how\s+(are\s+you|are\s+you\s+doing|'s\s+it\s+going)",
            r"^what's\s+up",
            r"^sup\b",
            r"^(thanks|thank\s+you)",
            r"^(bye|goodbye|see\s+you)",
            r"^(okay|ok|cool|nice|great)\b",
        ]
        
        # Emotion keywords that override a greeting classification
        # If ANY of these appear anywhere in the message, it's NOT a pure greeting
        self.emotion_override_keywords = [
            r"\b(sad|anxious|anxiety|angry|depressed|stressed|overwhelmed|lonely|scared|worried|frustrated|hopeless|miserable|upset|hurt|down|low|empty|afraid|terrified|nervous|panic|exhausted)\b",
            r"\b(feeling|feel|felt)\s+(so|really|very|extremely|quite|pretty)\b",
            r"\b(can't\s+sleep|can't\s+cope|can't\s+handle|can't\s+take)\b",
            r"\b(kill|hurt|harm|cut|end\s+my)\b",
        ]
        
        # Exercise/technique request patterns - MUST trigger mindfulness_exercise
        self.exercise_patterns = [
            r"(teach|show|help|guide|walk|lead).{0,20}(breathing|exercise|meditation|mindfulness|relaxation|grounding|technique)",
            r"(breathing|meditation|mindfulness|relaxation|grounding|guided).{0,20}(exercise|technique|practice)",
            r"(exercise|meditation|breathing|grounding|technique|practice).{0,20}(help|guide|teach|show)",
            r"\b(breathing\s+exercise|guided\s+meditation|grounding\s+technique|relaxation\s+exercise)\b",
            r"can\s+you\s+(teach|help|do|try|start).{0,20}(breathing|meditation|exercise)",
            r"let's\s+(try|do|practice).{0,20}(breathing|meditation|exercise|technique)",
            r"(help\s+me|teach\s+me|show\s+me).{0,20}(breathe|meditate|relax|calm\s+down)",
            r"walk\s+me\s+through.{0,20}(breathing|meditation|exercise)",
        ]
        
        # Cognitive distortion patterns - MUST trigger analyze_mood + cbt_reframe
        # IMPORTANT: Patterns require SELF-REFERENTIAL or NEGATIVE context
        # to avoid false positives on innocent messages like "I always exercise"
        self.cognitive_distortion_patterns = [
            # Overgeneralization with negative self-reference
            # "I always mess up" ✓  but NOT "I always go for walks" ✗
            r"(i\s+(always|never|constantly)\s+(mess|fail|screw|ruin|forget|lose|get\s+it\s+wrong))",
            # Catch "I feel like I fail at everything"
            r"(i\s+feel\s+(like|that)\s+i\s+(fail|am\s+a\s+failure|can't\s+do\s+anything))",
            r"(nothing|no\s+one|nobody)\s+(ever|always|will)\s+(work|help|care|change|love|understand)",
            r"(every\s+time|all\s+the\s+time).{0,30}(wrong|bad|fail|mess|worse|ruin)",
            # Catastrophizing (strong words only)
            r"\b(worst\s+thing|disaster|my\s+life\s+is\s+ruined|everything\s+is\s+(ruined|over|falling\s+apart))\b",
            r"\b(i'll\s+never\s+(recover|get\s+better|succeed|be\s+happy|find))\b",
            # Self-blame / Self-criticism (kept — already self-referential)
            r"(i'm\s+(a|such\s+a)\s+(failure|stupid|worthless|broken|incompetent|useless))",
            r"(it's\s+all\s+my\s+fault|i\s+messed\s+up|i\s+ruined\s+(everything|it|this))",
            # Black-and-white thinking (tightened)
            r"(i'm\s+either).{0,20}(perfect|failure|good|bad|success|nothing)",
            # Mind reading (kept — already contextual)
            r"(they\s+(think|know|believe)\s+(i'm|that\s+i'm))",
            r"(everyone\s+(thinks|knows|hates|judges)\s+(i'm|me|that))",
        ]
        
        # Casual conversation patterns - do NOT call analyze_mood
        # IMPORTANT: These patterns are ONLY applied if the message does NOT
        # contain emotion keywords (checked in classify_message method)
        self.casual_patterns = [
            r"^(can\s+you|could\s+you|would\s+you).{0,30}(help|tell|explain|clarify|say|describe)\b",
            r"^what.{0,30}(can\s+you|do\s+you|are\s+you)",
            r"^(how|why).{0,30}(does|do|is|are|work|help)",
            r"^tell\s+me\s+about",
            r"^i\s+(want|need).{0,20}(to\s+)?talk",
            r"^i\s+(want|need).{0,20}(help|support|assistance)",
            # Removed overly broad question pattern that matched emotional questions
            # like "Should I be worried about my panic attacks?"
        ]
        
        # Crisis/self-harm markers - ONLY these trigger crisis_check
        self.crisis_markers = [
            # Self-harm / Suicide intent
            r"\b(kill|hurt|harm|cut|injure|wound)(ing)?\s+(myself|my\s+self)\b",
            r"\b(suicide|suicidal|end\s+(my\s+)?life|want\s+to\s+die|better\s+off\s+dead)\b",
            r"\b(no\s+point|no\s+reason|can't\s+go\s+on|can't\s+take\s+it|nothing\s+matters)\b",
            # Passive SI - "don't want to be here", "don't feel like going on"
            r"(don't|do\s+not).{0,20}(want\s+to\s+be\s+here|feel\s+like\s+going\s+on|want\s+to\s+exist)",
            r"\b(burden|everyone\s+would\s+be|better\s+without|world\s+better\s+without)\b",
            # Severe self-harm behavior descriptions
            r"\b(overdose|cutting|self\s+harm|self\s+injur|suffocate|drown|jump)\b",
        ]
        
        # Anger/conflict patterns - NOT crisis
        self.anger_patterns = [
            r"\b(angry|furious|rage|mad|livid|pissed|upset|frustrated)\b",
            r"\b(hate|despise|can't\s+stand|can't\s+stand)\b",
            r"\b(conflict|fight|argument|dispute|disagree|blamed|blamed)\b",
        ]
        
        # Emotional distress patterns - triggers analyze_mood + get_techniques
        # These detect general emotional suffering that isn't anger-specific
        self.emotional_distress_patterns = [
            r"\b(sad|depressed|anxious|anxiety|stressed|overwhelmed|lonely|scared|worried|hopeless|miserable|empty|exhausted|down|low)\b",
            r"\b(can't\s+(sleep|cope|handle|stop\s+crying|breathe))\b",
            r"\b(panic\s+attack|anxiety\s+attack|breaking\s+down|falling\s+apart)\b",
            r"\b(feel|feeling)\s+(so|really|very|extremely)?\s*(bad|terrible|awful|horrible|worthless|numb|down|low)\b",
        ]
    
    def classify_message(self, message: str) -> Dict[str, any]:
        """
        Classify a message and return metadata for tool selection.
        
        Returns:
        {
            "is_greeting": bool,
            "is_exercise_request": bool,
            "is_cognitive_distortion": bool,
            "is_casual_conversation": bool,
            "has_crisis_markers": bool,
            "is_anger_not_crisis": bool,
            "detected_patterns": List[str],
            "suggested_tools": List[str],
            "tools_to_skip": List[str],
        }
        """
        msg_lower = message.lower().strip()
        results = {
            "is_greeting": False,
            "is_exercise_request": False,
            "is_cognitive_distortion": False,
            "is_casual_conversation": False,
            "has_crisis_markers": False,
            "is_anger_not_crisis": False,
            "is_emotional_distress": False,
            "detected_patterns": [],
            "suggested_tools": [],
            "tools_to_skip": [],
        }
        
        # ============================================
        # STEP 1: Check for ACTUAL crisis markers FIRST (highest safety priority)
        # ============================================
        for pattern in self.crisis_markers:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                results["has_crisis_markers"] = True
                results["detected_patterns"].append("crisis_marker")
                results["suggested_tools"].append("handle_crisis")
                break
        
        # If crisis markers found, do NOT skip handle_crisis under any circumstances
        # Return early — crisis takes absolute priority
        if results["has_crisis_markers"]:
            return results
        
        # ============================================
        # STEP 2: Check for greeting (but only if message is PURELY a greeting)
        # ============================================
        # "Hi!" → greeting ✓
        # "Hi, I'm feeling really down" → NOT a greeting (has emotional content)
        has_emotion_content = any(
            re.search(pattern, msg_lower, re.IGNORECASE)
            for pattern in self.emotion_override_keywords
        )
        
        if not has_emotion_content:
            for pattern in self.greeting_patterns:
                if re.search(pattern, msg_lower, re.IGNORECASE):
                    # Additional check: short messages are more likely pure greetings
                    # "Hello!" (6 chars) → greeting
                    # "Hello, I've been struggling with anxiety lately" → NOT greeting
                    words = msg_lower.split()
                    if len(words) <= 8:
                        results["is_greeting"] = True
                        results["detected_patterns"].append("greeting")
                        results["tools_to_skip"] = ["handle_crisis", "analyze_mood", "recommend_technique"]
                        return results
                    break  # Matched greeting pattern but too long — fall through
        
        # ============================================
        # STEP 3: Check for exercise request (MUST trigger mindfulness_exercise)
        # ============================================
        for pattern in self.exercise_patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                results["is_exercise_request"] = True
                results["detected_patterns"].append("exercise_request")
                results["suggested_tools"].append("recommend_technique")
                results["tools_to_skip"].append("handle_crisis")
                break
        
        # ============================================
        # STEP 4: Check for casual conversation
        # Only if NO emotion keywords are present in the message
        # ============================================
        if not has_emotion_content and not results["is_exercise_request"]:
            for pattern in self.casual_patterns:
                if re.search(pattern, msg_lower, re.IGNORECASE):
                    results["is_casual_conversation"] = True
                    results["detected_patterns"].append("casual_conversation")
                    results["tools_to_skip"] = ["handle_crisis"]
                    break
        
        # ============================================
        # STEP 5: Check for cognitive distortion
        # ============================================
        cognitive_matches = 0
        for pattern in self.cognitive_distortion_patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                cognitive_matches += 1
        
        if cognitive_matches >= 1:
            results["is_cognitive_distortion"] = True
            results["detected_patterns"].append("cognitive_distortion")
            results["suggested_tools"].extend(["analyze_mood", "recommend_technique"])
            results["tools_to_skip"].append("handle_crisis")
        
        # ============================================
        # STEP 6: Check for anger/conflict (NOT crisis)
        # ============================================
        for pattern in self.anger_patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                results["is_anger_not_crisis"] = True
                results["detected_patterns"].append("anger_expression")
                if "analyze_mood" not in results["suggested_tools"]:
                    results["suggested_tools"].append("analyze_mood")
                if "recommend_technique" not in results["suggested_tools"]:
                    results["suggested_tools"].append("recommend_technique")
                results["tools_to_skip"].append("handle_crisis")
                break
        
        # ============================================
        # STEP 7: Check for emotional distress
        # CAN co-exist with anger or cognitive distortion
        # ============================================
        for pattern in self.emotional_distress_patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                results["is_emotional_distress"] = True
                results["detected_patterns"].append("emotional_distress")
                if "analyze_mood" not in results["suggested_tools"]:
                    results["suggested_tools"].append("analyze_mood")
                if "recommend_technique" not in results["suggested_tools"]:
                    results["suggested_tools"].append("recommend_technique")
                results["tools_to_skip"].append("crisis_check")
                break
        
        # Deduplicate tools_to_skip
        results["tools_to_skip"] = list(set(results["tools_to_skip"]))
        
        return results


def get_message_classification(message: str) -> Dict[str, any]:
    """
    Convenience function to classify a message.
    
    Usage:
    ```
    classification = get_message_classification(user_message)
    if classification["is_greeting"]:
        # Skip all analysis
        pass
    elif classification["is_exercise_request"]:
        # Force recommend_technique
        pass
    ```
    """
    preprocessor = MessagePreprocessor()
    return preprocessor.classify_message(message)


# Emotion mapping normalization
EMOTION_NORMALIZATION_MAP = {
    # Normalize similar emotions
    "fear": "anxiety",           # Fear and anxiety are closely related
    "worry": "anxiety",
    "nervous": "anxiety",
    "dread": "anxiety",
    "panic": "anxiety",
    
    # Sadness related
    "depressed": "sadness",
    "down": "sadness",
    "blue": "sadness",
    "melancholy": "sadness",
    
    # Anger related
    "rage": "anger",
    "furious": "anger",
    "livid": "anger",
    "resentment": "anger",
    
    # Keep as-is
    "anxiety": "anxiety",
    "sadness": "sadness",
    "anger": "anger",
    "joy": "joy",
    "happiness": "joy",
    "neutral": "neutral",
}


def normalize_emotion(emotion: str) -> str:
    """
    Normalize emotion terms to standard categories.
    Helps with consistency across different emotion detectors.
    """
    emotion_lower = emotion.lower().strip()
    return EMOTION_NORMALIZATION_MAP.get(emotion_lower, emotion_lower)
