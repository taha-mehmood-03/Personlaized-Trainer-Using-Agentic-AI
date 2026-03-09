# SentiMind v3.0: Next-Generation Intelligent Therapy Architecture

## Executive Summary

SentiMind has already proven its superiority over traditional ReAct agents through its **Deterministic Hybrid Architecture** — a strict node pipeline that makes exactly **1 LLM call per message** and handles all reasoning through Python, local ML models, and database queries.

**SentiMind v3.0** extends this foundation by adding 8 clinically-intelligent subsystems. These upgrades push SentiMind beyond what competitors like **Woebot, Wysa, and Replika** offer, without violating the core constraint: **no ReAct loops, no multi-LLM chains, one LLM call only**.

**Current State (v2.0):** The system already has `ConversationPhase`, `BehaviorProfile`, `TechniqueOutcome`, and a `conversation_planner_node.py`. These are strong foundations to build upon.

---

## 🔍 Competitor Gap Analysis

| Capability | Woebot | Wysa | Replika | SentiMind v2 | SentiMind v3 |
|:---|:---:|:---:|:---:|:---:|:---:|
| Local emotion NLP | ❌ | ❌ | ❌ | ✅ | ✅ |
| CBT Technique DB | ✅ | ✅ | ❌ | ✅ | ✅ |
| Cognitive Distortion Detection | ❌ | ❌ | ❌ | ❌ | ✅ |
| Persistent Psych Profile | ❌ | Partial | Basic | Partial | ✅ |
| Emotion Trajectory Tracking | ❌ | ❌ | ❌ | Partial | ✅ |
| RL-Ranked Recommendations | ❌ | ❌ | ❌ | ❌ | ✅ |
| Crisis Bypass (no LLM) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Proactive Mental Health Monitoring | ❌ | Partial | ❌ | ❌ | ✅ |
| Multi-Modal Fusion (text + voice) | ❌ | ❌ | ❌ | Partial | ✅ (ready) |
| Single LLM Call / message | ❌ | ❌ | ❌ | ✅ | ✅ |

---

## 🏗️ v3 Node Pipeline (Full Architecture)

