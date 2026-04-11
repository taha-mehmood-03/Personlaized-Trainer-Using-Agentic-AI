<div align="center">

<img src="https://img.shields.io/badge/version-5.3-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/python-3.10+-6366f1?style=for-the-badge&logo=python&logoColor=white&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/LangGraph-0.2+-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/FastAPI-0.109+-6366f1?style=for-the-badge&logo=fastapi&logoColor=white&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/license-MIT-6366f1?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/LLM_calls-1_per_message-22c55e?style=for-the-badge&labelColor=0f0f1a" />
<img src="https://img.shields.io/badge/latency-v5.3_optimized-22c55e?style=for-the-badge&labelColor=0f0f1a" />

<br /><br />

```
███████╗███████╗███╗   ██╗████████╗██╗███╗   ███╗██╗███╗   ██╗██████╗
██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗ ████║██║████╗  ██║██╔══██╗
███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔████╔██║██║██╔██╗ ██║██║  ██║
╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╔╝██║██║██║╚██╗██║██║  ██║
███████║███████╗██║ ╚████║   ██║   ██║██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝
```

### **Deterministic Hybrid Mental Health Agent — v5.3 (Latency-Optimized)**

*A production-grade AI emotional support system — 10 graph nodes, 3 parallel tiers, 1 LLM call per message, fully async Groq pipeline*

<br />

