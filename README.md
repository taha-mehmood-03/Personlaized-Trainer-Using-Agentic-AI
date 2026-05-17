<div align="center">

<img src="https://img.shields.io/badge/version-9.0-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/python-3.10+-6366f1?style=for-the-badge&logo=python&logoColor=white&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/LangGraph-0.2+-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/FastAPI-0.109+-6366f1?style=for-the-badge&logo=fastapi&logoColor=white&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/license-MIT-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/Voice-Multimodal_Fusion-22c55e?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/ASR-Deepgram_Nova--2-22c55e?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/Smart_Gate-Pre--Graph_Router-f59e0b?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/Clinical-PHQ--9_+_GAD--7-ef4444?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/latency-v8.0_optimized-22c55e?style=for-the-badge&labelColor=0f0f1a" />

<br /><br />

```
███████╗███████╗███╗   ██╗████████╗██╗███╗   ███╗██╗███╗   ██╗██████╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗ ████║██║████╗  ██║██╔══██╗
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔████╔██║██║██╔██╗ ██║██║  ██║
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╔╝██║██║██║╚██╗██║██║  ██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝
```

### **Deterministic Hybrid Mental Health Agent — v9.0 (Priority Routing + Clinical Severity Validation + DB-First Exercises + Multimodal Voice Fusion)**

*A production-grade AI emotional support system — 7-route priority gate, **PHQ-9/GAD-7 clinical severity assessment**, severity-gated DB exercises, 5 fused nodes, 3 parallel tiers, true token streaming, multimodal voice + text emotion fusion*

<br />