```
USER INPUT
    │
    ▼
┌──────────────────────────────────────────────┐
│ [NODE 1] INTAKE                              │
│ • Load user stats + preferences              │
│ • ChromaDB semantic memory pull              │
│ • Load Psychological Profile (NEW)           │
│ ✅ NO LLM — ~150ms                           │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│ [NODE 2] MOOD ANALYZER                       │
│ • DistilRoBERTa → emotion, intensity (0-1)   │
│ • Context-aware heuristic corrections        │
│ ✅ NO LLM — ~400ms                           │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← NEW (2a)
│ [NODE 2a] MULTI-MODAL FUSION (FUTURE-READY)  │
│ • Merge text + optional voice emotion        │
│ • Compute fused_emotion, fused_intensity     │
│ ✅ NO LLM — <5ms                             │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← NEW (2b)
│ [NODE 2b] COGNITIVE DISTORTION DETECTOR      │
│ • Keyword + pattern analysis                 │
│ • Output: distortion_type, distortion_conf   │
│ ✅ NO LLM — <50ms                            │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← NEW (2c)
│ [NODE 2c] EMOTION TRAJECTORY UPDATER        │
│ • Append current emotion to session log      │
│ • Compute emotion_delta (worsening/stable/   │
│   improving)                                 │
│ ✅ NO LLM — <5ms                             │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← MODIFIED
│ [NODE 3] CONVERSATION PLANNER (Enhanced)     │
│ • Phase detection (VENTING/REFLECT/SOLUTION/ │
│   RECOVERY) — existing                       │
│ • Strategy selection — existing              │
│ • Incorporates distortion_type → reframe str.│
│ ✅ NO LLM — <5ms                             │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← NEW (3b)
│ [NODE 3b] BEHAVIORAL ACTIVATION ENGINE       │
│ • Recommend real-world micro-actions         │
│ • Based on: emotion, intensity, time, profile│
│ ✅ NO LLM — ~50ms                            │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← MODIFIED
│ [NODE 4] TECHNIQUE SELECTOR (RL-Enhanced)    │
│ • Existing: DB query by emotion              │
│ • NEW: Contextual RL ranking by user history │
│   + success rates + profile preferences      │
│ ✅ NO LLM — ~100ms                           │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
                ┌─────┴──────┐
          intensity < 0.8  intensity >= 0.8
                │             │
                ▼             ▼
         NORMAL PATH     CRISIS PATH
                │             │
                ▼             ▼
┌───────────────────┐  ┌──────────────────────┐
│ [NODE 4.5]        │  │ [NODE 4] CRISIS       │
│ ROLE SELECTOR     │  │ HANDLER (Existing)    │
│ friend/coach/     │  │ Templated response    │
│ trainer           │  │ 988 + resources       │
│ ✅ NO LLM        │  │ ✅ ZERO LLM — <10ms   │
└────────┬──────────┘  └──────────┬───────────┘
         │                        │
         ▼                        │
┌──────────────────────────────────────────────┐
│ [NODE 5] RESPONSE GENERATOR                  │
│ ⚡ SINGLE LLM CALL (Groq/Llama 3.1)          │
│ Structured payload now includes:             │
│ • emotion + intensity                        │
│ • distortion_type + reframe instruction      │
│ • behavioral micro-action                    │
│ • agent_role                                 │
│ • conversation_strategy                      │
│ ~400 tokens in, ~100 tokens out              │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← NEW (post-LLM)
│ [NODE 5b] PSYCHOLOGICAL PROFILE UPDATER      │
│ • Update resilience_score, coping_style      │
│ • Update emotional triggers list            │
│ • No LLM — pure stat accumulation           │
│ ✅ NO LLM — ~50ms                            │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│ [NODE 6] SESSION SAVER (Existing)            │
│ + NEW: Save emotion trajectory               │
│ + NEW: Save distortion_type detected         │
│ + NEW: Save micro_action_recommended         │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐  ← NEW (async/background)
│ [NODE 7] PROACTIVE MONITOR (Background)      │
│ • Runs ASYNC, outside conversation pipeline  │
│ • Reads historical MoodLog data              │
│ • Fires proactive alerts: repeated spikes,   │
│   gradual decline, sleep deterioration       │
│ ✅ NO LLM — pure analytics                   │
└──────────────────────────────────────────────┘
```

---

## 📋 New Subsystem Deep Dive

### 1. Cognitive Distortion Detector (Node 2b)

**Location:** `nodes/cognitive_distortion_node.py`

**Purpose:** Identify maladaptive thinking patterns in the user's language that CBT specifically targets.

**Distortion Lexicon (Deterministic Pattern Matching):**

```python
DISTORTION_PATTERNS = {
    "catastrophizing":     ["always", "never", "everything", "ruined", "hopeless", "disaster"],
    "black_white":         ["completely", "total failure", "perfect", "100%", "not at all"],
    "overgeneralization":  ["always happens", "nobody", "everyone", "every time", "it's always me"],
    "mind_reading":        ["they think", "he must think", "she thinks i'm", "people see me as"],
    "personalization":     ["my fault", "i caused", "because of me", "i made them"],
    "emotional_reasoning": ["i feel like it's true", "i know it's bad because i feel it"],
    "should_statements":   ["i should", "i must", "i have to", "i ought"],
    "magnification":       ["it's so bad", "the worst", "unbearable", "i can't handle"],
}
```

**Output state fields:**
```python
{
    "distortion_type": "catastrophizing",       # Primary distortion detected
    "distortion_confidence": 0.78,              # 0.0-1.0
    "distortion_explanation": "User uses 'always' and 'never' pattern...",
    "all_distortions": ["catastrophizing", "black_white"],  # Secondary matches
}
```

**Impact on downstream nodes:**
- `conversation_planner` picks `"reframe"` strategy when `distortion_confidence > 0.5`.
- `response_generator` LLM payload includes: *"The user exhibits catastrophizing. Gently reframe this into conditional thinking."*