[**Architecture**](#-architecture) · [**Features**](#-key-features) · [**Pipeline**](#-pipeline-stages) · [**Tech Stack**](#-tech-stack) · [**API**](#-api-endpoints) · [**Roadmap**](#-improvements--roadmap)

</div>

---

## 🧭 What is SentiMind?

SentiMind is a **clinically-informed, deterministic-first AI mental health agent** built on [LangGraph](https://github.com/langchain-ai/langgraph). It combines fast rule-based logic, local ML inference, and strategic LLM usage to deliver emotionally intelligent support — safely, cheaply, and at scale.

> **The core problem it solves:** Most AI mental health tools either use LLMs for everything (expensive, unsafe, unpredictable) or rule-based scripts for everything (robotic, inflexible). SentiMind uses *neither* exclusively — it routes each decision to the cheapest, fastest, safest component that can handle it.

---

## ⚡ Core Philosophy

```
               DECISION ROUTING LOGIC
               ─────────────────────

   Structured Decision?   ──→  Deterministic Python
   Pattern Recognition?   ──→  Local ML Model
   Empathetic Language?   ──→  Single LLM Call
   Crisis Detected?       ──→  Hardcoded Safety Template
```

| Principle | Implementation |
|-----------|---------------|
| **Deterministic-first** | 9 of 10 nodes are pure Python — no LLM |
| **Safety by default** | Three-layer crisis screening (keywords → ELECTRA → Groq 70b async) |
| **Token efficiency** | ~480 tokens/message (vs 1,500+ in ReAct systems) |
| **Truly async** | All Groq HTTP calls use `await ainvoke` — event loop never blocked |
| **Modular & auditable** | Each node has a single, testable responsibility |

---

## 🏗️ Architecture

### Full System Diagram (v5.3)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INPUT                                  │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 1 ── PARALLEL INTAKE v2                      ⚡ 4-WAY ASYNC  │
│  Runs FOUR tasks concurrently via asyncio.gather:                   │
│                                                                     │
│  ┌──────────────────┐ ┌──────────────────┐                         │
│  │ Crisis Screener  │ │  Context Loader  │                         │
│  │ Layer 1: Keywords│ │  DB + ChromaDB   │                         │
│  │ Layer 2: ELECTRA │ │  user profile    │                         │
│  │ Layer 3: 70b LLM │ │  semantic memory │                         │
│  │  (async ainvoke) │ │                  │                         │
│  └──────────────────┘ └──────────────────┘                         │
│  ┌──────────────────┐ ┌──────────────────┐                         │
│  │  Mood Analyzer   │ │  Intent Prefetch │  ← v5.3 NEW             │
│  │  DistilRoBERTa   │ │  Groq 8b async   │                         │
│  │  local CPU infer │ │  prefetched_intent│                         │
│  │  8 emotions      │ │  → state for     │                         │
│  │                  │ │    planner       │                         │
│  └──────────────────┘ └──────────────────┘                         │
│  All 4 read only initial state → write to disjoint keys             │
└──────────┬──────────────────────────────────────────────────────────┘
           │ normal (crisis → crisis_handler directly)
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 2 ── EMOTION FUSION                                🔗 FUSION  │
│  • Combines: text emotion (from parallel_intake) + voice emotion    │
│  • Outputs: fused_emotion, fused_intensity                          │
│  • Hedge dampening: "a little" → ×0.5 intensity multiplier         │
│                                                      NO LLM CALL   │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 3 ── PARALLEL ANALYSIS                       ⚡ 2-WAY ASYNC  │
│  Runs TWO tasks concurrently:                                       │
│  ┌──────────────────────────┐ ┌──────────────────────────────────┐  │
│  │ Cognitive Distortion     │ │ Trend Analyzer                   │  │
│  │ 8-pattern heuristic      │ │ Linear regression over last 5    │  │
│  │ LLM fallback (8b async)  │ │ MoodLogs. slope>+0.05→WORSENING  │  │
│  │ only on low confidence   │ │ slope<-0.05→IMPROVING | STABLE   │  │
│  └──────────────────────────┘ └──────────────────────────────────┘  │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 4 ── CONVERSATION PLANNER                          📋 STRATEGY│
│  Phase: VENTING → REFLECTION → SOLUTION → RECOVERY (+ NEUTRAL)     │
│  Strategy: no_action | validate_only | ask_question | reframe |     │
│            suggest_technique | encourage_reflection                  │
│                                                                     │
│  ┌─ v5.3 INTENT RESOLUTION (priority order) ──────────────────┐    │
│  │  1. prefetched_intent (from parallel_intake) → USE, no LLM │    │
│  │  2. Heuristic keyword match → USE, no LLM                  │    │
│  │  3. Groq 8b async call → ONLY for ambiguous messages (~20%) │    │
│  └─────────────────────────────────────────────────────────────┘    │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ├── strategy = no_action ──→ Skip to NODE 7 (Role Selector)
           │
           ▼ (therapeutic path)
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 5 ── BEHAVIORAL ACTIVATION                         💡 ACTION  │
│  • (emotion, intensity_band) → micro-action from 5-category matrix  │
│  • Time-of-day filter, profile-aware ordering     NO LLM CALL       │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 6 ── TECHNIQUE SELECTOR                            🎯 THERAPY │
│  • Planner-gated (skips on validate_only, ask_question, no_action)  │
│  • Queries PostgreSQL: top-3 by avgRating × targetEmotions          │
│  • 6 categories: Breathing/CBT/DBT/Mindfulness/Journaling/BA        │
│                                                      NO LLM CALL   │
└────┬──────┴──────────────────────────────────────────────────────────┘
     │
     ├──crisis──►┌──────────────────────────────────────────┐
     │           │  CRISIS HANDLER  🚨                       │
     │           │  Hardcoded template + 988 Lifeline        │
     │           │  NO LLM CALL                              │
     │           └──────────────────────────────────────────┘
     │
     ▼ (normal)
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 7 ── ROLE SELECTOR                                 👤 PERSONA │
│  friend | coach | trainer | crisis_support — phase + trend aware    │
│                                                      NO LLM CALL   │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 8 ── RESPONSE GENERATOR             ✨ SINGLE LLM CALL (ASYNC)│
│  • v5.3: uses await llm.ainvoke() — event loop never blocked        │
│  • Structured prompt: emotion, phase, strategy, technique,          │
│    distortion, micro-action, memory_context, chat history           │
│  • Model: Groq llama-3.3-70b-versatile · Key rotation supported    │
│  • LLM instance cached per key — no per-call ChatGroq construction  │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  NODE 9 ── PARALLEL PERSIST                        ⚡ 3-WAY ASYNC  │
│  Runs THREE tasks concurrently:                                     │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
│  │ Psych Profile    │ │  Session Saver   │ │  Outcome Tracker │    │
│  │ Updater          │ │  Prisma DB write │ │  Technique EMA   │    │
│  │ 9-field EMA      │ │  MoodLog create  │ │  effectiveness   │    │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘    │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      RESPONSE TO USER                               │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Latency Breakdown (v5.3)

```
  PARALLEL TIER 1                SERIAL PATH           PARALLEL TIER 2/3
  ─────────────────              ────────────          ─────────────────
  crisis_screener  ┐             emotion_fusion        distortion  ┐
  intake_node      ├── ~800ms ─► (~5ms)                trend       ├── ~60ms
  mood_analyzer    │             planner                            │
  intent_prefetch  ┘             (prefetch used,       profile+saver+
                                 ~0 LLM wait)          outcome    ─── ~120ms
                                 technique
                                 role_selector
                                 response_gen (async)
                                 ~1200ms

  SCENARIO            v5.2 (est.)    v5.3 (est.)    SAVING
  ──────────────────  ──────────     ──────────     ──────
  Casual chitchat     1.5–2.5s       0.8–1.2s       ~1s
  Venting (heuristic) 2–3s           1–1.8s         ~1s
  Ambiguous message   3–5s           1.5–2.5s       ~1.5–2.5s
  Crisis path         4–7s           2–3s           ~2–4s
```

---

### Token Budget per Message

```
  ┌─────────────────────────────────────────────────────┐
  │              TOKEN BUDGET (~480 total)              │
  │                                                     │
  │  System prompt          ████░░░░░░░░░  120 tokens   │
  │  Structured context     █████░░░░░░░░  150 tokens   │
  │  User message           ██░░░░░░░░░░░   50 tokens   │
  │  Memory context         ██░░░░░░░░░░░   60 tokens   │
  │  LLM output             ████░░░░░░░░░  100 tokens   │
  │                                                     │
  │  vs ReAct baseline:     ████████████  1,570 tokens  │
  │  SAVINGS: 71% ▼                                     │
  └─────────────────────────────────────────────────────┘
```

---

## 🧠 Key Features

| Feature | Implementation |
|---------|---------------|
| 🎭 **Real-time Emotion Detection** | Local DistilRoBERTa — 8 emotions + sentiment + intensity, no API cost |
| 🧠 **Cognitive Distortion Detection** | 8-pattern weighted heuristic + conditional LLM (Groq 8b) fallback |
| 📋 **Conversation Phase Awareness** | NEUTRAL → VENTING → REFLECTION → SOLUTION → RECOVERY |
| 🧬 **Persistent Psychological Profile** | 9-field user profile with EMA smoothing, updated per session |
| 🎯 **Planner-Gated Technique Selection** | Strategy + readiness score gate technique delivery timing |
| 💡 **Behavioral Activation** | Emotion × intensity_band × time-of-day matrix, profile-aware ordering |
| 📈 **Longitudinal Trend Detection** | Linear regression over last 5 MoodLogs, requires ≥3 sessions |
| 🔗 **Multimodal Fusion Layer** | Text + voice emotion fusion; voice via opensmile/librosa/torchaudio |
| 🚨 **Three-Layer Crisis Detection** | Keywords → ELECTRA specialist → Groq 70b Chain-of-Thought validator |
| 🧠 **Semantic Memory** | ChromaDB vector store for cross-session context (RAG) |
| ⚡ **Chitchat Fast-Path** | Bypasses therapeutic nodes (7–8) when neutral + low intensity detected |
| 👤 **Phase-Aware Role Selection** | Friend/Coach/Trainer/Crisis — considers trend, phase, and intensity |

---

## 📦 Pipeline Stages

| Graph Node | Logical Tasks | LLM? | Avg Time |
|---|------|-------|----------|
| **1** Parallel Intake v2 | crisis screener \|\| intake \|\| mood \|\| intent prefetch | Crisis: Groq 70b async (conditional) · Intent: Groq 8b async | **~800ms** (all 4 concurrent) |
| **2** Emotion Fusion | text + voice fusion, hedge dampening | ❌ | ~5ms |
| **3** Parallel Analysis | distortion \|\| trend (concurrent) | Distortion: Groq 8b async (conditional) | ~60ms |
| **4** Conversation Planner | phase + strategy, uses prefetched_intent | ❌ (prefetch consumed) | ~5ms |
| **5** Behavioral Activation | micro-action matrix | ❌ | ~5ms |
| **6** Technique Selector | PostgreSQL DB query | ❌ | ~100ms |
| Crisis Handler | hardcoded template + 988 Lifeline | ❌ | ~1ms |
| **7** Role Selector | phase-aware persona | ❌ | ~1ms |
| **8** Response Generator | single Groq 70b call, **async** ainvoke | ✅ **ONE** | ~1200ms |
| **9** Parallel Persist | psych profile \|\| session saver \|\| outcome tracker | ❌ | ~120ms (concurrent) |
| | **TOTAL (warm server)** | **1 LLM call always** | **~1.5–2.5s** |

---

## 🛠️ Tech Stack

```
Frontend                 Backend                  AI / ML
─────────────────        ───────────────          ────────────────────
Next.js 14 (App Router)  FastAPI                  DistilRoBERTa (emotion)
React 18 + TypeScript    LangGraph 0.2+           ELECTRA (crisis)
Tailwind CSS             LangChain                Llama 3.3 70b (Groq)
Radix UI Primitives      Python 3.10+             Llama 3.1 8b (Groq)
Lucide React (icons)     Uvicorn                  Sentence Transformers
next-themes              Pydantic                 opensmile + librosa

Data                     DevOps
──────────────────────   ──────────────────────
PostgreSQL (Supabase)    CORS middleware
Prisma Client Python     SSE streaming endpoint
ChromaDB (RAG)           Groq API key rotation
langgraph-checkpoint-    bcrypt auth
  postgres               python-dotenv
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

    # Intake (Node 1)
    is_new_user: bool
    session_count: int
    most_common_emotion: str
    user_preferences: dict
    chat_history: list[dict]
    memory_context: str           # ChromaDB semantic retrieval

    # Intent
    intent: str                   # casual|emotional|crisis|technique_request|check_in
    skip_intervention: bool       # True → chitchat fast-path bypass

    # v5.3: Prefetched intent (written by parallel_intake, consumed by planner)
    prefetched_intent: Optional[dict]  # {"intent": str, "confidence": float}

    # Mood Analyzer (now inside Parallel Intake)
    emotion: str                  # anger|fear|sadness|joy|neutral|surprise|disgust|anxiety
    sentiment: str                # positive|negative|neutral
    intensity: float              # 0.0–1.0
    confidence: float

    # Emotion Fusion
    fused_emotion: str
    fused_intensity: float

    # Voice Analysis (optional)
    voice_emotion: str
    voice_arousal: float
    voice_valence: float
    voice_confidence: float
    has_voice: bool
    audio_file_path: Optional[str]

    # Cognitive Distortion (Parallel Analysis)
    distortion_type: Optional[str]
    distortion_confidence: float
    distortion_explanation: Optional[str]
    all_distortions: list[str]

    # Trend Analyzer (Parallel Analysis)
    emotional_trend: str          # improving|stable|worsening
    trend_window: list[dict]      # last N {emotion, intensity} snapshots

    # Conversation Planner
    conversation_strategy: str    # no_action|validate_only|ask_question|reframe|
                                  # suggest_technique|encourage_reflection
    conversation_phase: str       # neutral|venting|reflection|solution|recovery
    technique_readiness: float    # 0.0–1.0

    # Behavioral Activation
    micro_action: Optional[str]
    micro_action_rationale: Optional[str]
    micro_action_category: Optional[str]  # physical|social|environmental|nourishment|cognitive

    # Technique Selector
    recommended_technique: dict
    recommended_techniques_by_category: dict
    alternative_techniques: list[dict]

    # Crisis Detection
    crisis_level: str             # low|medium|high
    crisis_detected: bool
    crisis_resources: dict
    crisis_pre_screened: bool

    # Role & Response
    agent_role: str               # friend|coach|trainer|crisis_support
    final_response: str

    # Psych Profile (Parallel Persist)
    psych_profile: dict
    proactive_alert: Optional[str]

    # Session Intelligence
    session_summary: str
    session_message_count: int

    # Outcome Tracker Baselines
    session_start_emotion: Optional[str]
    session_start_intensity: Optional[float]
    technique_delivery_emotion: Optional[str]
    technique_delivery_intensity: Optional[float]
    historical_mood: str

    # Metadata
    tools_used: list[str]
    processing_time_ms: int
    technique_reasoning: str
```

---

## 🗄️ Database Schema (Prisma → PostgreSQL)

12 models with proper normalization. Key models shown:

```
model User {
  id            String    @id
  email         String    @unique
  name          String
  passwordHash  String?
  consentGiven  Boolean   @default(false)
  → sessions[], moodLogs[], techniqueRatings[], crisisLogs[]
  → preference?, statistics?, psychProfile?
  → facts[], sessionSummaries[]
}

model Session {
  id             String
  userId         String
  title          String          @default("New Conversation")
  status         SessionStatus   (ACTIVE | COMPLETED | ABANDONED)
  phase          ConversationPhase (VENTING | REFLECTION | SOLUTION | RECOVERY)
  agentRole      AgentRole       (FRIEND | COACH | TRAINER | CRISIS_SUPPORT)
  → messages[], emotionSnapshots[], techniqueOutcomes[], summaries[]
}

model Message {
  id           String
  sessionId    String
  role         MessageRole     (USER | ASSISTANT | SYSTEM)
  content      Text
  emotion      Emotion?        (ANGER|DISGUST|FEAR|JOY|NEUTRAL|SADNESS|SURPRISE|ANXIETY)
  intensity    Float?
  sentiment    Sentiment?
  techniqueId  String?         → Technique relation
  voiceEmotion String?        (voice analysis fields)
}

model PsychProfile {
  userId            String    @unique
  copingStyle       String    @default("avoidant")    // avoidant|proactive|mixed
  techniqueAccRate  Float     @default(0.5)
  reflectionDepth   Float     @default(0.5)
  anxietyBaseline   Float     @default(0.5)            // EMA of anxiety intensity
  resilienceScore   Float     @default(0.5)
  dominantEmotion   String    @default("neutral")
  socialDependency  Float     @default(0.5)
  motivationType    String    @default("external")
  emotionalTriggers String[]
  topDistortions    String[]
  distortionCount   Int       @default(0)
}

model Technique {
  id               String
  categoryId       String    → TechniqueCategory
  name             String
  description      String
  brief            String
  steps            String[]
  durationMinutes  Int
  difficulty       Difficulty  (EASY | MODERATE | HARD)
  targetEmotions   Emotion[]
  avgRating        Float
  effectiveness    Float
}

model TechniqueOutcome {
  sessionId        String
  techniqueId      String
  emotionBefore    Emotion
  emotionAfter     Emotion?
  intensityBefore  Float
  intensityAfter   Float?
  effectiveness    Float?
}

model CrisisLog {
  userId               String
  riskLevel            CrisisRiskLevel  (LOW | MEDIUM | HIGH)
  triggeredKeywords    String[]
  messageContent       Text
  actionTaken          String
  resourcesProvided    Boolean
  humanHandoffRequested Boolean
}

// Also: MoodLog, TechniqueCategory, UserTechniqueRating,
//       UserPreference, UserStatistics, SessionSummary,
//       UserFact, EmotionSnapshot
```

---

## 🔌 API Endpoints

The `api_server.py` FastAPI application exposes:

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/api/chat` | `POST` | Core agent interaction — returns response + emotion + techniques |
| `/api/chat/stream` | `POST` | SSE streaming endpoint — word-by-word token streaming + metadata |
| `/api/pipeline/complete` | `POST` | Full pipeline with frontend-compatible response format |
| `/api/user/create` | `POST` | Create user with email/name + auto-create preferences & statistics |
| `/api/user/ensure` | `POST` | Ensure user exists, create anonymous footprint if not found |
| `/api/auth/signup` | `POST` | Sign up with email + bcrypt-hashed password |
| `/api/auth/login` | `POST` | Login with email + password verification |
| `/api/user/{id}/sessions` | `GET` | Retrieve sessions with all messages + technique data |
| `/api/session/{id}/messages` | `GET` | Get all messages from a specific session |
| `/api/session/{id}/rename` | `PATCH` | Rename a chat session title |
| `/api/user/{id}/stats` | `GET` | User statistics (streaks, totals, avg mood) |
| `/api/techniques` | `GET` | Technique catalog, filterable by emotion/category |
| `/api/technique/rate` | `POST` | Submit 1–5 star rating + feedback for a technique |
| `/api/wellness/tips` | `GET` | Static wellness tips (gratitude, breathing, etc.) |
| `/health` | `GET` | Detailed health check (DB + agent readiness) |

---

## 📁 Repository Structure

```bash
├── frontend/                         # Next.js 14 Web UI
│   ├── src/                          # App Router, components, utilities
│   ├── tailwind.config.ts            # Design system tokens
│   ├── middleware.ts                  # Auth / routing middleware
│   └── package.json                  # React 18, Radix UI, Lucide, next-themes
│
└── mental_health_wellness/           # Python AI Backend
    ├── api_server.py                 # FastAPI server (15+ endpoints)
    ├── prisma/
    │   └── schema.prisma             # 12 models, 477 lines
    ├── requirements.txt              # LangGraph, PyTorch, Transformers, opensmile
    └── src/mental_health_wellness/
        ├── agent/
        │   ├── graph.py              # LangGraph StateGraph v5.3 (10 nodes)
        │   ├── state.py              # MentalHealthState TypedDict (+ prefetched_intent)
        │   └── preprocessing.py      # MessagePreprocessor, emotion normalization
        ├── nodes/                    # Node modules
        │   ├── parallel_intake.py    # ⚡ v5.3: 4-way concurrent intake
        │   ├── intake.py             # Context loader (ChromaDB + Prisma)
        │   ├── mood_analyzer_node.py # DistilRoBERTa (runs inside parallel_intake)
        │   ├── emotion_fusion_node.py
        │   ├── parallel_analysis.py  # Distortion + trend (concurrent)
        │   ├── conversation_planner_node.py  # Uses prefetched_intent
        │   ├── behavioral_activation_node.py
        │   ├── technique_selector_node.py
        │   ├── crisis_handler.py
        │   ├── role_selector.py
        │   ├── optimized_response_generator.py  # await ainvoke (v5.3)
        │   ├── parallel_persist.py   # psych + saver + outcome (concurrent)
        │   ├── psych_profile_updater.py
        │   ├── session_saver.py
        │   ├── outcome_tracker_node.py
        │   └── voice_preprocessing.py
        ├── llm/
        │   ├── groq_llm.py           # Multi-key Groq manager + instance cache (v5.3)
        │   └── llm_classifier.py     # All Groq calls now async ainvoke (v5.3)
        ├── db/                       # Prisma client
        ├── memory/                   # ChromaDB semantic retrieval
        ├── tools/                    # mood_tools, technique_tools
        └── utils/                    # Formatters, helpers
```

---

## 🚀 Setup & Installation

### 1. Backend Environment

```bash
cd mental_health_wellness
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file:
```ini
GROQ_API_KEY="your_groq_key"
GROQ_API_KEY_2="optional_second_key_for_rotation"
DATABASE_URL="postgresql://user:password@localhost:5432/sentimind"
DIRECT_URL="postgresql://user:password@localhost:5432/sentimind"
```

### 3. Database Initialization (Prisma)

```bash
prisma generate
prisma db push
```

### 4. Running the Backend

```bash
cd mental_health_wellness
python -m api_server
# ML models auto-preload on startup (DistilRoBERTa, ELECTRA)
```

### 5. Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## 🚀 Improvements & Roadmap

### ⚡ 1. Latency Optimization — v5.3 Full Async Pipeline  ✅ IMPLEMENTED

Three classes of latency bugs fixed and one architectural improvement added:

**Fix 1 — Async façade bug (biggest win, ~1–3s per message):**
All Groq HTTP calls were `llm.invoke()` (blocking `requests` library) inside `async def` functions — freezing the event loop. Fixed by converting `_call_groq` to `async def _call_groq_async` using `await llm.ainvoke()`.

```python
# llm/llm_classifier.py — v5.3
async def _call_groq_async(prompt, model, temperature, max_tokens):
    call_llm = manager.get_llm(model=model).bind(max_tokens=max_tokens)
    response = await call_llm.ainvoke(prompt)   # ← NON-BLOCKING
    return response.content
```

**Fix 2 — LLM instance cache (~20–50ms per call):**  
`get_llm()` now returns a cached `ChatGroq` instance keyed by `(key_idx, model)` instead of constructing a new object on every call.

**Fix 3 — Response generator async (~1–3s per message):**  
Both `llm.invoke()` calls in `optimized_response_generator.py` replaced with `await llm.ainvoke()`.

**Architecture — 4-way Parallel Intake (v5.3, ~800–1500ms off critical path):**  
Mood analysis and intent pre-check now run concurrently with crisis screening and context loading:

```python
# nodes/parallel_intake.py — v5.3
crisis_result, intake_result, mood_result, intent_result = await asyncio.gather(
    crisis_pre_screener_node(state),    # ELECTRA + async Groq 70b
    intake_node(state),                  # DB + ChromaDB
    mood_analyzer_node(state),           # DistilRoBERTa local
    _intent_pre_check_task(message),     # async Groq 8b
    return_exceptions=True,
)
# prefetched_intent → state → conversation_planner skips its LLM call
```

**Before v5.2:** `Intake → Mood → Fusion → ... → Planner [+LLM intent]` (~3–5s)
**After v5.3:** `ParallelIntake[crisis|intake|mood|intent] → Fusion → ...` (~1.5–2.5s)

---

### 🎯 2. Hedge Dampening for Intensity Calibration  ✅ IMPLEMENTED

Implemented in `emotion_fusion_node.py` (FIX 3). Detects hedging language and applies a 50% intensity multiplier to prevent over-escalation.

```python
# Already live in emotion_fusion_node.py
_HEDGE_WORDS = [
    "a little", "a bit", "slightly", "kind of", "kinda", "somewhat",
    "a tad", "mildly", "not that", "not very", "not too", "sort of",
]
_HEDGE_MULTIPLIER = 0.50

# "I'm a little annoyed" → ANGER 76% → ANGER 38% → Friend role (correct)
```

---

### 🧬 3. Profile-Aware Personalization Engine  ✅ IMPLEMENTED

The conversation planner now reads the user's `PsychProfile` to adapt its therapeutic strategy. Four profile-aware overrides run BEFORE the default strategy rules:

```python
# conversation_planner_node.py — v5.1 _select_strategy()
# Reads: copingStyle, resilienceScore, techniqueAccRate

1. Avoidant coping + moderate distress → validate_only (don't push techniques)
2. High resilience (>0.7) + low distress → encourage_reflection
3. Low acceptance rate (<0.3) + worsening → reframe (stop suggesting rejected techniques)
4. Proactive coping + high distress → suggest_technique (action-oriented user)
```

---

### 📱 4. Product & UX Enhancements

| Feature | Priority | Status |
|---------|----------|--------|
| Mood dashboard (charts + trends) | High | Planned |
| Daily check-in push notifications | High | Planned |
| Streak system + engagement hooks | Medium | Partial (UserStatistics exists) |
| Technique feedback (👍 / 👎) | High | ✅ Implemented (`/api/technique/rate`) |
| Voice input (browser recording) | Medium | ✅ Backend ready (`voice_preprocessing.py`) |
| PHQ-9 / GAD-7 screening | Low | Planned |

---

### 🔐 5. Clinical Validation Layer

```
PLANNED INTEGRATION:

  PHQ-9  →  Depression severity scoring
  GAD-7  →  Anxiety severity scoring

  Trigger clinical validation when:
    • resilience_score < 0.3 for 5+ sessions
    • emotion = sadness/anxiety for 7+ consecutive days
    • trend = worsening for 2+ weeks

  Output:
    → Flag for therapist review
    → Adjusted response tone
    → Referral suggestion in response
```

---

### 🏗️ 6. Tiered Execution Architecture  ✅ IMPLEMENTED

Three execution paths based on message analysis:

```
  MESSAGE ARRIVES
       │
       ├── CASUAL (neutral, intensity < 0.25, skip_intervention=True)
       │    └── FAST PATH: Skip Nodes 7–8  ← ✅ IMPLEMENTED
       │         ~1.5s total
       │
       ├── EMOTIONAL (distress, intensity 0.3–0.7)
       │    └── FULL PATH: All nodes (with parallel analysis)
       │         ~2.5s total
       │
       └── CRISIS (keywords matched OR intensity ≥ 0.8 + neg emotion)
            └── CRISIS PATH: Pre-screener → Crisis Handler (bypass LLM)
                 ~0.1s total  ← ✅ IMPLEMENTED
```


---

## 🏆 Competitive Positioning

| Capability | Replika | Woebot† | Wysa | **SentiMind v5** |
|------------|---------|---------|------|-----------------|
| Real-time emotion detection | Basic | Scripted | Rule-based | ✅ DistilRoBERTa (8 emotions) |
| Cognitive distortion detection | ❌ | ✅ Scripts | ✅ Scripts | ✅ 8-pattern heuristic + LLM |
| Conversation phase awareness | ❌ | ⚠️ Partial | ❌ | ✅ 5-phase detection |
| Long-term psychological profile | ⚠️ Persona | ❌ | ❌ | ✅ 9-field persistent profile |
| Behavioral activation | ❌ | ✅ | ✅ 150+ | ✅ Emotion × time × profile matrix |
| Proactive trend detection | ❌ | ❌ | ❌ | ✅ Linear regression over MoodLogs |
| Multi-layer crisis detection | Basic | N/A | Basic | ✅ Keywords + ELECTRA + Groq 70b |
| Token efficiency | N/A | N/A | N/A | ✅ ~480/msg (71% savings vs ReAct) |
| Architecture transparency | Closed | Shutdown† | Closed | ✅ Open LangGraph nodes |
| Voice emotion integration | ❌ | ❌ | ❌ | ✅ opensmile + librosa fusion |

*† Woebot shut down its consumer app June 2025*

---

## 🤝 Contribution Guidelines

```
✅ Keep logic deterministic where possible
✅ Use LLM only as the last resort (classify with Groq 8b, never 70b for non-response tasks)
✅ Every new node = single responsibility
✅ Always update MentalHealthState in state.py first
✅ Add a fallback return {} for every node (never crash the pipeline)
✅ Wire new nodes into build_graph() in graph.py with exact edge routing
✅ Test with crisis messages to verify safety layers still fire
```

---

## 🔐 Compliance

- **GDPR-ready** — user data export endpoint (`/api/user/{id}/data-export`)
- **Anonymous mode** — no PII required; anonymous users auto-provisioned
- **Consent tracking** — `consentGiven` + `consentDate` fields on User model
- **Crisis logging** — all crisis events → `CrisisLog` table with timestamps, keywords, actions
- **Password security** — bcrypt hashing for authenticated users
- **Cascade deletion** — `onDelete: Cascade` on all user-owned relations

---

## 👥 Team

| Name | Reg # | Role |
|------|-------|------|
| Taha Mehmood | 22MDSWE196 | Co-developer |
| Hasnain Gul | 22MDSWE216 | Co-developer |

*University of Engineering & Technology Mardan — Final Year Project 2022–2026*

---

<div align="center">

**SentiMind v5.0** — Faster · Safer · Smarter · More Personal

*Built with ❤️ for accessible mental health support*

</div>