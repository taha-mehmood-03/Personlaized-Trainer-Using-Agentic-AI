# SentiMind — Dashboard Analytics & Glossary (FYP Reference)

**Project**: SentiMind — AI-Powered Personalized Mental Health & Wellness Platform
**Student**: Taha Mehmood
**Purpose**: Plain-language reference for the three FYP objectives, every dashboard analytic, and every technical/clinical/compliance term used in the system. Written for FYP defense preparation.

---

## Table of Contents
1. The Three FYP Objectives (meaning + implementation)
2. Emotion & Voice Terms
3. Clinical & Psychological Terms
4. The Two-Level Improvement Model
5. Dashboard Analytics — every card explained
6. GDPR Controls (every one)
7. HIPAA Safeguards (every one)
8. Proactive Clinical Monitoring

---

## 1. The Three FYP Objectives

### Objective 1 — Detect & Interpret Emotional States via Multimodal Fusion
**Meaning:** Determine what the user actually feels from their text AND voice — not just the words but the tone — and reconcile the two when they conflict.

**Implementation (3 layers):**
1. **Text emotion (LLM)** — `llm/llm_classifier.py`: Gemini (temperature 0.0) returns core emotion (8 classes), `primary_sub_emotion`, intensity, symptoms, behaviors, contexts, PHQ-9/GAD-7 scoring, and a 3-step crisis check. A regex safety net runs first (<50ms) for explicit self-harm language.
2. **Voice (DSP + LLM)** — `voice/__init__.py`: Praat/librosa compute deterministic acoustics (F0, jitter, shimmer, HNR, pause density) → `acoustic_distress_proxy`. Gemini separately analyzes the audio holistically. The prompt instructs it to classify by the VOICE, not the words, when they conflict (e.g. crying voice saying "I'm fine").
3. **Fusion** — `pipeline/emotion_fusion_node.py`: Combines text + voice in 3 cases (voice-authoritative / text-only / weighted blend) and runs gap-based **masking detection** (`possible_masking`). Maintains `peak_distress_intensity` as a conversation anchor.

### Objective 2 — Personalized Mental Health Exercise Recommendation
**Meaning:** Pick the right exercise for the user's current state, history, and past feedback — delivered at the right moment.