---

### 2. Psychological Profile Engine (Node 5b + Intake)

**Location:** `nodes/psych_profile_updater.py`, extends `BehaviorProfile` in DB.

**Profile Fields (New DB Schema):**

```prisma
model PsychProfile {
  id                String   @id @default(cuid())
  userId            String   @unique
  user              User     @relation(...)

  // Coping architecture
  copingStyle       String   @default("avoidant")   // avoidant | proactive | mixed
  techniqueAccRate  Float    @default(0.5)           // % of techniques accepted
  reflectionDepth   Float    @default(0.5)           // Low = venting only, High = reflective

  // Emotional landscape
  anxietyBaseline   Float    @default(0.5)           // Rolling 30-day avg intensity
  resilienceScore   Float    @default(0.5)           // Improves with positive trajectories
  dominantEmotion   String   @default("neutral")
  emotionalTriggers String[]                         // ["work", "family", "social"]

  // Social & motivational
  motivationType    String   @default("external")   // external | internal | mixed
  socialDependency  Float    @default(0.5)           // High = mentions people often

  // Distortion history
  topDistortions    String[]                         // ["catastrophizing", "mind_reading"]
  distortionCount   Int      @default(0)

  updatedAt         DateTime @updatedAt
}
```

**Update Algorithm (Python — no LLM):**
- `copingStyle`: Tracks ratio of proactive technique acceptance vs. passive venting.
- `resilienceScore`: Increases by 0.02 per positive `emotion_delta`, decreases on sustained crisis.
- `emotionalTriggers`: Extracts nouns from high-intensity messages via spaCy NER.
- `anxietyBaseline`: Rolling mean of last 30 MoodLog intensities.

---

### 3. Conversation Phase Engine (Enhanced in Node 3)

Already exists in `conversation_planner_node.py`. **Enhancements in v3:**

- Phase transitions now also consider `distortion_type`:
  - **VENTING + distortion detected** → stay in VENTING (user is not ready to reflect).
  - **REFLECTION + distortion detected** → switch strategy to `reframe` (prime moment for CBT).
- Phase is now **saved per-message** to `Message` table for trajectory analysis.

**Phase → Technique Readiness Matrix (v3):**

| Phase | Intensity | Distortion | Readiness | Strategy |
|:---|:---:|:---:|:---:|:---|
| VENTING | High | None | 0.1 | `validate_only` |
| VENTING | High | Detected | 0.2 | `ask_question` |
| REFLECTION | Medium | Detected | 0.75 | `reframe` |
| SOLUTION | Medium | None | 0.9 | `suggest_technique` |
| RECOVERY | Low | None | 0.5 | `validate_only` |

---

### 4. Behavioral Activation Engine (Node 3b)

**Location:** `nodes/behavioral_activation_node.py`

**Purpose:** Recommend real-world micro-actions alongside (or instead of) mindfulness exercises. Based on the evidence-based behavioral activation therapy (BAT) model used in CBT.

**Decision Matrix (No LLM):**

```python
ACTIVATION_RULES = {
    ("sadness", "high"):   ["Take a 10-minute walk outside", "Message one person you trust", "Tidy a small area of your space"],
    ("anxiety", "medium"): ["Drink a glass of water now", "Step away from your screen for 5 minutes", "Write 3 things you can control"],
    ("anger", "high"):     ["Do 10 slow, deep breaths", "Walk around the block", "Write what triggered this, not who"],
    ("neutral", "low"):    ["Optional: Journal about your day", "Check in with a friend"],
    ("fear", "any"):       ["Ground yourself: name 5 things you can see right now"],
}
```

**Context-Aware Filters:**
- If `time_of_day` is `"night"` → filter out walk/outdoor suggestions.
- If `psych_profile.copingStyle == "avoidant"` → start with smallest, least-effortful action.
- If `social_dependency > 0.7` → prioritize social actions (e.g., "message a friend").

**Output state fields:**
```python
{
    "micro_action": "Take a 10-minute walk outside",
    "micro_action_rationale": "Physical movement reduces cortisol for sadness states.",
}
```

