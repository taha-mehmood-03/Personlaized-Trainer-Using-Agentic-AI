"""
Mood Analysis Tools - Emotion detection and analysis
"""

from langchain_core.tools import tool

# ============================================
# LOCAL ML MODEL DISABLED
# ============================================

_emotion_pipeline = None

# def _get_emotion_pipeline():
#     """Lazy load emotion model. Raises if model cannot be loaded."""
#     global _emotion_pipeline
#     if _emotion_pipeline is None:
#         from transformers import pipeline
#         print("[TOOLS] 🔄 Loading emotion model (SamLowe/roberta-base-go_emotions)...")
#         _emotion_pipeline = pipeline(
#             "text-classification",
#             model="SamLowe/roberta-base-go_emotions",
#             device=-1
#         )
#         print("[TOOLS] ✅ Emotion model loaded")
#     return _emotion_pipeline

# def preload_emotion_model():
#     """Eagerly preload emotion model on startup."""
#     _get_emotion_pipeline()


@tool
def analyze_mood(message: str) -> dict:
    """
    Analyze the emotional state of a message.
    Use this tool when the user shares their feelings or seems emotional.
    
    Args:
        message: The user's message to analyze
        
    Returns:
        Dictionary with emotion, sentiment, intensity, and confidence
    """
    try:
        if not message or not isinstance(message, str):
            print("[MOOD_TOOLS] ⚠️ Invalid input - returning neutral")
            return {
                "emotion": "neutral",
                "sentiment": "neutral",
                "intensity": 0.5,
                "confidence": 0.0
            }
        
        # ── FIX 5: Emoji pre-processing ─────────────────────────
        # Convert common emotion emojis to text so DistilBERT can
        # interpret them meaningfully instead of returning neutral.
        EMOJI_EMOTION_MAP = [
            # Sadness / crying
            ("😭", "feeling sad and crying "),
            ("😢", "feeling sad and tearful "),
            ("😿", "feeling sad and crying "),
            ("😔", "feeling sad and disappointed "),
            ("💔", "feeling heartbroken and sad "),
            ("🥺", "feeling sad and pleading "),
            # Anger
            ("😡", "feeling very angry and frustrated "),
            ("🤬", "feeling furious and outraged "),
            ("😤", "feeling annoyed and frustrated "),
            # Fear / Anxiety
            ("😰", "feeling scared and anxious "),
            ("😨", "feeling frightened and anxious "),
            ("😱", "feeling terrified and panicked "),
            ("😟", "feeling worried and uneasy "),
            ("😣", "feeling overwhelmed and distressed "),
            # Joy / Positive
            ("😊", "feeling happy and content "),
            ("😁", "feeling joyful and excited "),
            ("🎉", "feeling celebratory and happy "),
            ("😄", "feeling joyful and pleased "),
            ("❤️", "feeling loved and happy "),
        ]
        
        processed_message = message
        emoji_text_prepend = ""
        for emoji_char, text_replacement in EMOJI_EMOTION_MAP:
            if emoji_char in message:
                emoji_text_prepend += text_replacement
        
        # If the message is ONLY emojis (no real words), prepend emotion text
        has_real_words = any(c.isalpha() for c in message)
        if emoji_text_prepend and not has_real_words:
            processed_message = emoji_text_prepend.strip()
            print(f"[MOOD_TOOLS] 🎭 Emoji→text: '{message}' → '{processed_message}'")
        elif emoji_text_prepend:
            # Mixed message — prepend hint to help the model
            processed_message = emoji_text_prepend.strip() + " " + message
        # ────────────────────────────────────────────────────────
        
        # ── LLM Emotion Classification (replaces local RoBERTa) ───────────
        from src.mental_health_wellness.llm.groq_llm import get_llm_manager
        import json
        import re
        
        manager = get_llm_manager()
        # Use the fast model (Haiku) for 8b instruct replacement
        llm = manager.get_llm(model=manager.model_fast).bind(max_tokens=64, temperature=0.0)
        
        prompt = f"""You are an emotion classification AI. Analyze the primary emotion in the user message.
Choose from exactly one of these labels: admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, neutral.

Respond ONLY with valid JSON:
{{"label": "emotion_name", "score": float_between_0_and_1}}

Message: "{processed_message[:512]}"
JSON:"""
        try:
            print("[MOOD_TOOLS] 🤖 Running LLM emotion analysis...")
            response = llm.invoke(prompt)
            content = re.sub(r"```(?:json)?", "", response.content).strip()
            parsed = json.loads(content)
            
            raw_emotion = parsed.get("label", "neutral").lower()
            confidence = round(float(parsed.get("score", 0.5)), 2)
            print(f"[MOOD_TOOLS] ✅ LLM emotion result: {raw_emotion} ({confidence})")
        except Exception as e:
            print(f"[MOOD_TOOLS] ⚠️ LLM returned invalid result, falling back to neutral: {e}")
            raw_emotion = "neutral"
            confidence = 0.5
        # ────────────────────────────────────────────────────────
        
        # GoEmotions (28 labels) -> SentiMind Core Emotions (6 labels)
        # FIX 2: Standardize ALL fear/anxiety variants to 'anxiety' for
        # clinical consistency. The app uses 'anxiety' not 'fear' everywhere.
        go_emotions_map = {
            # Joy / Positive cluster
            'admiration': 'joy', 'amusement': 'joy', 'approval': 'joy', 'caring': 'joy',
            'desire': 'joy', 'excitement': 'joy', 'gratitude': 'joy', 'joy': 'joy',
            'love': 'joy', 'optimism': 'joy', 'pride': 'joy', 'relief': 'joy',
            # Surprise cluster
            'surprise': 'surprise', 'realization': 'surprise',
            # Anger / Disgust cluster
            'anger': 'anger', 'annoyance': 'anger', 'disapproval': 'anger', 'disgust': 'disgust',
            # Sadness cluster
            'sadness': 'sadness', 'disappointment': 'sadness', 'grief': 'sadness', 'remorse': 'sadness',
            # Fear / Anxiety cluster — FIX: ALL map to 'anxiety' (consistent label)
            'fear': 'anxiety', 'nervousness': 'anxiety', 'anxiety': 'anxiety',
            # Neutral / Ambiguous
            'confusion': 'neutral', 'curiosity': 'neutral', 'neutral': 'neutral',
            'embarrassment': 'sadness', 'shame': 'sadness',
        }
        
        # Map to core emotion
        emotion = go_emotions_map.get(raw_emotion, "neutral")
        
        # Context-aware correction for commonly misinterpreted phrases
        message_lower = message.lower()
        
        # Negative context phrases that indicate the emotion is NOT positive
        mocking_context_indicators = [
            "laughed at me", "laughing at me", "made fun of me", "mocked me",
            "laughed at my", "laughing at my", "everyone laughed",
            "they laughed", "he laughed", "she laughed", "people laughed"
        ]
        
        failure_context_indicators = [
            "good at nothing", "im a failure", "i'm a failure", "fail at everything",
            "good for nothing", "so stupid", "useless", "pointless"
        ]
        
        # FIX 3: Neutral-phrasing indicators — model wrongly labels these as 'joy'
        # because GoEmotions picks up on polite/positive-toned language patterns.
        neutral_override_indicators = [
            "i feel okay", "feel okay today", "feeling okay", "i'm okay",
            "feel fine", "i feel fine", "feeling fine", "i'm fine",
            "feel alright", "feeling alright", "i'm alright",
            "nothing special happened", "just a normal day", "average day",
            "nothing much", "not much going on", "same as usual",
        ]
        
        # FIX 3: Anxiety/help-seeking phrases misclassified as 'joy'
        anxiety_override_indicators = [
            "manage my anxiety", "managing my anxiety", "need guidance",
            "need help with anxiety", "guidance on managing",
            "i need some guidance", "help me cope",
        ]
        
        # If model detected joy/surprise but message has negative context, correct it
        if emotion in ['joy', 'surprise']:
            if any(phrase in message_lower for phrase in mocking_context_indicators):
                print(f"[MOOD_TOOLS] ✅ Context correction: '{emotion}' → 'sadness' (detected mocking context)")
                emotion = 'sadness'
                confidence = 0.80
            elif any(phrase in message_lower for phrase in failure_context_indicators):
                print(f"[MOOD_TOOLS] ✅ Context correction: '{emotion}' → 'sadness' (detected failure/worthlessness context)")
                emotion = 'sadness'
                confidence = 0.85
            elif any(phrase in message_lower for phrase in neutral_override_indicators):
                print(f"[MOOD_TOOLS] ✅ Context correction: '{emotion}' → 'neutral' (detected neutral phrasing)")
                emotion = 'neutral'
                confidence = 0.75
            elif any(phrase in message_lower for phrase in anxiety_override_indicators):
                print(f"[MOOD_TOOLS] ✅ Context correction: '{emotion}' → 'anxiety' (detected anxiety help-seeking)")
                emotion = 'anxiety'
                confidence = 0.80
        
        sentiment_map = {
            'anger': 'negative', 'disgust': 'negative', 'fear': 'negative',
            'sadness': 'negative', 'anxiety': 'negative',
            'joy': 'positive', 'surprise': 'positive',
            'neutral': 'neutral'
        }
        
        # Calculate therapeutic intensity based on emotion type
        if emotion == 'neutral':
            # Neutral statements shouldn't trigger high-intensity interventions
            intensity = round(0.1 + (confidence * 0.15), 2)  # Max 0.25
        elif emotion in ['joy', 'surprise']:
            # Positive emotions shouldn't trigger crisis/distress protocols
            intensity = round(0.15 + (confidence * 0.2), 2) # Max 0.35
        else:
            # Negative emotions: high confidence = high distress intensity
            intensity = round(confidence * 0.9 + 0.1, 2)
        
        print(f"[MOOD] ✔  FINAL EMOTION │ {emotion.upper()} │ sentiment={sentiment_map.get(emotion, 'neutral')} │ intensity={intensity:.0%} │ confidence={confidence:.0%}")
        
        return {
            "emotion": emotion,
            "sentiment": sentiment_map.get(emotion, "neutral"),
            "intensity": intensity,
            "confidence": confidence
        }
    
    except Exception as e:
        print(f"[MOOD_TOOLS] ❌ Error analyzing mood: {str(e)[:100]}")
        print(f"[MOOD_TOOLS] 🛡️ Returning neutral fallback")
        return {
            "emotion": "neutral",
            "sentiment": "neutral",
            "intensity": 0.5,
            "confidence": 0.0
        }

