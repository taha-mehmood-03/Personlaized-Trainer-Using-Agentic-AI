# SentiMind — FYP Objectives & Feature Implementation

**Project**: SentiMind — AI-Powered Personalized Mental Health & Wellness Platform  
**Student**: Taha Mehmood  
**Document Date**: 2026-06-19  
**Status**: All three objectives fully implemented

---

## Platform Overview

SentiMind is a full-stack AI mental health platform that combines real-time emotion analysis, personalized therapeutic exercise delivery, and strict regulatory compliance into a single conversational interface. Users interact through a Next.js 14 chat UI; messages flow through a LangGraph pipeline on a FastAPI backend powered by Google Gemini LLMs, with all clinical data stored in a HIPAA/GDPR-compliant PostgreSQL database (Supabase).

**Technology Stack**:
| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, SSE streaming |
| Backend | FastAPI (Python), LangGraph, Pydantic |
| LLM | Google Gemini (Flash / Flash-Lite), OpenRouter (Groq/llama-3.3-70b) |
| Database | Prisma ORM + Supabase PostgreSQL |
| Vector Memory | pgvector (HNSW index), MiniLM-L6-v2 embeddings (384-dim) |
| Audio Analysis | librosa (MFCCs, VAD), Praat/parselmouth (F0, jitter, shimmer, HNR) |
| Crisis Alerts | Twilio WhatsApp API |

---

## Objective 1 — Detect and Interpret Emotional States via Multimodal Fusion

**Definition**: Automatically determine the user's emotional state from their typed message and/or recorded voice using text analysis, psychoacoustic signal processing, and a fusion algorithm that combines both modalities into a single clinical representation.

**Status: FULLY IMPLEMENTED**

---

### 1.1 Text Emotion Classification (LLM-Based)

**Implementation file**: `mental_health_wellness/src/mental_health_wellness/llm/llm_classifier.py`

Every user message is passed to a Gemini Flash model with a structured clinical prompt. The model is configured with `temperature=0.0` for deterministic, reproducible output.

**What is classified**:

| Classifier | Purpose | Model | Output |
|---|---|---|---|
| Crisis pre-screener | Suicidal ideation detection | llama-3.3-70b (Groq) | `crisis_level: low/medium/high` |
| Mood analyzer | Core emotion + sub-emotion | Gemini Flash-Lite | `emotion`, `primary_sub_emotion`, `intensity` |
| Intent classifier | Conversational intent routing | Gemini Flash-Lite | `intent` (11+ categories) |
| Distortion detector | Cognitive error identification | Gemini Flash | 8 distortion types |
| Severity scorer | Clinical severity benchmark | Gemini Flash | PHQ-9 (0-27), GAD-7 (0-21) scores |

**Emotion Taxonomy**:
- **Core emotions** (8 classes): `ANGER`, `DISGUST`, `FEAR`, `JOY`, `NEUTRAL`, `SADNESS`, `SURPRISE`, `ANXIETY`
- **Primary sub-emotion**: More granular label (e.g., `panic`, `hopelessness`, `social_humiliation`)
- **Secondary sub-emotions**: Co-occurring secondary states (array)
- **Sentiment**: `POSITIVE`, `NEGATIVE`, `NEUTRAL`
- **Intensity**: Float 0.0–1.0 (how strongly the emotion is expressed)
- **Detected symptoms**: Clinically-relevant signals (e.g., `racing_thoughts`, `sleep_disruption`)
- **Detected behaviors**: Behavioral patterns (e.g., `avoidance`, `rumination`, `isolation`)
- **Detected contexts**: Situational factors (e.g., `academic_pressure`, `relationship_conflict`)

**Deterministic Crisis Safety Net** (runs before LLM, < 50ms):
A regex-based screener checks for explicit self-harm language (18 HIGH-risk patterns, 5 MEDIUM-risk patterns). This hard-wired gate ensures zero reliance on the LLM for the most critical safety decisions.

**LLM Crisis 3-Step Dimensional Reasoning**:
```
STEP A (DESIRE)  — Does the person express an active wish to die or harm themselves?
                    NO → low risk, STOP immediately.
STEP B (CONTEXT) — Nature of statement: venting? cognitive distortion? passive ideation? active desire?
STEP C (LETHALITY) — Specific method, timeline, or access to means?
                    YES → HIGH risk regardless of A/B outcome.
```

**Robust JSON Extraction**: LLM output is parsed via a 4-strategy fallback chain:
1. Direct `json.loads()`
2. Markdown fence extraction (` ```json ... ``` `)
3. Brace-balanced substring extraction
4. Regex field-by-field recovery