---

### 5. RL-Ranked Recommendation Engine (Enhancement to Node 4)

**Location:** Enhancement in `nodes/technique_selector_node.py`.

**Algorithm:** Contextual Multi-Armed Bandit (lightweight — no external ML library needed).

**Feature Vector Per User-Technique Pair:**

```python
features = {
    "emotion_match":     float,   # 1.0 if technique targets current emotion
    "user_past_rating":  float,   # User's own rating of this technique (0-5 / 5)
    "global_avg_rating": float,   # avgRating from DB
    "time_since_used":   float,   # Recent use → lower score (variety)
    "phase_match":       float,   # 1.0 if technique fits current conversation phase
    "profile_fit":       float,   # High if matches user's coping style
    "intensity_match":   float,   # Difficult technique penalized if intensity is high
}
```

**Scoring Formula:**
```
score = (0.30 × emotion_match) + (0.25 × user_past_rating) + 
        (0.15 × global_avg_rating) + (0.10 × time_since_used) + 
        (0.10 × phase_match) + (0.05 × profile_fit) + (0.05 × intensity_match)
```

**Result:** The top-scoring technique is selected. All scores are persisted to `TechniqueOutcome` for model improvement over time.

---

### 6. Emotion Trajectory Modeling (Node 2c)

**Location:** `nodes/emotion_trajectory_node.py`

**Purpose:** Track how emotion evolves *within* and *across* sessions.

**Per-Session In-Memory Window:**
```python
session_emotion_window = [
    {"emotion": "anxiety", "intensity": 0.75, "turn": 1},
    {"emotion": "anxiety", "intensity": 0.60, "turn": 2},
    {"emotion": "sadness",  "intensity": 0.45, "turn": 3},
]

# Computed output:
emotion_delta = "improving"  # intensity fell > 0.1 over last 2 turns
emotion_before = "anxiety"   # First emotion this session
emotion_now = "sadness"      # Current
intensity_change = -0.30     # Total change since session start
```

**Saved to DB (`TechniqueOutcome`):** After each session, `intensityAfter` is filled in and `effectiveness` is calculated as `max(0, intensity_before - intensity_after)` — a ground-truth effectiveness signal that improves the RL ranking over time.

---

### 7. Multi-Modal Emotion Fusion (Node 2a)

**Location:** `nodes/multimodal_fusion_node.py`

**Current State:** Only text emotion exists.
**Design:** Built as a fusion layer that is a no-op when only text is available, but can weight multiple input modalities:

```python
def fuse_emotions(text_emotion, text_intensity, voice_emotion=None, voice_intensity=None):
    if voice_emotion is None:
        # Single modality — pass through
        return text_emotion, text_intensity

    # Future: weighted fusion when voice is active
    # Voice is weighted at 0.4 (text is more reliable for nuance)
    VOICE_WEIGHT = 0.4
    TEXT_WEIGHT  = 0.6
    fused_intensity = (TEXT_WEIGHT * text_intensity) + (VOICE_WEIGHT * voice_intensity)
    # Emotion: text wins on tie, voice overrides if confidence >> text_confidence
    fused_emotion = voice_emotion if voice_intensity > text_intensity + 0.2 else text_emotion
    return fused_emotion, fused_intensity
```

**State fields added:**
- `fused_emotion`, `fused_intensity` — used by all downstream nodes instead of raw `emotion`/`intensity`.
- The `Message` table already has `voiceEmotion`, `voiceArousal`, `voiceValence` columns — the schema is already ready.

---

### 8. Proactive Mental Health Monitor (Node 7 — Background)

**Location:** `nodes/proactive_monitor.py` (called by a scheduled job, not the live pipeline)

**Mechanism:** Runs every night via a cron job / FastAPI background task. Reads the last 14 days of `MoodLog` for each user.

**Detection Rules:**

