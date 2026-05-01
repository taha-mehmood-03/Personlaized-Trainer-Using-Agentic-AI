<div align="center">

<img src="https://img.shields.io/badge/version-7.0-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/python-3.10+-6366f1?style=for-the-badge&logo=python&logoColor=white&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/LangGraph-0.2+-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/FastAPI-0.109+-6366f1?style=for-the-badge&logo=fastapi&logoColor=white&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/license-MIT-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/Voice-Multimodal_Fusion-22c55e?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/latency-v7.0_optimized-22c55e?style=for-the-badge&labelColor=0f0f1a" />

<br /><br />

```
███████╗███████╗███╗   ██╗████████╗██╗███╗   ███╗██╗███╗   ██╗██████╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗ ████║██║████╗  ██║██╔══██╗
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔████╔██║██║██╔██╗ ██║██║  ██║
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╔╝██║██║██║╚██╗██║██║  ██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝
```

### **Deterministic Hybrid Mental Health Agent — v7.0 (Multimodal Voice Fusion)**

*A production-grade AI emotional support system — 5 fused nodes, 3 parallel tiers, true token streaming, multimodal voice + text emotion fusion*

<br />

[**Architecture**](#-architecture) · [**Voice Pipeline**](#-voice-pipeline-v70) · [**Features**](#-key-features) · [**Pipeline**](#-pipeline-stages) · [**Tech Stack**](#-tech-stack) · [**API**](#-api-endpoints) · [**Setup**](#-setup--installation)

</div>

---

## 🧭 What is SentiMind?

SentiMind is a **clinically-informed, multimodal AI mental health agent** built on [LangGraph](https://github.com/langchain-ai/langgraph). It uses semantic LLM understanding for all decision-making and fuses **text emotion** with **real acoustic voice features** (pitch, arousal, distress index) to detect emotion masking — where a user's words say one thing but their voice reveals another.

> **The core problem it solves:** Most mental health chatbots rely purely on text. SentiMind adds a full voice analysis layer so it can catch when a user says "I'm fine" in a sad voice and respond to their *true* emotional state.

---

## ⚡ Core Philosophy (v7.0)

```
               DECISION ROUTING LOGIC
               ─────────────────────

   Semantic Understanding?  ──→  LLM (OpenRouter — llama-3.3-70b / claude-3.5-sonnet)
   Voice Features?          ──→  ML models (wav2vec2, OpenSMILE eGeMAPS, Whisper ASR)
   Emotion Masking?         ──→  Acoustic Override (distress_index / arousal rules)
   Crisis Response?         ──→  LLM semantic analysis (claude-3.5-sonnet) + Twilio alerts
```

| Principle | Implementation |
|-----------|---------------|
| **LLM-first** | All semantic decisions use LLM for nuanced understanding |
| **Multimodal voice** | wav2vec2 emotion + OpenSMILE acoustic features + Whisper ASR |
| **Acoustic Override** | Catches emotion masking (happy words + sad voice → sadness) |
| **Safety by default** | LLM crisis detection + GPS-aware Twilio WhatsApp/SMS alerts |
| **SSE Streaming** | LangGraph true real-time token streaming directly to frontend |
| **Zero ffmpeg** | Browser-side WebM→WAV conversion (Web Audio API) |

---

## 🏗️ Architecture

### Full System Diagram (v7.0)

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
│  NODE 1 ── PARALLEL INTAKE                          ⚡ 4-WAY ASYNC │
│  ┌──────────────────┐ ┌──────────────────┐                         │
│  │ Crisis Screener  │ │  Context Loader  │                         │
│  │ claude-3.5-sonnet│ │  DB + ChromaDB   │                         │
│  └──────────────────┘ └──────────────────┘                         │
│  ┌──────────────────┐ ┌──────────────────┐                         │
│  │  Mood Analyzer   │ │  Intent Prefetch │                         │
│  │  llama-3.3-70b   │ │  llama-3.1-8b    │                         │
│  └──────────────────┘ └──────────────────┘                         │
└────────────────────────┬───────────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│  NODE 2 ── ANALYSIS & PLANNING                          🔗 FUSED  │
│  • Emotion Fusion  (text + pre-injected voice_features)            │
│      → Acoustic Override: distress_index > 0.65 → sadness         │
│      → Arousal Override:  arousal > 0.75 → anxiety                │
│      → Pause Boost:       pause_density > 0.40 → +15% intensity   │
│  • Parallel Analysis (Cognitive Distortion + Trend)                │
│  • Conversation Planner (Phase & Strategy)                         │
│  • Behavioral Activation (Micro-actions)                           │
└────────────────────────┬───────────────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────────────┐
│  NODE 3 ── RESPONSE PIPELINE                            🔗 FUSED  │
│  • Technique Selector (PostgreSQL query)                            │
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
  1. extract_acoustic_features()     # OpenSMILE eGeMAPS → pitch, jitter, shimmer, HNR
                                     # fallback: librosa → pitch, loudness, MFCC
                                     # + torchaudio MFCC (13-dim + delta + delta-delta)
                                     # → distress_index (composite psychoacoustic score)
                                     # → pause_density  (hesitancy / silence ratio)

  2. classify_voice_emotion()        # wav2vec2 (r-f/wav2vec-english-speech-emotion-recognition)
                                     # → emotion label + confidence + all_scores

  3. transcribe_audio()              # Whisper-tiny (openai/whisper-tiny)
                                     # → ASR transcript (reused, no double-call)
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
| 🎭 **Multimodal Emotion Detection** | LLM text emotion + wav2vec2 voice emotion + acoustic feature fusion |
| 🔊 **Acoustic Override** | Catches emotion masking (happy words + sad voice → detects sadness) |
| 🧠 **Cognitive Distortion Detection** | LLM semantic analysis via llama-3.1-8b |
| 📋 **Conversation Phase Awareness** | NEUTRAL → VENTING → REFLECTION → SOLUTION → RECOVERY |
| 🧬 **Persistent Psychological Profile** | 9-field user profile with EMA smoothing, updated per session |
| 🎯 **Planner-Gated Technique Selection** | Strategy + readiness score gate technique delivery timing |
| 💡 **Behavioral Activation** | Emotion × intensity_band × time-of-day matrix |
| 📈 **Longitudinal Trend Detection** | Linear regression over last 5 MoodLogs, requires ≥3 sessions |
| 🚨 **Crisis Detection** | claude-3.5-sonnet semantic analysis — NO keyword matching |
| 📍 **GPS Crisis Alerts** | Browser geolocation → Twilio WhatsApp/SMS with Google Maps link |
| 🧠 **Semantic Memory** | ChromaDB vector store for cross-session context (RAG) |
| 👤 **Phase-Aware Role Selection** | Friend / Coach / Trainer / Crisis — considers trend, phase, intensity |
| 🎤 **Browser-Native WAV Encoding** | Web Audio API → 16kHz mono RIFF/WAV, zero system dependencies |

---

## 📦 Pipeline Stages (v7.0)

| Graph Node | Logical Tasks | LLM Provider | Model | Avg Time |
|---|------|-------|----------|----------|
| **Pre-server** | Voice model preload (Whisper + wav2vec2 + OpenSMILE) | ❌ ML only | — | Startup |
| **API Layer** | WebM decode → WAV → voice feature extraction | ❌ ML only | wav2vec2 / librosa | ~200ms |
| **1** Parallel Intake | crisis ∥ intake ∥ mood ∥ intent prefetch | ✅ OpenRouter | claude-3.5-sonnet / llama-3.3-70b | ~800ms |
| **2** Analysis & Planning | emotion fusion + distortion + trend + planner + behavior | ✅ Fallback | llama-3.1-8b | ~60ms |
| **3** Response Pipeline | technique selector + role selector | ❌ DB only | — | ~100ms |
| **4** Response Generator | Empathetic response with voice-aware context | ✅ OpenRouter | llama-3.3-70b | ~1200ms |
| **5** Parallel Persist | profile ∥ DB saver ∥ outcome tracker (background) | ❌ | — | 0ms (UI) |
| | **TOTAL (warm, TTFT)** | | | **~2.1s** |

---

## 🛠️ Tech Stack

```
Frontend                    Backend                    AI / ML
──────────────────          ───────────────            ────────────────────────
Next.js 14 (App Router)     FastAPI                    llama-3.3-70b (OpenRouter)
React 18 + TypeScript       LangGraph 0.2+             claude-3.5-sonnet (OpenRouter)
Tailwind CSS                LangChain                  wav2vec2 (voice emotion)
Web Audio API               Python 3.10+               OpenSMILE eGeMAPS (acoustics)
MediaRecorder API           Uvicorn                    librosa (acoustic fallback)
Lucide React                Pydantic                   torchaudio MFCC
                            asyncio / SSE              Whisper-tiny (ASR)
                                                       ChromaDB (semantic memory)

Data                        DevOps
──────────────────          ──────────────────────
PostgreSQL (Supabase)       CORS middleware
Prisma Client Python        SSE streaming endpoint
ChromaDB                    Twilio (WhatsApp + SMS)
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
    memory_context: str           # ChromaDB semantic retrieval
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
    ├── prisma/schema.prisma            # 12 models
    └── src/mental_health_wellness/
        ├── agent/
        │   ├── graph.py                # LangGraph 5-node graph + chat_with_agent_streaming
        │   └── state.py                # MentalHealthState TypedDict (voice fields added)
        ├── nodes/
        │   ├── parallel_intake.py      # 4-way concurrent intake
        │   ├── analysis_and_planning.py# Fused: fusion + distortion + trend + planner
        │   ├── emotion_fusion_node.py  # 3-way text+voice+acoustic fusion + overrides
        │   ├── response_pipeline.py    # Fused: technique + role selector
        │   ├── optimized_response_generator.py
        │   ├── crisis_handler.py       # LLM-based crisis + Twilio alerts
        │   ├── parallel_persist.py     # Fire-and-forget: profile + saver + outcome
        │   └── voice_preprocessing.py  # preprocess_voice_input() node
        ├── voice/
        │   └── __init__.py             # analyze_voice_full() + preload_all_voice_models()
        │                               # OpenSMILE → librosa → torchaudio → wav2vec2 → Whisper
        ├── llm/
        │   ├── groq_llm.py             # OpenRouter LLM manager
        │   └── llm_classifier.py       # LLM-based intent, crisis, distortion classifiers
        ├── db/                         # Prisma client
        └── memory/                     # ChromaDB semantic retrieval
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
#   [VOICE-PRELOAD] OpenSMILE: ok
#   [VOICE-PRELOAD] wav2vec2: ok
#   [VOICE-PRELOAD] Whisper: ok
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

**SentiMind v7.0** — Multimodal · Empathetic · Safe · Real-time

*Built with ❤️ for accessible mental health support*

</div>