---

### 1.2 Voice & Audio Emotion Analysis

**Implementation files**:
- `mental_health_wellness/src/mental_health_wellness/voice/acoustic_features.py` — DSP signal processing
- `mental_health_wellness/src/mental_health_wellness/pipeline/voice_preprocessing.py` — orchestration

When the user records a voice message, two parallel analyses run:

#### Psychoacoustic DSP Analysis (deterministic, no LLM)

Using **librosa** (Python audio library) and **Praat/parselmouth** (acoustic phonetics library):

| Measure | Tool | Clinical Relevance |
|---|---|---|
| **F0 Pitch Mean/Std** | Praat | Elevated pitch variance = anxiety; flat pitch = depression |
| **Jitter** (vocal tremor %) | Praat | Involuntary pitch variation = physiological distress |
| **Shimmer** (amplitude variation %) | Praat | Amplitude instability = emotional dysregulation |
| **HNR** (harmonics-to-noise ratio, dB) | Praat | Low HNR = strained, irregular voice |
| **MFCCs** (13-dim vector) | librosa | Timbre fingerprint of emotional coloring |
| **RMS Loudness** | librosa | Volume envelope (monotone = flat affect) |
| **Spectral Flux** | librosa | Timbre change rate (expressive variability) |
| **Pause Density** | librosa (energy VAD) | Ratio of silence (high = hesitancy, withdrawal) |
| **Speech Rate** | librosa | Segments/second (fast = anxiety; slow = depression) |

**Acoustic Distress Proxy** (composite deterministic score):
```
acoustic_distress_proxy = 0.30 × jitter_norm
                        + 0.30 × shimmer_norm
                        + 0.20 × pitch_variability_norm
                        + 0.20 × hnr_strain_norm
                        
Result: Float 0.0–1.0 (0 = calm, 1 = high physiological distress)
```

This score is a mathematical measurement, not a model prediction — it provides an objective physiological distress baseline independent of what the user says.

#### Gemini Holistic Voice Analysis (semantic + tonal)

Gemini receives the audio file and simultaneously:
- Transcribes the speech verbatim
- Analyzes both the semantic content AND the vocal delivery (tone, affect, hesitations)
- Returns: `emotion`, `arousal` (0-1), `valence` (0-1), `distress_index` (0-1), `confidence` (0-1)

This is more holistic than DSP alone: Gemini can detect a person saying "I'm fine" in a crying voice and correctly identify the contradiction.

**Voice Feature Fields**:
```json
{
  "emotion": "fear | sadness | anxiety | ...",
  "primary_sub_emotion": "panic | hopelessness | ...",
  "secondary_sub_emotions": ["restlessness", "guilt"],
  "intensity": 0.0–1.0,
  "arousal": 0.0–1.0,
  "valence": 0.0–1.0,
  "distress_index": 0.0–1.0,
  "confidence": 0.0–1.0,
  "pause_density": 0.0–1.0,
  "acoustic_distress_proxy": 0.0–1.0,
  "acoustic_features": { "pitch_mean", "pitch_std", "jitter", "shimmer", "hnr", ... },
  "mfcc_vector": [13 float values]
}
```

---

### 1.3 Multimodal Emotion Fusion Algorithm

**Implementation file**: `mental_health_wellness/src/mental_health_wellness/pipeline/emotion_fusion_node.py`

The fusion node combines text analysis and voice analysis into a single authoritative emotional state. Three cases are handled:

**CASE 0 — Voice-Only Passthrough (Authoritative)**
When `voice_processed=True` and the route is `therapeutic` or `crisis`, Gemini's audio result has already analyzed both the spoken content and the vocal delivery together — no blending is more accurate. Safety checks are still applied (passive ideation detection, hedge reduction).

**CASE 1 — Text-Only (No Audio)**
Applied intensity normalization:
- Cap `neutral` emotion at maximum 0.20 intensity (prevent false alarming)
- Cap low-signal emotions (`joy`, `calm`) at 0.30
- Detect passive ideation phrases (19 patterns: "sleep forever", "don't want to live", "wish I wasn't here")
- Apply hedge reduction (50× multiplier for softeners: "a bit", "kind of", "slightly")
- Apply route-aware gate caps (e.g., chitchat → intensity = 0.0)

**CASE 2 — Three-Way Blend (Text + Voice Label + Acoustic)**