```python
class ProactiveAlerts:
    @staticmethod
    def detect(mood_logs: list[MoodLog]) -> list[str]:
        alerts = []
        intensities = [m.intensity for m in mood_logs]
        
        # Rule 1: Gradual decline (intensity rising > 0.15 over 7 days)
        if len(intensities) >= 7:
            rolling_trend = intensities[-1] - intensities[-7]
            if rolling_trend > 0.15:
                alerts.append("gradual_mood_decline")
        
        # Rule 2: Repeated anxiety spikes (intensity > 0.65 appearing > 3x in 5 days)
        recent = [m for m in mood_logs[-5:] if m.intensity > 0.65]
        if len(recent) >= 3:
            alerts.append("repeated_anxiety_spikes")
        
        # Rule 3: No check-in for 3+ days (disengagement)
        if not mood_logs or (datetime.now() - mood_logs[-1].createdAt).days > 3:
            alerts.append("disengagement_risk")

        return alerts
```

**Proactive Message:** When an alert fires, it pre-loads a `ProactiveNotification` record into the DB. The next time the user opens the app, the Intake Node reads this flag and the Response Generator receives an instruction: *"User hasn't checked in for 4 days; gently ask how they're doing."*

---

## 🗄️ Database Schema Additions (Prisma)

```prisma
// All additions to schema.prisma

model PsychProfile {
  id                String   @id @default(cuid())
  userId            String   @unique
  user              User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  
  copingStyle       String   @default("avoidant")
  techniqueAccRate  Float    @default(0.5)
  reflectionDepth   Float    @default(0.5)
  anxietyBaseline   Float    @default(0.5)
  resilienceScore   Float    @default(0.5)
  dominantEmotion   String   @default("neutral")
  emotionalTriggers String[]
  motivationType    String   @default("external")
  socialDependency  Float    @default(0.5)
  topDistortions    String[]
  distortionCount   Int      @default(0)
  
  updatedAt         DateTime @updatedAt
}

model EmotionSnapshot {
  id        String   @id @default(cuid())
  sessionId String
  session   Session  @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  userId    String
  
  turn      Int
  emotion   Emotion
  intensity Float
  sentiment Sentiment
  
  distortionType String?
  phase          ConversationPhase?
  
  createdAt DateTime @default(now())

  @@index([sessionId])
  @@index([userId])
}

model ProactiveNotification {
  id        String   @id @default(cuid())
  userId    String
  user      User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  
  alertType  String   // gradual_mood_decline | repeated_anxiety_spikes | disengagement_risk
  isRead     Boolean  @default(false)
  payload    String?  @db.Text  // JSON: hint for response generator
  
  createdAt  DateTime @default(now())

  @@index([userId])
  @@index([isRead])
}

// Add to User model:
  psychProfile          PsychProfile?
  emotionSnapshots      EmotionSnapshot[]
  proactiveNotifications ProactiveNotification[]
```

---

## 🧠 Updated State Schema

```python
class MentalHealthState(TypedDict):
    # ── Core (unchanged) ────────────────────────────────
    messages:          list[BaseMessage]
    user_id:           str
    session_id:        str
    
    # ── Intake (unchanged) ──────────────────────────────
    is_new_user:        bool
    session_count:      int
    user_preferences:   dict
    memory_context:     str
    psych_profile:      dict        # NEW: loaded from PsychProfile DB model
    proactive_alert:    str | None  # NEW: pre-loaded proactive hint

    # ── Mood Analyzer (unchanged) ───────────────────────
    emotion:           str
    sentiment:         str
    intensity:         float
    confidence:        float

    # ── Multi-Modal Fusion (Node 2a) — NEW ──────────────
    fused_emotion:     str          # = text emotion or merged
    fused_intensity:   float        # = text or weighted fusion
    voice_emotion:     str | None
    voice_intensity:   float | None

    # ── Cognitive Distortion (Node 2b) — NEW ────────────
    distortion_type:         str | None   # "catastrophizing" | None
    distortion_confidence:   float
    distortion_explanation:  str | None
    all_distortions:         list[str]

    # ── Emotion Trajectory (Node 2c) — NEW ──────────────
    emotion_trajectory:  list[dict]    # [{emotion, intensity, turn}, ...]
    emotion_delta:       str           # "worsening" | "stable" | "improving"
    session_start_intensity: float

    # ── Conversation Planner (unchanged + enhanced) ──────
    conversation_phase:    str
    conversation_strategy: str
    technique_readiness:   float
    session_message_count: int

    # ── Behavioral Activation (Node 3b) — NEW ───────────
    micro_action:           str | None
    micro_action_rationale: str | None

    # ── Technique Selector (RL-enhanced) ────────────────
    recommended_technique:              dict
    recommended_techniques_by_category: dict
    technique_rl_score:                 float   # NEW: RL ranking score

    # ── Role Selector (unchanged) ──────────────────────
    agent_role: str

    # ── Crisis (unchanged) ──────────────────────────────
    crisis_detected:   bool
    crisis_level:      str
    crisis_resources:  dict

    # ── Response Generator (unchanged) ──────────────────
    final_response:   str

    # ── Metadata ─────────────────────────────────────────
    tools_used:           list[str]
    processing_time_ms:   int
```