**Implementation:** `pipeline/technique_selector_node.py`:
- **Readiness gates** — consent, conversation strategy, route, context sufficiency (LLM-signal-based).
- **Semantic ranking** — techniques embedded with MiniLM-L6-v2 in pgvector (HNSW index), matched against a rich clinical query (emotion + symptoms + contexts + PHQ/GAD).
- **Personalization** — boosts/penalties from `UserTechniqueRating` history (≥4★ → +2.0, ≤2★ → −4.0, recently used → −1.2).
- **Clinical safety filter** — contraindicated flags, PHQ-9 range, severity.
- **Behaviors:** anti-repetition (won't re-show same exercise, acknowledges "same exercise applies here too"), immediate-regulation→complement flow (regulation first; complement only when there is genuine situational/cognitive context), 3-layer cross-session memory.

### Objective 3 — HIPAA & GDPR Compliance
**Meaning:** Handle clinical/PHI data lawfully — consent, access, erasure, audit, retention, encryption.
**Implementation:** See sections 6 & 7 below.

---

## 2. Emotion & Voice Terms

### Valence
How *positive or negative* an emotion feels (0–1). 0 = very negative, 0.5 = neutral, 1 = very positive. "I got the job!" ≈ 0.9; "I failed again" ≈ 0.2.

### Arousal
How *activated/energized* the emotion is (0–1) — separate from positive/negative. 0 = calm/flat/numb; 1 = highly activated (panic, rage, excitement).

**Why both matter (they pinpoint the emotion together):**
- High arousal + low valence = anxiety/anger (activated AND negative)
- Low arousal + low valence = depression (drained AND negative)
- High arousal + high valence = excitement

A flat, low-arousal voice claiming "I'm fine" (positive words) is a red flag — energy doesn't match words.

### Acoustic (voice physics) measures — computed by Praat/librosa, pure math, no AI
| Term | Plain meaning | Signals |
|---|---|---|
| **F0 / Pitch** | How high/low the voice sounds | Shaky high = anxiety; flat low = depression |
| **Jitter** | Cycle-to-cycle pitch wobble | Vocal tremor = physiological stress |
| **Shimmer** | Loudness wobble | Amplitude instability = emotional dysregulation |
| **HNR** (harmonics-to-noise ratio) | How clean vs raspy/strained | Low = strained, tense voice |
| **MFCCs** | 13-number voice-timbre fingerprint | Emotional coloring of the voice |
| **Pause density** | % of silence | High = hesitancy, withdrawal, heaviness |
| **Speech rate** | How fast they talk | Fast = anxiety; slow = depression |

**acoustic_distress_proxy (0–1):** an objective physiological distress score from these signals, independent of the words. Lets the system catch "I'm fine" said in a trembling voice.

### possible_masking
A flag set when the voice/acoustic distress contradicts positive words — the user may be hiding how they feel. The response then gently creates space instead of mirroring the positive words.

---

## 3. Clinical & Psychological Terms

### PHQ-9 (depression screen, 0–27)
A standard clinical questionnaire (9 items, each 0–3 by frequency). The system *infers* the score from conversation.
0–4 minimal · 5–9 mild · 10–14 moderate · 15–19 moderately severe · 20–27 severe.

### GAD-7 (anxiety screen, 0–21)
The anxiety equivalent (7 items): nervousness, uncontrollable worry, restlessness, irritability, dread, etc.
0–4 minimal · 5–9 mild · 10–14 moderate · 15–21 severe.

> In SentiMind the **severity label always derives from the numeric score** — it can never show "SEVERE" next to a score of 2.

### Resilience (0–1, shown as %)
How well the user *bounces back* from hard moments and recovers between distressing events. High = recovers quickly / uses coping skills; low = distress lingers. Computed in the psychological profile from recovery patterns and technique effectiveness.

### Distress baseline
The user's *typical/resting* distress level over time — their "normal," so the system knows whether today is unusually bad **for them**.

### Emotional volatility
How up-and-down the mood is. High = big swings (unstable); low = steady. Affects pacing.

### Coping style
Pattern of dealing with stress: `avoidant`, `proactive`, or `mixed`. Avoidant copers get validation first; proactive copers get exercises sooner.

### Intervention readiness
Combined score (reflection depth + technique acceptance + low distress) estimating whether the user is ready to act on a technique vs. needs more validation.

### Adherence rate
% of started/offered exercises the user actually **completes**. Low = not finishing (maybe too long/hard).

### Cognitive distortion
A thinking error (irrational thought pattern). 8 types detected, e.g.:
- **Catastrophizing** — "I'll fail and my life is over"
- **Black-and-white thinking** — "I'm a total failure"
- **Mind-reading** — "everyone thinks I'm stupid"

Guides exercise choice (catastrophizing → Thought Record / Decatastrophizing).

---

## 4. The Two-Level Improvement Model

The system answers two DIFFERENT questions with two DIFFERENT signals:

| Question | Signal used | Why |
|---|---|---|
| "Did this exercise help **right now**?" (within-session) | **Emotional intensity** before→after the technique | PHQ-9/GAD-7 measure a 2-week window; they shouldn't swing in one chat |
| "Am I improving **over weeks**?" (cross-session) | **PHQ-9/GAD-7** per-session baselines compared over time | This is what these instruments are designed for |

- **Within-session** is computed by the OUTCOME_TRACKER: it snapshots intensity at delivery, then again on the user's reaction, and computes effectiveness = (before − after) / before.
- **Cross-session** compares each session's *disclosure-phase peak* (pre-intervention baseline) to the first session's baseline — falling baselines = genuine improvement.

---

## 5. Dashboard Analytics — Every Card Explained

Each card maps to a section of the `build_user_dashboard` payload (`services/dashboard_analytics.py`).

| Card / Section | What it shows | Payload source |
|---|---|---|
| **Overview / StatCards** | Total sessions, messages, check-ins, current & longest streak, avg mood, most-common emotion | `overview` |
| **MoodChart** | Mood score over time + trend (improving/declining/stable) | `mood.timeline`, `mood.trend` |
| **EmotionDistribution** | How often each core emotion occurred | `mood.distribution` |
| **SignalBreakdown** | Top sub-emotions, symptoms, behaviors, contexts (frequencies) | `mood.top_symptoms/behaviors/contexts/sub_emotions` |
| **PsychologicalProfileCard** | Coping style, resilience %, anxiety baseline, AI insight, top distortions/triggers | `personalization.profile` |
| **ClinicalValidityCard** | PHQ-9/GAD-7 before→after per session, severity badge, within-session delta, cross-session "improving vs baseline" | `clinical` |
| **TechniqueOutcomeChart** | Intensity before vs after each technique → effectiveness % | `techniques.outcomes` |
| **OutcomeRadar / TopTechniques** | Ranked techniques by composite score (usage × effectiveness × rating) | `techniques.ranked` |
| **ImprovementAnalysisPanel** | Long-term trajectory: mood trend, volatility, technique effectiveness, adherence, resilience, composite score | `long_term_outcomes` |
| **VoiceInsightsCard** | Dominant voice emotion, avg arousal/valence/confidence, avg acoustic distress | `voice_insights` |
| **SessionHistoryTable** | Recent sessions with emotion, score trajectory, techniques | `sessions.recent` |
| **SuggestionPanel** | Proactive AI suggestions derived from analytics | `suggestions` |
| **data_quality (meta)** | How many logs underpin the analytics (confidence gating) | `data_quality` |

---

## 6. GDPR Controls (EU data-protection law)

GDPR protects personal data; each "Article" (Art.) is a specific legal requirement.

| Control | Article | Plain meaning | Implementation |
|---|---|---|---|
| **Consent** | Art. 6 & 9 | User must agree before processing health data | `ConsentRecord` table, 7 consent scopes, `POST /api/consent` |
| **Right of Access** | Art. 15 | User can get a copy of all their data | `GET /api/user/{id}/data-export` → JSON export |
| **Right to Erasure** | Art. 17 | User can demand full deletion | Cascade deletes + pgvector purge + `DataSubjectRequest` tracker |
| **Audit logging** | Art. 30 | Record who accessed what | `AuditEvent` table; identities pseudonymized via HMAC-SHA256 |
| **Retention limits** | Art. 5(1)(e) | Don't keep data longer than needed | `DataRetentionPolicy` + cleanup job every 6 hrs |
| **Data minimization** | Art. 5(1)(b)(c) | Only collect what's needed | Minimal schema, purpose-limited processing |
| **Anonymous Mode** | Art. 5 | Use the app without tracking | `anonymousMode` flag skips pgvector writes & session summaries |

---

## 7. HIPAA Safeguards (US health-data law)

HIPAA protects PHI (Protected Health Information). Each "§" is a regulation section.

| Safeguard | Section | Plain meaning | Implementation |
|---|---|---|---|
| **Access controls** | §164.312(a)(1) | Only the right person sees their data | JWT auth + session verification + per-user query scoping |
| **Password security** | §164.312(d) | Passwords stored safely | bcrypt (work factor 12) |
| **Encryption** | §164.312(a)(2)(iv) | Data scrambled in transit & at rest | TLS (transit), AES-256 (at rest, Supabase), HMAC pseudonymization |
| **Audit controls** | §164.312(b) | Track access to health data | `AuditEvent` with PHI sensitivity tagging |
| **Transmission security** | §164.312(e)(1) | Safe data transfer | CORS whitelist + security headers (HSTS, X-Frame-Options, CSP) |
| **Rate limiting** | §164.308(a)(3) | Prevent abuse/scraping | slowapi: 120/min default, 60/min chat, 10/min auth |
| **Breach detection** | §164.308(a)(6) | Notice anomalies | `scan_for_breach_indicators()` — 4-rule audit-log scanner |

**Key compliance terms:**
- **PHI** — Protected Health Information (health data tied to a person).
- **Pseudonymization** — replacing identities with a consistent hash; logs stay useful but don't expose who the person is.
- **HMAC-SHA256** — a one-way cryptographic hash; cannot be reversed to the original ID.
- **Cascade delete** — deleting a user automatically deletes all linked records (messages, moods, etc.).

---

## 8. Proactive Clinical Monitoring

Background alerts (`ProactiveNotification`, `services/proactive_monitor.py`):
- **Gradual mood decline** — 7-session downward trend
- **Anxiety spikes** — 3+ high-anxiety entries in last 5
- **Disengagement risk** — 3+ days without check-in
- **Persistent negative mood** — 80%+ negative in last 10 logs
- **Crisis escalation** — 2+ crisis events in 7 days

---

## Crisis Resources (Pakistan)

Crisis responses use real Pakistan emergency organizations (from `tools/crisis_tools.py`), injected into the crisis prompt so the LLM never invents US numbers:
- Umang Pakistan Mental Health Helpline: +92-311-7786264
- Rescue / Ambulance: 1122
- Police Emergency: 15
- Edhi Ambulance: 115