| Voice Confidence | Text Weight | Voice Label Weight | Acoustic Weight |
|---|---|---|---|
| High (≥ 0.50) | 50% | 30% | 20% |
| Low (< 0.50) | 70% | 15% | 15% |

Intensity blending:
```
fused_intensity = w_text × text_intensity
               + w_voice × voice_arousal
               + w_acoustic × distress_index
```

Emotion label selection: If text and voice agree → agreement bonus (+10% confidence). If they disagree → valence-weighted selection (higher valence score wins).

**Acoustic Override Rules** (detect emotional masking):

| Rule | Trigger | Override Action |
|---|---|---|
| Masking Language | "I'm fine" + effective_distress ≥ 0.50 | Override emotion to `sadness`, flag `possible_masking=True` |
| Positive Overclaim | "I'm amazing" + distressed voice ≥ 0.45 | Flag `possible_masking=True` |
| Hidden Distress | High distress (> 0.65) + neutral/positive text | Override to `sadness` |
| Suppressed Anxiety | High arousal (> 0.75) + neutral text | Override to `anxiety` |
| Hesitation Signal | High pause_density (> 0.40) + low intensity | Boost intensity +0.15 |

**Distress Anchoring System**:
The pipeline maintains `last_detected_emotion` and `peak_distress_intensity` across the conversation. These anchors are only updated on therapeutic disclosures (not on chitchat or short follow-up turns). This prevents the system from losing track of a user's true emotional baseline just because they briefly say "ok" or "yes, please".

**Final Output Fields Stored per Message**:
```json
{
  "fused_emotion": "sadness",
  "fused_intensity": 0.72,
  "primary_sub_emotion": "hopelessness",
  "secondary_sub_emotions": ["guilt", "emptiness"],
  "detected_symptoms": ["sleep_disruption", "anhedonia"],
  "detected_behaviors": ["isolation", "rumination"],
  "detected_contexts": ["academic_pressure"],
  "sentiment": "NEGATIVE",
  "mismatch": false,
  "possible_masking": false,
  "fusion_confidence": 0.84
}
```

---

## Objective 2 — Personalized Mental Health Exercise Recommendation

**Definition**: Based on the user's detected emotional state, historical interaction data, and their past feedback on exercises, the system selects and delivers the most appropriate mental health technique in a format tailored to their current condition.

**Status: FULLY IMPLEMENTED**

---

### 2.1 Technique Database

**Schema file**: `mental_health_wellness/prisma/schema.prisma` (Technique model)

Each technique in the database is described not just by its name and instructions, but with a rich clinical targeting profile:

**Targeting Fields**:
| Field | Purpose |
|---|---|
| `targetEmotions` | Which core emotions this helps (e.g., `[ANXIETY, FEAR]`) |
| `targetSubEmotions` | Specific sub-emotions it addresses (e.g., `panic`, `exam_anxiety`) |
| `targetSymptoms` | Clinically-relevant symptoms it targets (e.g., `racing_thoughts`, `physical_tension`) |
| `targetBehaviors` | Behavioral patterns it addresses (e.g., `avoidance`, `rumination`) |
| `bestForContexts` | Situational contexts (e.g., `exam_season`, `bedtime_rumination`) |
| `avoidSubEmotions` | When NOT to recommend (contraindicated sub-emotions) |
| `avoidSymptoms` / `avoidBehaviors` | Contraindicated clinical signals |

**Clinical Safety Fields**:
| Field | Purpose |
|---|---|
| `minPhq9` / `maxPhq9` | PHQ-9 score range the technique is safe for (0–27) |
| `safeAtSeverity` | Allowed severity levels: `MINIMAL`, `MILD`, `MODERATE`, `MODERATELY_SEVERE` |
| `contraindicatedFlags` | Block if present: `suicidal_ideation`, `psychomotor_agitation`, etc. |

**Intensity Routing Fields**:
| Field | Purpose |
|---|---|
| `minIntensity` / `maxIntensity` | Intensity range the technique is appropriate for |
| `pacingTier` | `normal`, `fast`, or `slow` — matches user's emotional state |
| `deliveryMode` | `exercise`, `reflective`, or `educational` |

**User Interaction Tracking**:
```prisma
model UserTechniqueRating {
  userId      String
  techniqueId String
  sessionId   String?
  rating      Int?        // 1–5 stars
  feedback    String?     // free-text comment ("helped me calm down")
  completed   Boolean     // whether user finished the exercise
  usedAt      DateTime
}
```

---

### 2.2 Recommendation Pipeline