---

## ⚡ Performance Budget (v3.0)

| Node | Time | LLM? | Notes |
|:---|:---:|:---:|:---|
| Intake + Profile Load | ~200ms | ❌ | Adds PsychProfile query |
| Mood Analyzer | ~400ms | ❌ | Unchanged |
| Multimodal Fusion | <5ms | ❌ | Passthrough if no voice |
| Cognitive Distortion | <50ms | ❌ | Regex/keyword scan |
| Emotion Trajectory | <5ms | ❌ | In-memory list op |
| Conversation Planner | <5ms | ❌ | Enhanced with distortion |
| Behavioral Activation | <50ms | ❌ | Lookup table |
| Technique Selector (RL) | ~100ms | ❌ | DB query + score calc |
| Crisis Router | <1ms | ❌ | Threshold check |
| Role Selector | <1ms | ❌ | Threshold check |
| **Response Generator** | ~1,250ms | **✅ ONLY ONCE** | Structured prompt |
| Psych Profile Updater | ~100ms | ❌ | DB write |
| Session Saver | ~100ms | ❌ | Expanded fields saved |
| **TOTAL** | **~2,300ms** | | **+300ms vs v2** |

**Token Budget:** Still ~400-450 tokens/message. The new payload fields (distortion hint, micro-action) add approximately 30-40 tokens.

---

## 🛡️ Clinical Safety Framework

1. **Crisis is Unbreakable:** The crisis gate (intensity ≥ 0.8) fires *before* the LLM. No LLM output can bypass it.
2. **Distortion Detection Never Diagnoses:** The system detects linguistic *patterns*, not clinical diagnoses. Responses always frame it as "I notice your wording..." never "You have cognitive distortions."
3. **Profile Data is Additive Only:** The PsychProfile only grows richer over time. It never resets. This prevents losing streak data that could be clinically relevant.
4. **Proactive Alerts Trigger Care, Not Lectures:** The proactive notification system softly invites the user back ("It's been a few days — how are you feeling?") without being prescriptive or alarming.
5. **LLM Guardrails Stay Strict:** The system prompt for the LLM continues to hard-prohibit: diagnosis, medication advice, and any replacement for professional help.

---

## 📁 New Files to Create

| File | Purpose |
|:---|:---|
| `nodes/cognitive_distortion_node.py` | Distortion pattern detection |
| `nodes/multimodal_fusion_node.py` | Voice + text emotion fusion layer |
| `nodes/emotion_trajectory_node.py` | Session-level emotion tracking |
| `nodes/behavioral_activation_node.py` | Real-world micro-action engine |
| `nodes/psych_profile_updater.py` | Persistent pysch model updater |
| `nodes/proactive_monitor.py` | Background mood trend analysis |
| `agent/graph_v3.py` | Updated LangGraph StateGraph wiring |

---

*SentiMind v3.0 — Designed to be psychologically intelligent, scalable, and clinically responsible. All critical reasoning remains deterministic. The LLM is a speaker, not a thinker.*