[**Architecture**](#-architecture) · [**Voice Pipeline**](#-voice-pipeline-v70) · [**Features**](#-key-features) · [**Pipeline**](#-pipeline-stages) · [**Tech Stack**](#-tech-stack) · [**API**](#-api-endpoints) · [**Setup**](#-setup--installation)

</div>

---

## 🧭 What is SentiMind?

SentiMind is a **clinically-informed, multimodal AI mental health agent** built on [LangGraph](https://github.com/langchain-ai/langgraph). It uses semantic LLM understanding for all decision-making and fuses **text emotion** with **real acoustic voice features** (pitch, arousal, distress index) to detect emotion masking — where a user's words say one thing but their voice reveals another.

> **The core problem it solves:** Most mental health chatbots rely purely on text. SentiMind adds a full voice analysis layer so it can catch when a user says "I'm fine" in a sad voice and respond to their *true* emotional state.

---

## ⚡ Core Philosophy (v9.0)

**PRIORITY ROUTING + CLINICAL SEVERITY VALIDATION + DATABASE-FIRST EXERCISES**

```
           USER MESSAGE
                 │
        ┌────────▼────────┐
        │ SMART GATE v8.7  │  llama-3.1-8b semantic router
        │ (PRE-GRAPH)      │  LLM-based priority logic
        │ ~400ms latency   │  (NO keywords)
        └────────┬────────┘
                 │
    ┌────────────┼────────────────────────────────────────┐
    │                                                     │
    ▼ Route 1                                             │
EXPLICIT EXERCISE REQUEST?                                │
"can i try timeline journal"                              │
    │                                                     │
    ├─→ ACCEPT_TECHNIQUE ✅                               │
    │   • run_full_pipeline = FALSE                       │
    │   • Fetch exercise_data from DB                     │
    │   • Send steps (from DB, NOT LLM) to sidebar        │
    │   • Skip mood re-analysis → respect user choice     │
    │                                                     │
    ▼ Route 2                                             │
CASUAL CHAT?                                              │
"thanks!" / "hey there"                                   │
    │                                                     │
    ├─→ CHITCHAT ✅                                       │
    │   • run_full_pipeline = FALSE                       │
    │   • Direct response (~600ms)                        │
    │   • Skip therapy nodes                              │
    │                                                     │
    ▼ Route 3                                             │
MEMORY QUERY?                                             │
"what did we discuss last time?"                          │
    │                                                     │
    ├─→ MEMORY_QUERY ✅                                   │
    │   • run_full_pipeline = FALSE                       │
    │   • DB session lookup                               │
    │   • Return history                                  │
    │                                                     │
    ▼ Route 4                                             │
WANT EXERCISE LIST?                                       │
"show me breathing exercises"                             │
    │                                                     │
    ├─→ LIST_TECHNIQUES ✅                                │
    │   • run_full_pipeline = FALSE                       │
    │   • Fetch all exercises from category               │
    │   • Return DB-sourced list                          │
    │                                                     │
    ▼ Route 5                                             │
REJECTING HELP?                                           │
"i don't want exercises"                                  │
    │                                                     │
    ├─→ REJECTION ✅                                      │
    │   • run_full_pipeline = FALSE                       │
    │   • Acknowledge & respect choice                    │
    │                                                     │
    ▼ Route 6                                             │
CRISIS DETECTED?                                          │
"i want to hurt myself"                                   │
    │                                                     │
    ├─→ CRISIS ⚠️                                         │
    │   • run_full_pipeline = TRUE                        │
    │   • Claude 3.5 Sonnet analysis                      │
    │   • Twilio GPS alerts                               │
    │                                                     │
    ▼ Route 7 (DEFAULT)                                   │
EMOTIONAL/VENTING                                         │
"i feel sad" / "im anxious"                               │
    │                                                     │
    └─→ THERAPEUTIC ✅                                    │
        • run_full_pipeline = TRUE                        │
        • FULL 5-node graph pipeline                      │
        • Mood + context analysis                         │
        • Technique recommendation                        │
        • Track feedback/sentiment

KEY v8.7 CHANGES:
✅ LLM-based routing (semantic, not keywords)
✅ Explicit exercise requests BYPASS therapeutic override
✅ User choice RESPECTED (no mood re-analysis after selection)
✅ Database-FIRST: exercise steps ALWAYS from DB
✅ run_full_pipeline flag determines node execution
✅ Session context informs ALL routing decisions

KEY v9.0 CHANGES:
🏥 PHQ-9 + GAD-7 clinical severity assessment on every therapeutic turn
🏥 Severity-gated DB queries (minPhq9/maxPhq9/safeAtSeverity per technique)
🏥 Contraindication filtering (blocks unsafe exercises per clinical indicators)
🏥 ClinicalAssessmentLog for longitudinal severity tracking
🏥 Severity-aware strategy overrides (SEVERE → crisis pathway)
```

| Principle | Implementation |
|-----------|---------------|
| **Priority Routing** | 7-route LLM gate (v8.7) checks explicit requests FIRST |
| **Clinical Validation** | PHQ-9 + GAD-7 in LLM prompt → severity band → DB exercise filter |
| **Database-First** | Exercise steps ALWAYS from DB, NEVER LLM-generated |
| **Severity-Gated Exercises** | Each technique tagged with minPhq9/maxPhq9/safeAtSeverity/contraindicatedFlags |
| **User Choice Respected** | Explicit requests bypass mood re-analysis |
| **LLM Classification** | All routing uses semantic LLM understanding (no keywords) |
| **Multimodal voice** | wav2vec2 emotion + OpenSMILE acoustic features + Whisper ASR |
| **Acoustic Override** | Catches emotion masking (happy words + sad voice → sadness) |
| **Safety by default** | LLM crisis detection + GPS-aware Twilio WhatsApp/SMS alerts |
| **SSE Streaming** | LangGraph true real-time token streaming directly to frontend |
| **Zero ffmpeg** | Browser-side WebM→WAV conversion (Web Audio API) |

---

## 🏗️ Architecture

### Full System Diagram (v8.0)

```text
┌────────────────────────────────────────────────────────────────────┐
│                      USER INPUT (Text or Voice)                    │
└────────────────────────┬───────────────────────────────────────────┘
                         │
          ┌──────────────▼──────────────┐
          │  FRONTEND — ChatInput.tsx   │
          │  • SpeechRecognition API    │
          │  • MediaRecorder (WebM)     │
          │  • Web Audio API decode     │
          │  • Re-encode → 16kHz WAV   │  ← No ffmpeg required
          │  • Send text + WAV base64  │
          └──────────────┬──────────────┘
                         │ POST /api/chat/stream
          ┌──────────────▼──────────────────────────────────────────┐
          │  api_server.py — FastAPI SSE Streaming Endpoint         │
          │  • Decode base64 WAV                                    │
          │  • preprocess_voice_input() → voice_features dict       │
          │  • Inject [Voice Analysis: ...] annotation into message │
          │  • Pass voice_features directly into agent input_state  │
          └──────────────┬──────────────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────────────┐
│  PRE-GRAPH ── PRIORITY ROUTING GATE             ⚡ v8.7            │
│  smart_pipeline_gate() — llama-3.1-8b (~400ms) — 7-ROUTE PRIORITY  │
│                                                                     │
│  PRIORITY ORDER (check FIRST match, STOP):                         │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 1. ACCEPT_TECHNIQUE                         │ User explicitly  │
│  │    "can i try timeline journal?"            │ requests specific│
│  │    → run_full_pipeline=FALSE (bypass)       │ exercise by name │
│  │    → Fetch exercise_data + steps from DB    │                  │
│  │    → Skip mood re-analysis → respect choice │                  │
│  └─────────────────────────────────────────────┘                   │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 2. CHITCHAT                                 │ Casual social    │
│  │    "that's nice" / "how are you?"           │ conversation     │
│  │    → run_full_pipeline=FALSE (skip graph)   │ (≥75% confidence)│
│  │    → Return quick response in ~600ms        │                  │
│  └─────────────────────────────────────────────┘                   │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 3. MEMORY_QUERY                             │ Asking about     │
│  │    "what did we discuss?" / "last time"     │ past sessions    │
│  │    → run_full_pipeline=FALSE (DB query)     │                  │
│  │    → Retrieve & format session history      │                  │
│  └─────────────────────────────────────────────┘                   │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 4. LIST_TECHNIQUES                          │ User wants       │
│  │    "show me exercises" / "what can help?"   │ exercise list    │
│  │    → run_full_pipeline=FALSE (category DB)  │                  │
│  │    → Fetch all techniques from categories   │                  │
│  │    → Return formatted exercise list         │                  │
│  └─────────────────────────────────────────────┘                   │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 5. REJECTION                                │ User declines    │
│  │    "no thanks" / "i don't want help"        │ all support      │
│  │    → run_full_pipeline=FALSE (respect)      │                  │
│  │    → Acknowledge & offer future support     │                  │
│  └─────────────────────────────────────────────┘                   │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 6. CRISIS                                   │ Safety threat    │
│  │    "i want to hurt myself" / "suicidal"     │ detected         │
│  │    → run_full_pipeline=TRUE (full analysis) │                  │
│  │    → Claude 3.5 Sonnet semantic detection   │                  │
│  │    → Twilio GPS alerts                      │                  │
│  └─────────────────────────────────────────────┘                   │
│  ┌─────────────────────────────────────────────┐                   │
│  │ 7. THERAPEUTIC (DEFAULT)                    │ Everything else  │
│  │    User discussing emotions/feedback        │ (mood, anxiety,  │
│  │    → run_full_pipeline=TRUE (FULL PIPELINE) │ feedback, etc.)  │
│  │    → 5-node graph: intake→analysis→response │                  │
│  │    → Cognitive distortion + techniques      │                  │
│  └─────────────────────────────────────────────┘                   │
│                                                                     │
│  KEY v8.7 CHANGES:                                                 │
│  ✅ Explicit exercise requests bypass therapeutic re-analysis       │
│  ✅ User choice respected → no mood re-evaluation after selection   │
│  ✅ Database-first: steps ALWAYS from DB, never LLM-generated      │
│  ✅ run_full_pipeline flag controls node execution (T/F)           │
│  ✅ Session context informs all routing decisions                  │
│                                                                     │
│  LLM DECISION TREE (in classifier prompt):                          │
│  1. User EXPLICITLY NAMES exercise? → accept_technique, skip       │
│  2. Crisis keywords + semantic check? → crisis, full analysis      │
│  3. Asking for list of exercises? → list_techniques, DB fetch      │
│  4. Casual/social tone (≥75% conf)? → chitchat, quick response     │
│  5. Asking about past? → memory_query, session lookup              │
│  6. Explicitly rejecting help? → rejection, acknowledge            │
│  7. Anything else? → therapeutic, run full 5-node pipeline         │
│                                                                     │
└────────────────────────┬───────────────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────────────┐
│  NODE 1 ── PARALLEL INTAKE                        ⚡ 3-WAY ASYNC  │
│  ┌──────────────────┐ ┌──────────────────┐                         │
│  │ Crisis Screener  │ │  Context Loader  │                         │
│  │ claude-3.5-sonnet│ │  DB Context      │                         │
│  └──────────────────┘ └──────────────────┘                         │
│  ┌──────────────────┐ ┌──────────────────────────────────┐         │
│  │  Mood Analyzer   │ │  Intent Prefetch                 │         │
│  │  llama-3.3-70b   │ │  ⏭️ SKIPPED if gate fired       │         │
│  └──────────────────┘ └──────────────────────────────────┘         │
└────────────────────────┬───────────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│  NODE 2 ── ANALYSIS & PLANNING                          🔗 FUSED  │
│  • Emotion Fusion  (text + pre-injected voice_features)            │
│      → Acoustic Override: distress_index > 0.65 → sadness         │
│      → Arousal Override:  arousal > 0.75 → anxiety                │
│      → Pause Boost:       pause_density > 0.40 → +15% intensity   │
│  • Cognitive Distortion (LLM) — SKIPPED for technique_request,    │
│    advice_seeking, chitchat intents (saves 100-300ms per request)  │
│  • Trend Analyzer (DB query — always runs)                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 🏥 Clinical Severity (PHQ-9 + GAD-7 in LLM prompt)  v9.0  │   │
│  │    → severity band → DB exercise filter                    │   │
│  │    → llama-3.3-70b (MODEL_HEAVY) · parallel with above     │   │
│  │    → SKIPPED for chitchat/technique_request (same as above) │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  • Conversation Planner (Phase & Strategy + severity overrides)    │
│  • Behavioral Activation — SKIPPED for no_action/ask_question      │
└────────────────────────┬───────────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│  NODE 3 ── RESPONSE PIPELINE                            🔗 FUSED  │
│  • Technique Selector — severity-gated DB query (v9.0)             │
│      → WHERE minPhq9 <= score AND maxPhq9 >= score                 │
│      → AND safeAtSeverity HAS current_severity                     │
│      → Contraindication filter (exclude flagged exercises)         │
│      → SKIPPED for validate_only/ask_question                      │
│  • Role Selector (Friend / Coach / Trainer / Crisis)               │
└────────────────────────┬───────────────────────────────────────────┘
                         ▼  (tokens stream to browser via SSE)
┌────────────────────────────────────────────────────────────────────┐
│  NODE 4 ── RESPONSE GENERATOR              ✨ TRUE STREAMING ASYNC │
│  • llama-3.3-70b via OpenRouter                                    │
│  • LangGraph astream_events → token-by-token SSE yield             │
└────────────────────────┬───────────────────────────────────────────┘
                         ▼  (fire-and-forget background task)
┌────────────────────────────────────────────────────────────────────┐
│  NODE 5 ── PARALLEL PERSIST                         ⚡ 3-WAY ASYNC │
│  Psych Profile Updater || Session Saver (Prisma) || Outcome Tracker│
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ 🏥 ClinicalLog Writer (v9.0) — saves PHQ-9/GAD-7/severity   │ │
│  │    to ClinicalAssessmentLog table (only when severity>minimal)│ │
│  └───────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🎤 Voice Pipeline (v7.0)

The voice pipeline is fully end-to-end, zero-dependency, and runs entirely across browser + server with no system-level `ffmpeg` installation required.

### Browser → Server Flow

```
[User speaks]
      │
      ├── SpeechRecognition API  →  text transcript
      │
      └── MediaRecorder (WebM/Opus)  →  raw audio blob
              │
              ▼
      Web Audio API (AudioContext.decodeAudioData)
              │
              ▼
      Mix down to mono + resample to 16kHz
              │
              ▼
      Encode as RIFF/WAV (44-byte header + 16-bit PCM)
              │
              ▼
      Base64 → POST /api/chat/stream { message, audio_data }
```

### Server-Side Voice Analysis

```python
# voice/__init__.py — preload_all_voice_models() called at startup

analyze_voice_full(wav_path) runs 3 steps in one pass:
  1. extract_acoustic_features()     # librosa → pitch (F0/pyin), loudness (RMS),
                                     # MFCC (13-dim + delta + delta-delta),
                                     # spectral flux, jitter/shimmer approximation
                                     # → distress_index (composite psychoacoustic score)
                                     # → pause_density  (via voiced-flag from pyin)
                                     # → arousal / valence  (acoustic estimators)

  2. classify_voice_emotion()        # wav2vec2 (r-f/wav2vec-english-speech-emotion-recognition)
                                     # → emotion label + confidence + all_scores

  3. transcribe_audio()              # Deepgram Nova-2 REST API (httpx, no local model)
                                     # → ASR transcript (no ffmpeg, no Whisper download)
```

### Emotion Fusion Rules (emotion_fusion_node.py)

| Condition | Action |
|-----------|--------|
| `voice_confidence ≥ 0.5` | text:voice:acoustic = 50:30:20 blend |
| `voice_confidence < 0.5` | text:voice:acoustic = 70:15:15 blend |
| `distress_index > 0.65` AND text is neutral/joy | **Override → sadness** |
| `arousal > 0.75` AND text is neutral/joy | **Override → anxiety** |
| `pause_density > 0.40` AND intensity < 0.40 | **Boost intensity +15%** |
| Voice + text agree AND `distress_index > 0.5` | **Boost confidence +10%** |

### Psychoacoustic Distress Index

Composite score (0 = healthy, 1 = high distress) based on clinical voice research:

```
distress_index = 0.30 × jitter_norm        (pitch perturbation → vocal tension)
               + 0.25 × shimmer_norm       (amplitude variation → dysregulation)
               + 0.25 × hnr_distress       (low HNR → breathy/rough → depression)
               + 0.10 × pitch_std_norm     (high variability → anxiety)
               + 0.10 × pause_distress     (U-shaped: extremes signal distress)
```

### Model Preloading at Startup

All voice ML models load during server boot (not on first request):

```
[SERVER] Preloading voice ML models (Whisper + wav2vec2 + OpenSMILE)...
[VOICE-PRELOAD] OpenSMILE: ok
[VOICE-PRELOAD] wav2vec2: ok
[VOICE-PRELOAD] Whisper: ok
[SERVER] Voice models ready: ['opensmile', 'wav2vec2', 'whisper']
```

---

## 🧠 Key Features

| Feature | Implementation |
|---------|---------------|
| 🚦 **Priority Routing Gate (v8.7)** | 7-route pre-graph router — accepts explicit exercises, bypasses mood re-analysis |
| 🏥 **Clinical Severity (v9.0)** | PHQ-9 + GAD-7 in LLM prompt → severity band → DB exercise filter |
| 🏥 **Severity-Gated Exercises (v9.0)** | Each technique has minPhq9/maxPhq9/safeAtSeverity/contraindicatedFlags |
| 🏥 **Clinical Logging (v9.0)** | ClinicalAssessmentLog table for longitudinal PHQ-9/GAD-7 tracking |
| 💾 **Database-First Exercises** | Exercise steps fetched from DB (never LLM-generated) |
| 👤 **User Choice Respected** | Explicit exercise requests skip therapeutic override — user intent always honored |
| 🎭 **Multimodal Emotion Detection** | LLM text emotion + wav2vec2 voice emotion + acoustic feature fusion |
| 🔊 **Acoustic Override** | Catches emotion masking (happy words + sad voice → detects sadness) |
| 🧠 **Cognitive Distortion Detection** | LLM semantic analysis — skipped for technique_request/advice_seeking |
| 📋 **Conversation Phase Awareness** | NEUTRAL → VENTING → REFLECTION → SOLUTION → RECOVERY |
| 🧬 **Persistent Psychological Profile** | 9-field user profile with EMA smoothing, updated per session |
| 🎯 **Planner-Gated Technique Selection** | Strategy + readiness + **clinical severity** gate technique delivery |
| 💡 **Behavioral Activation** | Emotion × intensity_band × time-of-day matrix |
| 📈 **Longitudinal Trend Detection** | Linear regression over last 5 MoodLogs, requires ≥3 sessions |
| 🚨 **Crisis Detection** | claude-3.5-sonnet semantic analysis — NO keyword matching |
| 📍 **GPS Crisis Alerts** | Browser geolocation → Twilio WhatsApp/SMS with Google Maps link |
| 👤 **Phase-Aware Role Selection** | Friend / Coach / Trainer / Crisis — considers trend, phase, intensity |
| 🎤 **Browser-Native WAV Encoding** | Web Audio API → 16kHz mono RIFF/WAV, zero system dependencies |
| 📌 **Active Exercise Sidebar** | Left sidebar shows current technique card — works on all screen sizes |

---

## 🏥 Clinical Severity Assessment (v9.0)

### PHQ-9 + GAD-7 in LLM Prompt

Every therapeutic turn runs a **clinical severity check** using the full PHQ-9 (9 items) and GAD-7 (7 items) instruments embedded in the LLM prompt. The LLM scores each item 0-3 based on conversational evidence only — no questionnaire is presented to the user.

```text
┌─────────────────────────────────────────────────────────────────┐
│  User message: "I can't sleep, I feel worthless, nothing       │
│  interests me anymore and I can't concentrate at work"         │
│                                                                 │
│  → LLM Clinical Classifier (llama-3.3-70b, temp=0.0)          │
│                                                                 │
│  PHQ-9 Scoring:                                                 │
│    Q1 (anhedonia)       = 2  ← "nothing interests me"          │
│    Q3 (sleep)           = 2  ← "can't sleep"                   │
│    Q6 (worthlessness)   = 2  ← "feel worthless"                │
│    Q7 (concentration)   = 2  ← "can't concentrate"             │
│    Total: 8/27 → MILD                                           │
│                                                                 │
│  GAD-7 Scoring:                                                 │
│    All items = 0  (no anxiety evidence)                         │
│    Total: 0/21 → MINIMAL                                        │
│                                                                 │
│  Overall Severity: MAX(MILD, MINIMAL) = MILD                    │
│  Clinical Indicators: [anhedonia, sleep_disturbance,            │
│                        worthlessness, concentration]             │
└─────────────────────────────────────────────────────────────────┘
```

### Severity Bands

| PHQ-9 Score | Severity Level | Pipeline Behavior |
|:-----------:|:--------------|:------------------|
| 0-4 | **MINIMAL** | Validate only, no technique push |
| 5-9 | **MILD** | Standard technique selection |
| 10-14 | **MODERATE** | Structured techniques prioritized, professional support mentioned |
| 15-19 | **MODERATELY SEVERE** | Techniques pushed earlier, professional support recommended |
| 20-27 | **SEVERE** | Crisis-adjacent pathway, professional referral in every response |

### Severity-Gated DB Queries

Each technique in the database has clinical fields:

```prisma
model Technique {
  // ...existing fields...
  minPhq9              Int       @default(0)      // min PHQ-9 score appropriate
  maxPhq9              Int       @default(27)     // max PHQ-9 score appropriate  
  safeAtSeverity       String[]  @default(["MINIMAL", "MILD", "MODERATE", "MODERATELY_SEVERE"])
  contraindicatedFlags String[]  @default([])     // e.g. ["suicidal_ideation", "psychomotor"]
}
```

The technique selector builds a WHERE clause:
```sql
WHERE minPhq9 <= {user_phq9} AND maxPhq9 >= {user_phq9}
  AND safeAtSeverity HAS {current_severity}
  AND contraindicatedFlags NOT OVERLAPPING {user_indicators}
```

### Clinical Assessment Log

Severity assessments are persisted per-session for longitudinal tracking:

```prisma
model ClinicalAssessmentLog {
  id           String           @id @default(cuid())
  sessionId    String
  userId       String
  severity     ClinicalSeverity // MINIMAL|MILD|MODERATE|MODERATELY_SEVERE|SEVERE
  phq9Score    Int              // 0-27
  gad7Score    Int              // 0-21
  indicators   String[]         // items scoring >= 2
  confidence   Float            // 0.0-1.0
  justification String?         // LLM reasoning
  assessedAt   DateTime         @default(now())
}
```

---

## 🧠 Priority Routing Gate & Session Context (v8.7)

### How Priority Routing Works (v8.7)

The **Priority Routing Gate** is a pre-graph LLM router that runs **before** the expensive 5-node graph. Unlike v8.0-8.2 which only checked for casual chat, v8.7 implements a **7-route priority system** that intelligently directs messages:

1. **Accept Technique** (Highest Priority)  
   - User explicitly names an exercise: "can i try timeline journal?"
   - Fetches exercise from DB with full details (steps, duration, difficulty)
   - Skips mood analysis → respects user choice
   - `run_full_pipeline=FALSE` (bypasses therapeutic pipeline)
   - Total latency: **~800-1000ms**

2. **Chitchat** (Fast Path)  
   - Casual social conversation: "that's nice!", "how are you?"
   - ≥75% confidence required
   - Returns quick conversational response
   - `run_full_pipeline=FALSE` (skips graph)
   - Total latency: **~600-900ms**

3. **Memory Query** (Context Lookup)  
   - User asking about past sessions: "what did we discuss?"
   - DB retrieves session history
   - `run_full_pipeline=FALSE` (DB-only operation)
   - Total latency: **~500-700ms**

4. **List Techniques** (Exercise Directory)  
   - User requests exercise list: "show me all exercises"
   - DB fetches techniques from multiple categories
   - Returns formatted exercise catalog
   - `run_full_pipeline=FALSE` (DB-only operation)
   - Total latency: **~600-800ms**

5. **Rejection** (User Declines)  
   - User explicitly declining help: "no thanks", "i don't want support"
   - Acknowledges & stores preference
   - `run_full_pipeline=FALSE` (respect user choice)
   - Total latency: **~400-600ms**

6. **Crisis** (Safety First)  
   - Crisis keywords + semantic analysis
   - Runs claude-3.5-sonnet for detailed assessment
   - Triggers Twilio GPS alerts
   - `run_full_pipeline=TRUE` (full emergency protocol)
   - Total latency: **~2-3s** (safety > speed)

7. **Therapeutic** (Default Full Pipeline)  
   - Everything else: mood discussion, emotional support, feedback
   - Runs full 5-node graph: intake → analysis → response
   - Cognitive distortion analysis + technique selection
   - `run_full_pipeline=TRUE` (complete analysis)
   - Total latency: **~2-4s**

### Session Context Integration

The priority router has access to **complete session context**:

```json
{
  "summary": "User struggling with work anxiety",
  "description": "Discussed 4-7-8 breathing technique and exercise routine",
  "facts": [
    {"fact": "Anxious about presentations", "mention_count": 3},
    {"fact": "4-7-8 breathing discussed", "mention_count": 1}
  ]
}
```

This enables the router to detect:
- **Follow-ups**: "That exercise didn't help" → THERAPEUTIC (feedback to suggestion)
- **Continuations**: "The presentation is happening now" → THERAPEUTIC (anxiety continuation)
- **Explicit requests**: "Can I try timeline journal?" → ACCEPT_TECHNIQUE (user choice respected)

### Critical v8.7 Behavior

| Scenario | Route | run_full_pipeline | Behavior |
|----------|-------|------|-----------|
| User says "can i try timeline journal" | accept_technique | FALSE | Fetch from DB, skip mood re-analysis |
| User says "that exercise didn't help" | therapeutic | TRUE | Feedback analysis, try alternative |
| User says "show me exercises" | list_techniques | FALSE | Return exercise catalog |
| User says "that's nice!" | chitchat | FALSE | Quick social response |
| User says "what did we discuss?" | memory_query | FALSE | Session history lookup |
| User says "no thanks" | rejection | FALSE | Acknowledge & respect |
| User says "i want to hurt myself" | crisis | TRUE | Emergency response + alerts |

### Why v8.7 Solves User Choice Problem

**Before v8.7:**
```
User: "can i try timeline journal"
  → Gate accepts, but full therapeutic pipeline re-runs
  → Mood analysis: detects sadness
  → Technique selector: "better option is breathing exercise"
  ❌ WRONG: Overrode user's explicit choice with AI judgment
```

**After v8.7:**
```
User: "can i try timeline journal"
  → Gate detects explicit exercise request
  → route = accept_technique, run_full_pipeline=FALSE
  → Fetches timeline journal from DB
  → Returns directly with DB steps (no LLM generation)
  → Skips mood re-analysis entirely
  ✅ CORRECT: Respects user choice, no therapeutic override
```

---

## 📦 Pipeline Stages (v7.0)

| Stage | Logical Tasks | LLM Provider | Model | Avg Time |
|---|------|-------|----------|----------|
| **Pre-server** | Voice model preload (wav2vec2 only — Deepgram is REST API) | ❌ ML only | — | Startup |
| **API Layer** | WebM decode → WAV → librosa acoustics + wav2vec2 emotion + Deepgram ASR | ❌ ML only | wav2vec2 / librosa + Deepgram Nova-2 | ~200ms |
| **PRE-GRAPH GATE** ⭐ | chitchat router — bypasses graph if casual | ✅ Groq | llama-3.1-8b | ~400ms |
| ↳ *Chitchat fast-path* | single casual LLM reply, no graph at all | ✅ Groq | llama-3.3-70b | **~600ms total** |
| **1** Parallel Intake | crisis ∥ intake ∥ mood (intent SKIPPED if gate fired) | ✅ OpenRouter | claude-3.5-sonnet / llama-3.3-70b | ~800ms |
| **2** Analysis & Planning | emotion fusion + trend + **🏥 clinical severity (PHQ-9/GAD-7)** + planner | ✅ OpenRouter | llama-3.3-70b (clinical) + llama-3.1-8b (distortion) | ~300ms |
| **3** Response Pipeline | technique selector (**severity-gated** DB query) + role selector | ❌ DB only | — | ~100ms |
| **4** Response Generator | Empathetic response with voice-aware + **clinical severity** context | ✅ OpenRouter | llama-3.3-70b | ~1200ms |
| **5** Parallel Persist | profile ∥ DB saver ∥ outcome tracker ∥ **🏥 clinical log** (background) | ❌ | — | 0ms (UI) |
| | **TOTAL — therapeutic (warm, TTFT)** | | | **~2.1s** |
| | **TOTAL — chitchat (warm)** | | | **~600ms** |

---

## 🛠️ Tech Stack

```
Frontend                    Backend                    AI / ML
──────────────────          ───────────────            ────────────────────────
Next.js 14 (App Router)     FastAPI                    llama-3.3-70b (OpenRouter)
React 18 + TypeScript       LangGraph 0.2+             claude-3.5-sonnet (OpenRouter)
Tailwind CSS                LangChain                  llama-3.1-8b (Groq — gate + intent)
Web Audio API               Python 3.10+               wav2vec2 (voice emotion, local)
MediaRecorder API           Uvicorn                    librosa (acoustic features: F0, MFCC)
Lucide React                Pydantic                   Deepgram Nova-2 (ASR — REST API)
                            asyncio / SSE              httpx (Deepgram client)

Data                        DevOps
──────────────────          ──────────────────────
PostgreSQL (Supabase)       CORS middleware
Prisma Client Python        SSE streaming endpoint
                            Twilio (WhatsApp + SMS)
                            bcrypt auth
                            python-dotenv
```

---

## 📊 State Schema

The `MentalHealthState` TypedDict carries all intelligence between nodes:

```python
class MentalHealthState(TypedDict):
    # Core
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str

    # Intake
    is_new_user: bool
    session_count: int
    memory_context: str           # DB Context retrieval
    user_preferences: dict

    # Intent (prefetched in parallel_intake)
    prefetched_intent: Optional[dict]  # {intent, confidence}

    # Mood
    emotion: str                  # anger|fear|sadness|joy|neutral|surprise|disgust|anxiety
    sentiment: str
    intensity: float              # 0.0–1.0
    confidence: float

    # Emotion Fusion
    fused_emotion: str
    fused_intensity: float

    # Voice Analysis (v7.0 — injected pre-graph from api_server)
    voice_features: Optional[dict]      # emotion, confidence, arousal, valence,
                                        # distress_index, pause_density, mfcc_vector
    voice_processed: bool
    voice_distress_index: float
    voice_pause_density: float
    voice_mfcc_vector: list[float]      # 13-dim MFCC means
    has_voice: bool
    audio_file_path: Optional[str]

    # Cognitive Distortion
    distortion_type: Optional[str]
    distortion_confidence: float

    # Trend
    emotional_trend: str          # improving|stable|worsening

    # Conversation Planner
    conversation_strategy: str    # validate_only|suggest_technique|reframe|...
    conversation_phase: str       # neutral|venting|reflection|solution|recovery
    technique_readiness: float

    # Behavioral Activation
    micro_action: Optional[str]
    micro_action_category: Optional[str]

    # Technique Selector
    recommended_technique: dict
    recommended_techniques_by_category: dict
    alternative_techniques: list[dict]

    # Crisis Detection
    crisis_level: str             # low|medium|high
    crisis_detected: bool
    crisis_pre_screened: bool

    # Role & Response
    agent_role: str               # friend|coach|trainer|crisis_support
    final_response: str

    # Psych Profile
    psych_profile: dict

    # Outcome Tracker Baselines
    session_start_emotion: Optional[str]
    session_start_intensity: Optional[float]
    technique_delivery_emotion: Optional[str]
    technique_delivery_intensity: Optional[float]

    # v9.0: Clinical Severity (PHQ-9/GAD-7)
    clinical_severity: str            # minimal|mild|moderate|moderately_severe|severe
    clinical_phq9_score: int          # estimated PHQ-9 total (0-27)
    clinical_gad7_score: int          # estimated GAD-7 total (0-21)
    clinical_indicators: list[str]    # items scoring >= 2 (e.g. ["anhedonia", "sleep_disturbance"])
    clinical_confidence: float        # 0.0-1.0

    # Metadata
    tools_used: list[str]
    processing_time_ms: int
```

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/api/chat/stream` | `POST` | **Primary endpoint** — SSE token streaming + voice fusion + metadata |
| `/api/chat` | `POST` | Non-streaming chat (returns full response) |
| `/api/chat/voice` | `POST` | Dedicated voice endpoint (multipart audio upload) |
| `/api/pipeline/complete` | `POST` | Full pipeline, frontend-compatible response |
| `/api/crisis/send-location` | `POST` | Receive GPS coords → Twilio WhatsApp alert with Maps link |
| `/api/user/create` | `POST` | Create user + auto-create preferences & statistics |
| `/api/user/ensure` | `POST` | Ensure user exists (anonymous footprint if not found) |
| `/api/auth/signup` | `POST` | Sign up with email + bcrypt-hashed password |
| `/api/auth/login` | `POST` | Login with email + password verification |
| `/api/user/{id}/sessions` | `GET` | Sessions with all messages + technique data |
| `/api/session/{id}/messages` | `GET` | All messages from a specific session |
| `/api/session/{id}/rename` | `PATCH` | Rename a chat session title |
| `/api/user/{id}/stats` | `GET` | User statistics (streaks, totals, avg mood) |
| `/api/techniques` | `GET` | Technique catalog, filterable by emotion/category |
| `/api/technique/rate` | `POST` | Submit 1–5 star rating + feedback |
| `/health` | `GET` | DB + agent + voice model readiness check |

### `/api/chat/stream` Request Format

```json
{
  "user_id": "cmod7fnzx000ccri6vl3hle9j",
  "message": "I feel happy today",
  "session_id": "cmomqe82g0001wugmnjnl1qjd",
  "audio_data": "data:audio/wav;base64,UklGRiQA..."
}
```

The `audio_data` field is a **base64-encoded 16kHz mono WAV** produced by the browser's Web Audio API. When present, the server runs the full voice analysis pipeline before the agent graph.

---

## 📁 Repository Structure

```bash
├── frontend/                           # Next.js 14 Web UI
│   └── src/
│       ├── components/chat/
│       │   ├── ChatInput.tsx           # Voice recording + WebM→WAV conversion + send
│       │   ├── ChatLayout.tsx          # Routes audioData through to useStream hook
│       │   └── ChatWindow.tsx
│       ├── hooks/
│       │   └── useStream.ts            # SSE stream reader + crisis GPS trigger
│       └── components/crisis/
│           └── LocationConsentModal.tsx # GPS consent UI
│
└── mental_health_wellness/             # Python AI Backend
    ├── api_server.py                   # FastAPI (UTF-8 forced, voice preload, SSE)
    ├── massive_test_suite.py           # Full automated test suite (all routes)
    ├── prisma/schema.prisma            # 13 models (+ClinicalAssessmentLog)
    └── src/mental_health_wellness/
        ├── agent/
        │   ├── graph.py                # LangGraph 5-node graph + chat_with_agent_streaming
        │   └── state.py                # MentalHealthState TypedDict (voice fields added)
        ├── nodes/
        │   ├── parallel_intake.py      # 4-way concurrent intake
        │   ├── analysis_and_planning.py# Fused: fusion + distortion + trend + clinical severity + planner
        │   ├── emotion_fusion_node.py  # 3-way text+voice+acoustic fusion + overrides
        │   ├── response_pipeline.py    # Fused: technique + role selector
        │   ├── optimized_response_generator.py
        │   ├── crisis_handler.py       # LLM-based crisis + Twilio alerts
        │   ├── parallel_persist.py     # Fire-and-forget: profile + saver + outcome + clinical log
        │   └── voice_preprocessing.py  # preprocess_voice_input() node
        ├── voice/
        │   └── __init__.py             # analyze_voice_full() + preload_all_voice_models()
        │                               # OpenSMILE → librosa → torchaudio → wav2vec2 → Whisper
        ├── llm/
        │   ├── groq_llm.py             # OpenRouter LLM manager
        │   └── llm_classifier.py       # LLM-based intent, crisis, distortion, clinical severity classifiers
        ├── db/                         # Prisma client
        └── memory/                     # Semantic retrieval
```

---

## 🚀 Setup & Installation

### 1. Backend

```bash
cd mental_health_wellness
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Environment Variables (`.env`)

```ini
OPENROUTER_API_KEY="your_openrouter_key"
DATABASE_URL="postgresql://user:password@host:5432/sentimind"
DIRECT_URL="postgresql://user:password@host:5432/sentimind"
TWILIO_ACCOUNT_SID="ACxxxx"
TWILIO_AUTH_TOKEN="xxxx"
TWILIO_WHATSAPP_FROM="whatsapp:+14155238886"
TWILIO_WHATSAPP_TO="whatsapp:+92xxxxxxxxxx"
TWILIO_SMS_TO="+92xxxxxxxxxx"
```

### 3. Database

```bash
prisma generate
prisma db push
```

### 4. Running the Backend

```bash
cd mental_health_wellness
python -m api_server
# Startup sequence:
#   [SERVER] Database connected
#   [SERVER] LLM provider ready
#   [SERVER] Deterministic Agentic Pipeline initialized
#   [VOICE-PRELOAD] Loading wav2vec2 emotion classifier...
#   [VOICE-PRELOAD] wav2vec2: ok
#   [VOICE-PRELOAD] Deepgram: ok
#   [SERVER] All systems ready
```

> **Windows note:** `api_server.py` automatically forces `sys.stdout` to UTF-8 at startup so all emoji log lines render correctly on Windows terminals.

### 5. Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 🏆 Key Architectural Decisions

### Why WebM → WAV in the Browser?

| Approach | Dependencies | Works on Windows? |
|----------|-------------|-------------------|
| Send raw WebM, decode with ffmpeg | Requires `ffmpeg` system install | ❌ Often missing |
| Send raw WebM, decode with pydub | Requires `ffmpeg` + `pydub` | ❌ Same issue |
| **Send WAV (Web Audio API)** | None — pure browser API | ✅ Always works |

The browser's `AudioContext.decodeAudioData()` handles all codec decoding natively (WebM, Opus, OGG), then the audio is re-encoded as standard 16-bit 16kHz mono PCM WAV which `scipy`, `librosa`, and `Whisper` all read without any additional dependencies.

### Why Pre-Inject Voice Features?

Voice features are extracted in `api_server.py` before the LangGraph graph starts. The `voice_features` dict is injected directly into `input_state` so:

- No double audio processing inside `parallel_intake`
- No race condition (temp file deleted before agent reads it)
- `emotion_fusion_node` gets pre-populated `voice_features` and `voice_processed=True`

### Why No Checkpointer?

LangGraph's `MemorySaver` was writing 7–9 checkpoint serialization events per message, adding 3–5s overhead. Replaced with a lightweight `_message_store` dict (rolling 20-message window per thread), cutting latency by 6×.

---

## 🔐 Compliance

- **GDPR-ready** — user data export endpoint available
- **Anonymous mode** — no PII required; anonymous users auto-provisioned
- **Consent tracking** — `consentGiven` + `consentDate` on User model
- **Crisis logging** — all events → `CrisisLog` table with timestamps and actions
- **Password security** — bcrypt hashing for authenticated users
- **Location privacy** — GPS coordinates are only transmitted during active crisis detection; never stored in the database

---

## 🤝 Contribution Guidelines

```
✅ Keep logic deterministic where possible
✅ LLM for semantics, ML for audio features — never swap these roles
✅ Every new node = single responsibility
✅ Always update MentalHealthState in state.py first
✅ Add a fallback return {} for every node (never crash the pipeline)
✅ Test with crisis messages to verify safety layers still fire
✅ Run massive_test_suite.py before any PR (PYTHONUTF8=1 on Windows)
✅ smart_pipeline_gate must always default to 'therapeutic' on failure — never skip crisis
✅ Gate confidence threshold for chitchat bypass is 0.75 — lower = too aggressive
✅ Any new intent category must be added to both smart_pipeline_gate AND llm_intent_check
```

---

## 👥 Team

| Name | Reg # | Role |
|------|-------|------|
| Taha Mehmood | 22MDSWE196 | Co-developer |
| Hasnain Gul | 22MDSWE216 | Co-developer |

*University of Engineering & Technology Mardan — Final Year Project 2022–2026*

---

<div align="center">

**SentiMind v9.0** — Smart Routing · Clinical Validation · Multimodal · Empathetic · Safe · Real-time

*Built with ❤️ for accessible mental health support*

</div>