**Implementation file**: `mental_health_wellness/src/mental_health_wellness/pipeline/technique_selector_node.py`

The pipeline follows six stages to reach the final recommendation:

#### Stage 1 — Readiness Gates

The system checks whether the user is ready to receive an exercise at this moment:
- **Consent gate**: If exercise consent is `denied_soft` or `denied_hard`, skip (unless user explicitly requested regulation help)
- **Strategy gate**: Skip if conversation planner set strategy to `validate_only`, `ask_question`, or `encourage_reflection` (the user needs validation first, not an exercise)
- **Route gate**: Skip for `chitchat`, `memory_query`, `contextual_followup` routes
- **Sub-emotion gate**: Skip for empathy-first sub-emotions (user needs to feel heard before receiving an exercise)
- **Context sufficiency gate**: Skip if `context_sufficiency_score < 0.65` (insufficient clinical info gathered)

#### Stage 2 — Emotion Inheritance

Addresses the problem of low-signal follow-up turns losing the clinical anchor:
```
SHORT CONSENT TURN ("yes sure", "ok") + anchored negative emotion
    → inherit anchored_emotion for technique targeting

NEUTRAL/JOY emotion + active therapeutic thread + distressed baseline
    → inherit thread emotion (e.g., "anxious" → target anxiety exercises)

NEEDS_TECHNIQUE + low intensity (< 0.45) + active therapeutic thread
    → floor intensity at 0.45 (prevent under-matching)
```

#### Stage 3 — Build Semantic Query

A rich 1,800-character clinical formulation is assembled:
```
"emotion: anxiety | intensity: 0.75 | primary feeling: panic |
 symptoms: racing_thoughts, physical_tension |
 context tags: exam_pressure, bedtime_rumination |
 thinking pattern: catastrophizing |
 PHQ-9 score: 8 | GAD-7 score: 12 |
 latest message: I can't stop thinking about my exam tomorrow..."
```
This carries the full clinical picture so the semantic search finds techniques that match the user's actual situation, not just their surface emotion.

#### Stage 4 — Semantic Ranking (pgvector)

All techniques are embedded using **MiniLM-L6-v2** (384-dimensional sentence embeddings) and stored in a pgvector table with an **HNSW** approximate nearest-neighbor index. The semantic query is embedded and compared using cosine similarity to find the most relevant techniques.

**Score Adjustments applied after retrieval**:

*Contextual Boosts* (deterministic Python rules for known clinical formulations):

| Situation Detected | Technique Boosted | Score Adjustment |
|---|---|---|
| Sleep + rumination + exam context | Worry Time | +4.0 |
| Sleep + rumination + exam context | Gratitude Journaling | -5.0 (penalty) |
| Catastrophic belief detected | Thought Record, Decatastrophizing | +4.3 / +4.1 |
| Social humiliation sub-emotion | Self-Compassion Letter | +4.3 |
| Environmental stressor | Environmental Design | +3.8 |
| Physical anxiety symptoms | Progressive Muscle Relaxation | +3.5 |
| Breathing exercise context | 4-7-8 Breathing | +3.2 |

*Personal History Adjustments*:

| User History Signal | Score Impact |
|---|---|
| User rated this technique ≥ 4 stars | +2.0 |
| User rated this technique ≤ 2 stars | −4.0 |
| User left negative text feedback | −1.5 |
| User left positive text feedback | +0.7 |
| Technique recently used (this session) | −1.2 |
| Hard ceiling: personally disliked (avg ≤ 2) | Max score capped at −2.0 |

#### Stage 5 — Clinical Safety Filter

Before finalizing the recommendation:
- Check `clinical_indicators` from the pipeline state against technique `contraindicatedFlags`
- Filter to techniques within the user's PHQ-9 score range
- Filter to techniques safe for the user's current severity level
- Remove techniques targeting suppressed topics (user explicitly opted out)

#### Stage 6 — Output

```json
{
  "recommended_technique": {
    "id": "technique_xyz",
    "name": "4-7-8 Breathing",
    "category": "Breathing",
    "description": "A breathing pattern that activates the parasympathetic...",
    "steps": ["Exhale completely...", "Inhale for 4 counts...", "Hold for 7...", "Exhale for 8..."],
    "duration_minutes": 5,
    "targetEmotions": ["ANXIETY", "FEAR"],
    "targetSubEmotions": ["panic", "physical_anxiety"],
    "effectiveness": 0.82,
    "score_reasons": ["semantic match", "targets racing_thoughts", "user rated 5 stars previously"]
  },
  "alternative_techniques": [...],
  "technique_selection_emotion": "anxiety",
  "technique_selection_intensity": 0.75
}
```

---

### 2.3 Memory & Personalization System

**Implementation files**:
- `mental_health_wellness/src/mental_health_wellness/memory/pgvector_store.py`
- `mental_health_wellness/src/mental_health_wellness/memory/memory_builder.py`

The system maintains three layers of personalized memory that persist across sessions:

#### Layer 1 — Explicit User Facts (`UserFact` table)
Stable knowledge extracted from conversations: preferences, identity, goals, patterns.
Examples:
- "Prefers grounding exercises over breathing exercises"
- "Has a history of social anxiety in presentations"
- "Currently in final semester, high academic pressure"
- "Finds cognitive reframing more effective than physical exercises"

These are extracted by a background LLM task after each session and stored as individual fact records. In anonymous mode, this extraction is skipped entirely.

#### Layer 2 — Session Summaries (`SessionSummary` table)
After each session, a background task generates a chapter-style narrative summary of what was discussed, the emotional arc, and which techniques were used. These summaries are embedded (MiniLM-L6-v2) and stored in pgvector.

When future messages reference past topics ("like I mentioned last week about my exam"), the system retrieves the most semantically relevant summaries and injects them into the LLM context — enabling genuine cross-session continuity without context window bloat.

#### Layer 3 — Sliding Window (Current Session)
The last 6 messages of the current session are always in context (synchronous, no DB lookup needed).

#### Smart Injection Logic (`build_full_memory_context`):
```
User asks broad history ("what did we talk about?")
    → Inject session summaries (narrative context)

User asks specific topic ("my breathing exercise last week")
    → Inject top-3 semantically similar past turns (precise recall)

Both cases:
    → End with: "Use above as context. Do not repeat verbatim. Only reference if directly relevant."
```

#### Technique Outcome Tracking:
Each time a technique is delivered and the user rates it, a `TechniqueOutcome` record is created:
- Pre-recommendation intensity vs. post-recommendation intensity
- User effectiveness rating (0-1 normalized from 1-5 stars)
- Free-text feedback
- Session ID (for longitudinal analysis)

This data feeds back into the recommendation pipeline's personal history adjustments on future visits.

---

## Objective 3 — HIPAA & GDPR Compliance

**Status: FULLY IMPLEMENTED** (see full detail in `objective_three.md`)

### GDPR Controls Implemented

| Control | Article | Implementation |
|---|---|---|
| Lawful basis & explicit consent | Art. 6 & Art. 9 | `ConsentRecord` table, 7 consent scopes, `POST /api/consent` |
| Right of Access (data export) | Art. 15 | `GET /api/user/{id}/data-export` — structured JSON export |
| Right to Erasure | Art. 17 | Cascade deletes, `DataSubjectRequest` tracker, pgvector purge |
| Audit logging | Art. 30 | `AuditEvent` table with HMAC-SHA256 pseudonymization |
| Data retention enforcement | Art. 5(1)(e) | `DataRetentionPolicy` table + background cleanup job (6 hrs) |
| Data minimization | Art. 5(1)(b)(c) | Minimal schema design + purpose-limited processing |
| Anonymous Mode | Art. 5 | `anonymousMode` flag skips pgvector writes and session summaries |

### HIPAA Controls Implemented

| Control | Safeguard | Implementation |
|---|---|---|
| Access controls | § 164.312(a)(1) | JWT auth + session verification + per-user query scoping |
| Password security | § 164.312(d) | bcrypt (work factor 12) |
| Encryption | § 164.312(a)(2)(iv) | TLS in transit, AES-256 at rest (Supabase), HMAC pseudonymization |
| Audit controls | § 164.312(b) | Full AuditEvent system with PHI sensitivity tagging |
| Transmission security | § 164.312(e)(1) | CORS whitelist, strict security headers (HSTS, X-Frame, CSP) |
| Rate limiting | § 164.308(a)(3) | slowapi (120/min default, 60/min chat, 10/min auth) |
| Breach detection | § 164.308(a)(6) | `scan_for_breach_indicators()` — 4-rule AuditEvent anomaly scanner |

### Proactive Clinical Monitoring
`ProactiveNotification` table stores alerts generated by `services/proactive_monitor.py`:
- Gradual mood decline (7-session trend)
- Repeated high-anxiety spikes (3+ in last 5 entries)
- Disengagement risk (3+ days without check-in)
- Persistent negative mood (80%+ negative in last 10 logs)
- Crisis escalation pattern (2+ crisis events in 7 days)

---

## Additional Features (Beyond the Three Objectives)

---

### Feature 1 — LangGraph 5-Node Pipeline

**File**: `mental_health_wellness/src/mental_health_wellness/agent/graph.py`

SentiMind's backend is structured as a deterministic LangGraph `StateGraph`. The graph is compiled once at startup (no per-request overhead). Each node contributes specialized processing, and all nodes write to a shared state dictionary that flows through the pipeline.

```
User Message
    │
    ▼
[parallel_intake]           ← 4 tasks run concurrently (asyncio.gather)
    │  ├─ Crisis pre-screen
    │  ├─ Mood analyzer (text emotion)
    │  ├─ Intent pre-check
    │  └─ Context prefetch (DB)
    │
    ▼
[analysis_and_planning]     ← emotion fusion + clinical analysis + strategy
    │  ├─ Emotion fusion (text + voice)
    │  ├─ Trend analyzer (improving / worsening / stable)
    │  ├─ Conversation planner (next strategy)
    │  ├─ Behavioral activation check
    │  └─ Cognitive distortion detection
    │
    ▼
[response_pipeline]         ← technique selection + role selection
    │  ├─ Technique selector (semantic ranking + safety)
    │  └─ Role selector (friend / coach / trainer / crisis_support)
    │
    ▼
[optimized_response_generator]  ← single Gemini LLM call (streaming)
    │  └─ Generates response with full clinical context injected
    │
    ▼
[parallel_persist]          ← fire-and-forget background tasks
       ├─ Profile update
       ├─ Session saver (message history, emotion snapshots)
       └─ Outcome tracker
```

**Pre-Graph Short-Circuits** (before LangGraph even runs):
- Deterministic crisis keyword check (regex, < 50ms) → hardcoded safety response
- Casual chitchat detection → single fast 8B LLM call (< 1.5s), skip full pipeline

---

### Feature 2 — Crisis Detection & Emergency Response

**Files**: `nodes/crisis_handler.py`, `llm/llm_classifier.py`

When crisis is detected (either by regex gate or LLM), the system:
1. Generates an LLM-crafted empathic response (not a robotic template)
2. Sends an enriched WhatsApp alert via Twilio to the user's saved emergency contacts (if consent was granted)

Alert payload includes:
- User's current emotion, sentiment, intensity
- The message that triggered the alert (redacted of PII)
- Acoustic signals: `distress_index`, `pause_density`, `voice_text_conflict` (if voice was used)
- Session ID for clinical follow-up

A deduplication guard prevents re-sending the same crisis alert within a single session.

Post-crisis safety check: After a crisis detection, the user must pass a text-based safety check before sending their next regular message. This state persists across page reloads via `localStorage`.

---

### Feature 3 — Intent Classification (11+ Categories)

**File**: `llm/llm_classifier.py`

Every message is classified by intent to determine the appropriate pipeline route:

| Intent | Response Strategy |
|---|---|
| `therapeutic` | Full clinical pipeline (emotion fusion + technique recommendation) |
| `crisis_signal` | Escalate to crisis handler |
| `technique_request` | User explicitly asked for an exercise |
| `technique_follow_up_accept` | User accepted a suggested technique |
| `technique_follow_up_reject` | User declined a technique |
| `positive_feedback` | User reported feeling better |
| `memory_query` | User asking about past sessions |
| `contextual_followup` | Low-signal follow-up ("yes", "ok") — inherits anchor |
| `chitchat` | Casual conversation — lightweight path |
| `gratitude` | User expressing thanks |
| `information_request` | User asking factual question |

---

### Feature 4 — Cognitive Distortion Detection

**File**: `llm/llm_classifier.py`

8 cognitive distortion types are detected per message using a specialized Gemini prompt:

| Distortion | Example |
|---|---|
| Catastrophizing | "If I fail this exam my life is over" |
| Black-and-White Thinking | "I'm either perfect or a total failure" |
| Overgeneralization | "I always mess everything up" |
| Mind Reading | "Everyone thinks I'm stupid" |
| Fortune Telling | "I know I'm going to fail tomorrow" |
| Emotional Reasoning | "I feel worthless so I must be worthless" |
| Should Statements | "I should be able to handle this" |
| Labeling | "I'm a loser" |

Detected distortions are included in the response generator's context so the LLM can gently challenge them using evidence-based CBT reframing.

---

### Feature 5 — Clinical Severity Scoring

**File**: `llm/llm_classifier.py`

Two validated clinical instruments are scored automatically from the user's message content:

**PHQ-9 (Patient Health Questionnaire)** — Depression severity, 0–27:
- Minimal (0–4), Mild (5–9), Moderate (10–14), Moderately Severe (15–19), Severe (20–27)
- Used to gate technique selection (some techniques are not appropriate for severe depression)

**GAD-7 (Generalized Anxiety Disorder Scale)** — Anxiety severity, 0–21:
- Minimal (0–4), Mild (5–9), Moderate (10–14), Severe (15–21)
- Used alongside PHQ-9 for clinical routing decisions

These scores are stored in the pipeline state and influence both technique filtering and the clinical tone of the LLM's response.

---

### Feature 6 — Conversation Planner (Strategy Engine)

**File**: `nodes/analysis_and_planning.py`

After emotion fusion, a planner node determines the conversational strategy for this turn:

| Strategy | When Used | Effect |
|---|---|---|
| `validate_only` | First disclosure, high distress | Respond with empathy only — no exercise |
| `ask_question` | Insufficient context (< 0.65 score) | Gather more clinical information |
| `encourage_reflection` | Mild distress, user is processing | Reflective prompts to deepen insight |
| `suggest_technique` | User is ready and the emotion is targetable | Full technique recommendation pipeline runs |
| `no_action` | Chitchat, gratitude, factual questions | Simple conversational response |

The planner also sets:
- `context_sufficiency_score`: How well the system understands the user's situation (0–1)
- `conversation_depth`: Number of therapeutic turns in this session
- `active_therapeutic_thread`: Whether there is an ongoing clinical topic being explored

---

### Feature 7 — Role Adaptation System

**File**: `nodes/response_pipeline.py`

The response generator adopts different conversational roles depending on the situation:

| Role | When Selected | Characteristics |
|---|---|---|
| `friend` | Light/casual emotional support | Warm, informal, supportive |
| `coach` | Goal-oriented, technique-active | Encouraging, structured, action-focused |
| `trainer` | Exercise delivery mode | Step-by-step instructional, pacing-aware |
| `crisis_support` | Crisis detected | Calm, non-judgmental, safety-focused |

---

### Feature 8 — Dashboard Analytics

**Files**: `services/dashboard_analytics.py`, `prisma/schema.prisma`

A dedicated analytics service computes user-level insights on request:

| Metric Category | Data Points |
|---|---|
| Session statistics | Total sessions, total messages, last session date |
| Mood trends | Average mood rating, emotion distribution, volatility score |
| Streak tracking | Current check-in streak, longest streak ever |
| Technique outcomes | Techniques used, average effectiveness per technique, user ratings |
| Emotion patterns | Most common emotion, sub-emotion distribution, symptom frequency |
| Trajectory | Improving / worsening / stable mood trend over time |
| Voice insights | Voice tone patterns, voice vs. text emotion agreement rate |
| Long-term outcomes | PHQ-9 / GAD-7 trajectory across sessions |

The frontend dashboard visualizes these as charts and cards, allowing users to understand their mental health patterns over time.

---

### Feature 9 — Session Summarization

**File**: `mental_health_wellness/src/mental_health_wellness/memory/session_summarizer.py`

After each session ends (or after sufficient turns), a background LangGraph task generates a structured summary:

- **What was discussed**: Main emotional topics, key concerns raised
- **Emotional arc**: How the user's state evolved through the session
- **Techniques delivered**: Which exercises were used and how the user responded
- **Key insights**: Notable observations for future sessions

Summaries are stored in the `SessionSummary` table AND embedded into pgvector. Future sessions can retrieve them semantically, enabling the AI to reference past conversations naturally and accurately without storing everything in a growing prompt.

---

### Feature 10 — Real-Time SSE Streaming

**Files**: `api/routes/chat.py` (backend), `frontend/src/hooks/useStream.ts` (frontend)

Responses are streamed token-by-token using Server-Sent Events (SSE):

**Backend**: FastAPI `StreamingResponse` yields `data: {"type": "token", "content": "..."}` events as Gemini generates them. A final `data: {"type": "done", "metadata": {...}}` event delivers all clinical metadata (emotion, technique, session ID) when generation completes.

**Frontend**: `useStream.ts` processes the event stream:
- Buffers tokens in batches of 8 before rendering (smooth animation)
- 15ms render delay between batches (human-like typing effect)
- Displays a blinking cursor in the streaming message bubble
- On `done` event: applies emotion metadata badges to the user's preceding message
- Suppresses "Thinking" indicator as soon as the first streaming message appears

---

### Feature 11 — Voice-Enabled Chat

**Files**: `api/routes/chat.py`, `pipeline/voice_preprocessing.py`

Users can send voice messages by recording audio in the browser:
1. Browser captures audio as base64 WebM/WAV
2. Backend decodes, writes to temp file
3. Gemini transcribes and analyzes vocal delivery
4. Transcript is used as the message text
5. Voice features (emotion, distress, acoustic_features) are passed into the pipeline alongside the text
6. Both modalities enter the fusion algorithm (Case 2 or Case 0)
7. Temp file is deleted after processing (no audio storage)

---

### Feature 12 — Psychometric Profile Tracking

**File**: `nodes/response_pipeline.py` (profile updater node)

A `PsychologicalProfile` record is maintained per user, updated after each session:
- **PHQ-9 trajectory**: Depression score history over time
- **GAD-7 trajectory**: Anxiety score history over time
- **Dominant emotion patterns**: What emotions dominate across sessions
- **Cognitive distortion frequency**: Which distortions appear repeatedly
- **Behavioral pattern tracking**: Recurring behaviors (avoidance, rumination, isolation)

This profile informs long-term clinical trend analysis shown in the dashboard.

---

### Feature 13 — Post-Crisis Safety Check Flow

**File**: `frontend/src/lib/crisisSafety.ts`, `frontend/src/hooks/useStream.ts`

After a crisis event is detected:
1. A safety check flag is stored in `localStorage` (persists across page reloads)
2. The user's next message is intercepted and classified (safe / in_danger / uncertain)
3. If "safe": the flag is cleared and normal chat resumes
4. If "danger" or "uncertain": a local empathy prompt is shown and the flag remains active

This ensures that a user who closes and re-opens the app in a vulnerable state is still met with appropriate care.

---

### Feature 14 — Behavioral Activation Detection

**File**: `nodes/analysis_and_planning.py`

The pipeline detects behavioral activation opportunities — moments where engaging in a positive activity would break a cycle of avoidance or low motivation:
- Detected from behavioral signals: withdrawal, social isolation, loss of interest
- Triggers `behavioral_activation_opportunity` flag in state
- Response generator uses this to naturally weave in an activity suggestion alongside empathy

---

## Summary Table

| Objective / Feature | Implementation Location | Status |
|---|---|---|
| **Objective 1: Emotion Detection** | `llm/llm_classifier.py`, `pipeline/emotion_fusion_node.py`, `voice/acoustic_features.py` | COMPLETE |
| **Objective 2: Exercise Recommendation** | `pipeline/technique_selector_node.py`, `memory/pgvector_store.py`, `prisma/schema.prisma` | COMPLETE |
| **Objective 3: HIPAA & GDPR** | `security/compliance.py`, `api/routes/`, `prisma/schema.prisma` | COMPLETE |
| LangGraph 5-node pipeline | `agent/graph.py`, `nodes/__init__.py` | COMPLETE |
| Crisis detection + alerts | `nodes/crisis_handler.py`, `llm/llm_classifier.py` | COMPLETE |
| Intent classification | `llm/llm_classifier.py` | COMPLETE |
| Cognitive distortion detection | `llm/llm_classifier.py` | COMPLETE |
| Clinical severity (PHQ-9, GAD-7) | `llm/llm_classifier.py` | COMPLETE |
| Conversation strategy planner | `nodes/analysis_and_planning.py` | COMPLETE |
| Role adaptation | `nodes/response_pipeline.py` | COMPLETE |
| Dashboard analytics | `services/dashboard_analytics.py` | COMPLETE |
| Session summarization | `memory/session_summarizer.py` | COMPLETE |
| SSE real-time streaming | `api/routes/chat.py`, `hooks/useStream.ts` | COMPLETE |
| Voice-enabled chat | `pipeline/voice_preprocessing.py` | COMPLETE |
| Psychometric profile tracking | `nodes/response_pipeline.py` | COMPLETE |
| Post-crisis safety check | `lib/crisisSafety.ts`, `hooks/useStream.ts` | COMPLETE |
| Behavioral activation detection | `nodes/analysis_and_planning.py` | COMPLETE |
| Proactive clinical monitoring | `services/proactive_monitor.py` | COMPLETE |

---

*Document generated: 2026-06-19*  
*All three FYP objectives fully implemented and operational*
