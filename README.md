<div align="center">

# SentiMind

### AI Mental Health Wellness Platform

*Agentic conversation · Voice fusion · Crisis safety · Memory · Therapeutic techniques · Outcome analytics*

SentiMind is a full-stack Final Year Project combining a Next.js frontend, FastAPI backend, LangGraph-style agent workflow, Gemini language and audio intelligence, Prisma Python ORM, Supabase PostgreSQL, structured memory, therapeutic technique selection, crisis routing, and longitudinal mood analytics.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white">
  <img alt="Supabase" src="https://img.shields.io/badge/Supabase-PostgreSQL-3FCF8E?style=for-the-badge&logo=supabase&logoColor=white">
  <img alt="Prisma" src="https://img.shields.io/badge/Prisma-Python-2D3748?style=for-the-badge&logo=prisma&logoColor=white">
  <img alt="Gemini" src="https://img.shields.io/badge/Gemini-AI-4285F4?style=for-the-badge&logo=google&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Agentic_Workflow-1C3C3C?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/Status-Active_Development-brightgreen?style=for-the-badge">
</p>

> **Disclaimer:** SentiMind is a wellness and educational software project. It is **not** a medical device, **not** a diagnostic system, and **not** a replacement for licensed care, emergency support, or professional treatment.

</div>

---

## Table of Contents

- [Project Snapshot](#project-snapshot)
- [Architecture Overview](#architecture-overview)
- [Runtime Flow](#runtime-flow)
- [Pre-Graph Gate](#pre-graph-gate)
- [Agent Graph](#agent-graph)
- [Node Analysis](#node-analysis)
- [Lifecycle and Outcome Tracking](#lifecycle-and-outcome-tracking)
- [Voice and Emotion Fusion](#voice-and-emotion-fusion)
- [Crisis Safety](#crisis-safety)
- [Memory and Personalization](#memory-and-personalization)
- [Dashboard Analytics](#dashboard-analytics)
- [Database Design](#database-design)
- [API Surface](#api-surface)
- [Frontend Architecture](#frontend-architecture)
- [Repository Structure](#repository-structure)
- [Environment Variables](#environment-variables)
- [Setup](#setup)
- [Running the Project](#running-the-project)
- [Validation](#validation)
- [Operational Notes](#operational-notes)
- [Credits](#credits)

---

## Project Snapshot

SentiMind is built around **structured emotional state**, not a single flat chatbot prompt. A user message enters through the API, passes through smart routing, runs through a compact agent graph, writes durable analytics to Supabase, and returns a response that is supportive, technique-oriented, memory-aware, or crisis-safe depending on the situation.

| Area | Location |
|---|---|
| Backend entrypoint | `mental_health_wellness/src/mental_health_wellness/api/app.py` |
| Agent graph | `mental_health_wellness/src/mental_health_wellness/agent/graph.py` |
| Frontend | `frontend/src` |
| Prisma schema | `mental_health_wellness/prisma/schema.prisma` |
| Database | Supabase PostgreSQL via Prisma Python |
| Lifecycle/outcome tracking | `mental_health_wellness/LIFECYCLE_OUTCOME_TRACKING_CHANGES.md` |

> **Note:** Prisma and Supabase are functionally aligned for the current app. Supabase may still contain the legacy enum value `TurnType.POST_RECOMMENDATION`; the app normalizes it to `POST_RECOMMENDATION_REACTION`.

---

## Architecture Overview

SentiMind has **two orchestration layers** before a user receives a reply:

1. **Pre-graph routing** in `agent/graph.py` and `llm/llm_classifier.py` — decides whether the message can take a fast bypass route or must enter the full therapeutic graph.
2. **The 5-node agent graph** built in `build_graph()` — performs deeper emotion, memory, technique, crisis, and response work.

```mermaid
flowchart TB
    classDef client fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef backend fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef agent fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef data fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46
    classDef providers fill:#FFF7ED,stroke:#F97316,stroke-width:2px,color:#9A3412
    classDef user fill:#FFF1F2,stroke:#F43F5E,stroke-width:2px,color:#881337

    User["👤 User"]:::user

    subgraph Client["Frontend — Next.js 14"]
        UI["Chat · Voice · Dashboard · Profile · Auth"]:::client
        ApiClient["API client layer"]:::client
    end

    subgraph Backend["Backend — FastAPI"]
        Routes["REST and streaming routes"]:::backend
        SmartGate["Smart gate & pre-graph bypass router"]:::backend
        Agent["SentiMind agent orchestrator"]:::backend
        Persist["Parallel persistence layer"]:::backend
        Analytics["Dashboard and profile analytics"]:::backend
    end

    subgraph AgentCore["Agent Intelligence — 5-node graph"]
        Intake["Parallel intake node"]:::agent
        Planning["Analysis and planning node"]:::agent
        Pipeline["Response pipeline node"]:::agent
        Crisis["Crisis handler node"]:::agent
        Response["Response generator node"]:::agent
    end

    subgraph Data["Database — Supabase PostgreSQL via Prisma"]
        Sessions["Sessions & messages"]:::data
        Snapshots["Emotion snapshots"]:::data
        Outcomes["Technique outcomes"]:::data
        Summaries["Session summaries"]:::data
        Memory["User memory & profile"]:::data
        Safety["Crisis & audit records"]:::data
    end

    subgraph Providers["External Providers"]
        Gemini["Google Gemini — LLM & audio"]:::providers
        Twilio["Twilio — SMS & WhatsApp crisis"]:::providers
        Speech["Audio transcription"]:::providers
    end

    User --> UI --> ApiClient --> Routes
    Routes --> SmartGate --> Agent
    Agent --> Intake --> Planning
    Planning --> Pipeline
    Planning --> Crisis
    Pipeline --> Response
    Crisis --> Response
    Response --> Persist --> Data
    Data --> Agent
    Routes --> Analytics --> Data
    Agent --> Gemini
    Routes --> Speech
    Crisis --> Twilio
```

### Design Intent

| Layer | Responsibility |
|---|---|
| **Frontend** | Interaction quality, screens, voice controls, user-facing dashboards |
| **API** | HTTP contracts, streaming, authentication boundaries, request orchestration |
| **Pre-graph gate** | Latency protection and safety; separates bypassable turns from full therapeutic analysis |
| **Agent graph** | Emotional reasoning, planning, crisis decisions, response strategy, technique selection |
| **Persistence** | Runs in parallel to keep user latency low |
| **Supabase** | Stores conversational history and analytic signals |
| **Dashboard services** | Transforms raw records into user-facing trend views |

---

## Runtime Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant F as Frontend (Next.js)
    participant A as API (FastAPI)
    participant G as Smart Gate
    participant N as Agent Graph
    participant L as Gemini (LLM + Audio)
    participant D as Supabase DB

    U->>F: Send text or voice message
    F->>A: POST chat request
    A->>G: Lightweight route, distress check, context load
    alt Bypass route allowed
        G->>L: Generate quick response
        G->>D: Save bypass turn (background task)
        G-->>A: Fast payload and metadata
    else Full graph route
        A->>N: Invoke 5-node graph
        N->>L: Parallel intake (crisis, mood, intent, voice)
        N->>L: Analysis and planning (fuse emotion, strategy)
        N->>L: Response pipeline (technique, role)
        N->>L: Response generator (final reply)
        N->>D: Parallel persist (messages, snapshots, outcomes, memory)
        N-->>A: Compiled payload and metadata
    end
    A-->>F: Response text, emotions, technique details
    F-->>U: Render reply, emotion graphics, technique cards
```

### Request Categories

| Request Type | Handling |
|---|---|
| **Text chat** | Standard FastAPI routes through the agent graph |
| **Streaming chat** | Incremental output while keeping persistence intact |
| **Voice chat** | Transcribes audio first, then routes based on transcript meaning |
| **Dashboard requests** | Bypass the agent; read analytic aggregates from Supabase |
| **Crisis actions** | Dedicated safety routes with Twilio-backed integrations |

---

## Pre-Graph Gate

The pre-graph gate is the most important routing layer. It runs before LangGraph and is shared by normal and streaming chat. It is a **staged dispatcher** that leverages parallel database loading and semantic LLM understanding to bypass or run the full graph.

**Core modules:** `agent/graph.py` · `llm/llm_classifier.py` · `utils/turn_lifecycle.py` · `utils/turn_signals.py` · `utils/distress_anchor.py`

```mermaid
flowchart TD
    classDef step fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef parallel fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef decision fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef bypass fill:#F0F9FF,stroke:#0284C7,stroke-width:2px,color:#075985
    classDef fullgraph fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59

    Start["Latest user message"]:::step
    LoadHistory["Load recent message history"]:::step
    UserFacts["User facts"]:::parallel
    SessionSumm["Session summaries"]:::parallel
    SessionFacts["Session facts and techniques"]:::parallel
    GateLLM["Smart pipeline gate — LLM classifier"]:::step
    Normalize["Normalize route labels and flags"]:::step
    FollowupProtect["Contextual follow-up protection"]:::step
    TurnGuess["Initial turn-type guess"]:::step
    VoiceGuard{"Voice or audio data present?"}:::decision
    BypassAllowed{"Bypass confidence high enough?"}:::decision
    Bypass["Fast bypass response"]:::bypass
    FullGraph["Run 5-node agent graph"]:::fullgraph

    Start --> LoadHistory
    LoadHistory --> UserFacts & SessionSumm & SessionFacts
    UserFacts --> GateLLM
    SessionSumm --> GateLLM
    SessionFacts --> GateLLM
    GateLLM --> Normalize --> FollowupProtect --> TurnGuess --> VoiceGuard
    VoiceGuard -- Yes --> FullGraph
    VoiceGuard -- No --> BypassAllowed
    BypassAllowed -- Yes --> Bypass
    BypassAllowed -- No --> FullGraph
```

### Context Loaded by the Pre-Gate

- Latest user message and last few in-memory conversation turns
- Database fallback message history when available
- Stored user context, memory snippets, session summary, facts, and formatted session context
- Latest recommended, pending, rejected, and active technique from session context
- Previous assistant question and expected answer type
- Prior exercise consent and solution preference
- Voice metadata when a voice request already supplied it

### Crisis Pre-Screening

A deterministic safety net checks narrow, high-precision crisis language **before** the LLM router, including:

- Explicit intent to kill oneself, end one's life, or die
- Statements of plan or immediate action
- Means (pills, knife, gun, rope, blade) with intent context
- Recent or current self-harm
- Passive suicidal ideation (e.g. not wanting to exist, wanting to disappear, "everyone better off without me")

### Active Route Labels

`chitchat` · `therapeutic` · `contextual_followup` · `technique_request` · `technique_follow_up` · `memory_query` · `crisis` · `positive_feedback`

### Structured Preference Fields

| Field | Values |
|---|---|
| `exercise_consent` | `unknown` · `denied` · `allowed` |
| `solution_preference` | `unknown` · `listen_only` · `advice_allowed` · `exercise_requested` |
| `suppression_signal` | Whether the user corrected prior history |
| `suppressed_topic` | Topic/person/source the user says not to use |
| `active_issue_source` | Corrected active concern, when provided |

### Gate Normalization and Guardrails

After the LLM responds, the result is normalized and hardened:

- Old route labels are converted to current labels
- `accept_technique` → `technique_follow_up` with an `accept_technique` flag
- `rejection` → `technique_follow_up` with rejection flags
- `list_techniques` → `technique_request` with a `list_techniques` flag
- Unknown routes fall back to `therapeutic`
- Positive outcome language forces `positive_feedback`
- Polite acknowledgement forces `chitchat` unless immediate technique-consent context exists
- Crisis gets high intensity and the full pipeline

### Gate Bypass Routes

```mermaid
flowchart TD
    classDef step fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef decision fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef bypass fill:#F0F9FF,stroke:#0284C7,stroke-width:2px,color:#075985
    classDef fullgraph fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef persist fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    GateResult["Gate result"]:::step
    ConsentBlock{"Prior refusal blocks technique?"}:::decision
    VoicePresent{"Audio or voice features present?"}:::decision
    Route{"Route label"}:::decision
    Bypassed["Bypass handler — chitchat, memory, list, accept, reject, feedback, crisis"]:::bypass
    Full["Full graph — therapeutic route"]:::fullgraph
    Persist["Background persist bypass turn"]:::persist

    GateResult --> ConsentBlock
    ConsentBlock -- Yes --> Full
    ConsentBlock -- No --> VoicePresent
    VoicePresent -- Yes --> Full
    VoicePresent -- No --> Route
    Route -- Recognized bypass --> Bypassed
    Route -- Therapeutic or unresolved --> Full
    Bypassed --> Persist
```

> Bypass is **deliberately disabled for voice turns** — if audio or voice features are present, the system forces the full graph so voice preprocessing and emotion fusion are preserved.

### Full Graph Input State

When bypass is not used, the gate builds the graph state including:

`messages` · `message` · `user_id` · `session_id` · `gate_route` · `gate_confidence` · `gate_context_flags` · `gate_emotional_register` · `gate_intensity_hint` · `gate_should_skip_mood_analysis` · `gate_needs_full_pipeline` · `prefetched_intent` · `prefetched_user_context` · `prefetched_session_context` · `turn_type_guess` · `previous_turn_context` · session message count · voice file path · voice features · transcription confidence · voice feature snapshot

---

## Agent Graph

The agent is intentionally compact: **five graph nodes** with conditional routing between them. The heavy work happens inside specialized node modules while the graph keeps orchestration readable.

```mermaid
flowchart TD
    classDef startend fill:#F5F5F7,stroke:#6C7A89,stroke-width:2px,color:#333
    classDef node fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef decision fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef crisis fill:#FEF2F2,stroke:#DC2626,stroke-width:2px,color:#991B1B

    Start([Start]):::startend
    Intake["1 · run_parallel_intake"]:::node
    CrisisGate{"Early crisis detected?"}:::decision
    Planning["2 · run_analysis_and_planning"]:::node
    NeedsPipeline{"Needs technique selection?"}:::decision
    Pipeline["3 · run_response_pipeline"]:::node
    PipelineCrisis{"Crisis or distress escalated?"}:::decision
    Crisis["4 · handle_crisis"]:::crisis
    Response["5 · generate_response"]:::node
    End([End]):::startend

    Start --> Intake --> CrisisGate
    CrisisGate -- Yes: direct --> Crisis
    CrisisGate -- No --> Planning --> NeedsPipeline
    NeedsPipeline -- No: fast/casual --> Response
    NeedsPipeline -- Yes: therapeutic --> Pipeline --> PipelineCrisis
    PipelineCrisis -- Yes: escalate --> Crisis
    PipelineCrisis -- No --> Response
    Crisis --> Response --> End
```

> The graph has **no LangGraph checkpointer**. It uses `_message_store` for bounded in-memory message history and `_session_context_store` for compact session continuity, reducing serialization overhead and keeping hot-path latency lower.

### Why This Shape Works

- Intake work runs early and in parallel
- Crisis handling is reachable both before and after deeper analysis
- Simple turns skip the expensive response pipeline
- Complex emotional turns receive full planning, memory, technique, and analytics support
- Response generation is the single common exit, keeping assistant style consistent

---

## Node Analysis

### 1. Parallel Intake

`nodes/parallel_intake.py`

```mermaid
flowchart LR
    classDef state fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef node fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef merge fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    State["Initial graph state"]:::state

    subgraph Concurrent["Concurrent tasks"]
        Crisis["screen_for_crisis"]:::node
        Context["load_user_context"]:::node
        Mood["analyze_mood"]:::node
        Intent["intent_pre_check"]:::node
        Voice["preprocess_voice_input"]:::node
    end

    Merge["Merged intake state"]:::merge

    State --> Crisis & Context & Mood & Intent & Voice
    Crisis --> Merge
    Context --> Merge
    Mood --> Merge
    Intent --> Merge
    Voice --> Merge
```

**Responsibilities**

- Skips duplicate crisis LLM when the smart gate already made a confident non-crisis route
- Runs a backup crisis screen when the gate route is uncertain or configured to duplicate crisis checks
- Loads DB-backed user context, summaries, facts, memory, preferences, and chat history
- Runs mood analysis unless the gate marks the turn as low-signal, contextual, memory, chitchat, or voice-authoritative
- Uses voice features as the authoritative mood source when Gemini audio features are present
- Runs intent pre-check only when the smart gate did not already provide authoritative intent
- Preserves distress anchors so contextual replies don't lower the true initial intensity
- Emits emotion, sentiment, intensity, confidence, sub-emotions, symptoms, behaviors, contexts, crisis state, intent, memory context, and voice metadata

**Collaborators:** `context_loader.py` · `intent_classifier.py` · `crisis_detection_node.py` · `memory_extraction_node.py` · `smart_gate_node.py`

---

### 2. Analysis and Planning

`nodes/analysis_and_planning.py`

```mermaid
flowchart TD
    classDef state fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef subnode fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    IntakeState["Intake state"]:::state

    subgraph FusedPlanning["Fused analysis and planning"]
        Fusion["emotion_fusion_node"]:::subnode
        ContextEnrich["context_enrichment"]:::subnode
        Trend["trend_analyzer"]:::subnode
        Clinical["clinical_severity"]:::subnode
        Consent["consent_parser"]:::subnode
        Resolver["context_resolver"]:::subnode
        Planner["conversation_planner"]:::subnode
        Lifecycle["turn_lifecycle.refine"]:::subnode
        Activation["behavioral_activation"]:::subnode
    end

    PlannedState["Planned response state"]:::output

    IntakeState --> Fusion --> ContextEnrich --> Trend --> Clinical --> Consent --> Resolver --> Planner --> Lifecycle --> Activation --> PlannedState
```

**Responsibilities**

- Fuses text and voice emotion into `fused_emotion` and `fused_intensity`
- Applies intensity normalization, neutral caps, hedge-word reduction, and passive-ideation checks
- Detects mismatch and possible masking between text and voice signals
- Enriches context for exam stress, sleep issues, fear-of-failure, catastrophic thought, and environment triggers
- Sets cognitive distortion hints (e.g. catastrophizing) when deterministic context supports it
- Parses consent, suppressed topics, corrected history, active issue source, and solution preference
- Resolves short replies and pronouns against the last assistant question, active thread, and session context
- Refines the lifecycle turn type from the gate's guess into a final `TurnType`

**Strategy outputs:** `no_action` · `validate_only` · `ask_question` · `encourage_reflection` · `reframe` · `suggest_technique` · `distract`

**Phase outputs:** `neutral` · `venting` · `reflection` · `solution` · `recovery`

---

### 3. Response Pipeline

`nodes/response_pipeline.py`

```mermaid
flowchart LR
    classDef state fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef subnode fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    Planned["Planned state"]:::state

    subgraph Fused["Fused response pipeline"]
        Technique["technique_selector_node"]:::subnode
        Role["role_selector"]:::subnode
    end

    PipelineState["Pipeline output state"]:::output

    Planned --> Technique --> Role --> PipelineState
```

**Responsibilities**

- Checks `conversation_strategy` and `technique_readiness`
- Honors exercise consent and listen-only preferences before selecting exercises
- Preserves a pending recommended technique until the user consents
- Searches active DB techniques semantically against emotion, sub-emotion, symptoms, behaviors, and contexts
- Filters out unsuitable or suppressed techniques
- Returns `recommended_technique`, `recommended_techniques_by_category`, `alternative_techniques`, `technique_candidates`, and `latest_recommended_technique`
- Selects communication role from crisis state, fused intensity, trend, and phase

**Role selection rules:**

| Condition | Role |
|---|---|
| Crisis detected | `crisis_support` |
| Worsening trend, intensity ≥ 0.6 | `trainer` |
| Reflection phase | `coach` or `friend` |
| Intensity < 0.4 | `friend` |
| Intensity 0.4–0.7 | `coach` |
| Intensity ≥ 0.7 | `trainer` |

**Collaborators:** `utils/technique_selector.py` · `utils/role_selector.py`

---

### 4. Crisis Handler

`nodes/crisis_handler.py`

**Responsibilities**

- Produces crisis-safe response state
- Avoids ordinary therapeutic technique framing during emergency-like turns
- Connects crisis route metadata to API-level safety features and emergency alerts
- Enforces emergency contact verification and alert dispatch via SMS/WhatsApp
- Preserves auditability for crisis events

**Collaborators:** `services/twilio_crisis.py` · `utils/distress_anchor.py`

---

### 5. Optimized Response Generator

`nodes/optimized_response_generator.py`

**Responsibilities**

- Creates the final assistant response
- Respects route, phase, lifecycle, crisis, and voice-fusion guidance
- Marks `technique_offered_this_turn` **only** when the final message actually offers the selected technique
- Avoids asserting that the user feels differently when text and voice signals conflict

---

## Lifecycle and Outcome Tracking

The lifecycle layer exists because mood analytics become noisy if every turn is treated as the same kind of emotional disclosure. A short "thanks" after a technique should not be scored like a new distress report, and a context-only answer should not distort mood-improvement graphs.

```mermaid
flowchart LR
    classDef input fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef node fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef type fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    UserTurn["User turn — text or voice"]:::input
    Lifecycle["Turn lifecycle classifier"]:::node

    subgraph TurnTypes["Turn type classification"]
        Initial["INITIAL_DISCLOSURE"]:::type
        FollowUp["FOLLOW_UP_DISCLOSURE"]:::type
        Context["CONTEXT_GATHERING"]:::type
        Reaction["POST_RECOMMENDATION_REACTION"]:::type
        CrisisTurn["CRISIS_DISCLOSURE"]:::type
    end

    Snapshot["EmotionSnapshot recorded"]:::output
    Dashboard["Mood and outcome analytics"]:::output

    UserTurn --> Lifecycle
    Lifecycle --> Initial & FollowUp & Context & Reaction & CrisisTurn
    Initial & FollowUp & Context & Reaction & CrisisTurn --> Snapshot --> Dashboard
```

### Turn Type Reference

| Turn Type | Meaning |
|---|---|
| `INITIAL_DISCLOSURE` | First meaningful emotional disclosure in a session |
| `FOLLOW_UP_DISCLOSURE` | A later emotional update in the same session |
| `CONTEXT_GATHERING` | User is answering facts or logistics; no new mood signal |
| `POST_RECOMMENDATION_REACTION` | User is reacting after a technique or recommendation |
| `CRISIS_DISCLOSURE` | Turn contains crisis-level safety concerns |

### Outcome Flow

```mermaid
flowchart TD
    classDef input fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef decision fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef node fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    AssistantReply["Assistant reply"]:::input
    TechniqueOffered{"Technique actually offered?"}:::decision
    Pending["Create pending TechniqueOutcome"]:::node
    LaterTurn["Later eligible user turn"]:::input
    Evidence{"Follow-through or reaction?"}:::decision
    Resolve["Resolve: effectiveness, followThrough, confidence"]:::node
    KeepPending["Keep pending"]:::node
    Analytics["Dashboard analytics"]:::output

    AssistantReply --> TechniqueOffered
    TechniqueOffered -- Yes --> Pending --> LaterTurn --> Evidence
    TechniqueOffered -- No --> Analytics
    Evidence -- Yes --> Resolve --> Analytics
    Evidence -- No --> KeepPending --> Analytics
```

This enables meaningful questions such as:

- Did the user's intensity decrease after an actual technique offer?
- Was there enough follow-through evidence to score the technique?
- Is the dashboard comparing real disclosures instead of polite acknowledgements?
- Did the session peak improve by the final qualifying emotional snapshot?

---

## Voice and Emotion Fusion

Voice handling is **route-aware**. The system transcribes audio and captures voice feature signals, but voice emotion is not forced into every route. The transcript drives routing first; voice features are linked into therapeutic or crisis processing when that route supports emotion fusion.

```mermaid
flowchart TD
    classDef input fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef decision fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef node fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    Audio["Audio upload"]:::input
    Transcribe["Gemini transcription"]:::node
    VoiceFeatures["Voice feature snapshot"]:::node
    SmartRoute["Smart gate routing"]:::node
    Therapeutic{"Therapeutic or crisis route?"}:::decision
    Fusion["Emotion fusion node"]:::node
    Mismatch["Mismatch / possible masking detected"]:::node
    ResponsePrompt["Response guidance"]:::output

    Audio --> Transcribe --> SmartRoute
    Audio --> VoiceFeatures
    SmartRoute --> Therapeutic
    Therapeutic -- Yes --> Fusion
    Therapeutic -- No: bypass or casual --> ResponsePrompt
    VoiceFeatures --> Fusion --> Mismatch --> ResponsePrompt
```

**Persisted fusion metadata:** text/voice mismatch · possible masking · fusion confidence · transcription confidence · voice feature snapshot · conversation phase · response strategy

> The response prompt instructs the model to acknowledge uncertainty and **never assert that the user feels something different from what they said**.

---

## Crisis Safety

```mermaid
flowchart TD
    classDef input fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef decision fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef crisis fill:#FEF2F2,stroke:#DC2626,stroke-width:2px,color:#991B1B
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    Input["User input — text or voice"]:::input
    PreScreener{"LLM crisis pre-screener"}:::decision
    GraphCheck{"Graph intake recheck"}:::decision
    CrisisPath["Crisis handler node"]:::crisis
    SafetyResponse["Grounded safety response"]:::output
    Resources["Localized help & resources"]:::output
    Twilio["Twilio SMS / WhatsApp alerting"]:::output
    Audit["Crisis audit records"]:::output

    Input --> PreScreener
    PreScreener -- High or medium risk --> CrisisPath
    PreScreener -- Low or none --> GraphCheck
    GraphCheck -- Escalation detected --> CrisisPath
    GraphCheck -- Normal turn --> SafetyResponse
    CrisisPath --> SafetyResponse & Resources & Twilio & Audit
```

**Crisis features**

- Context-aware LLM-based crisis pre-screener in the pre-graph gate
- Parallel intake validation check inside the graph as a redundant fail-safe
- Dedicated crisis handler node managing distress peaks and emergency escalation
- Stored emergency contact integration with automatic Twilio (SMS/WhatsApp) alerts
- Secure crisis audit database logs for clinical compliance and dashboard tracking
- Safety-first grounded response templates generated by the response node

---

## Memory and Personalization

SentiMind uses several memory layers so the assistant remains continuous without treating every message as isolated.

```mermaid
flowchart LR
    classDef client fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef agent fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef data fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    Message["Conversation message"]:::client

    subgraph MemoryLayers["Memory and personalization layers"]
        Explicit["Explicit user facts"]:::data
        Semantic["Semantic memory — embeddings"]:::data
        Summary["Session summary & analytics"]:::data
        Profile["Psychological profile"]:::data
        Handoff["Structured session handoff"]:::data
    end

    NextSession["Next session context intake"]:::agent

    Message --> Explicit & Semantic & Summary
    Summary --> Handoff
    Explicit --> NextSession
    Semantic --> NextSession
    Profile --> NextSession
    Handoff --> NextSession
```

| Module | Responsibility |
|---|---|
| `memory/explicit_facts.py` | Extracts durable facts and stores them in the DB |
| `memory/semantic_memory.py` | Coordinates embedding-based search for past topic matches |
| `nodes/session_saver.py` | Updates dynamic user profile metadata, session summaries, and structured handoffs |
| `agent/graph.py` (pre-graph loader) | Injects relevant prior-session context into the smart gate |

---

## Dashboard Analytics

Dashboard analytics intentionally **ignore noisy turn types** when calculating improvement. This is where lifecycle tagging directly improves product accuracy.

```mermaid
flowchart TD
    classDef input fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef filter fill:#FEF3C7,stroke:#D97706,stroke-width:2px,color:#78350F
    classDef node fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef api fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef ui fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    Records["Raw tables — mood logs, snapshots, outcomes"]:::input
    Filter["Qualifying turn filter"]:::filter
    Trends["Mood and intensity trends"]:::node
    Techniques["Technique effectiveness"]:::node
    Profile["Profile and pattern segments"]:::node
    DashboardAPI["Dashboard API router"]:::api
    UI["Next.js dashboard UI"]:::ui

    Records --> Filter --> Trends
    Records --> Techniques
    Records --> Profile
    Trends --> DashboardAPI
    Techniques --> DashboardAPI
    Profile --> DashboardAPI
    DashboardAPI --> UI
```

**Qualifying mood records:** `INITIAL_DISCLOSURE` · `FOLLOW_UP_DISCLOSURE` · `POST_RECOMMENDATION_REACTION` · `CRISIS_DISCLOSURE` · legacy `MoodLog` records

**Excluded from improvement-trend scoring:** `CONTEXT_GATHERING` · Short acknowledgements without outcome evidence · Assistant technique offers with no later user reaction

---

## Database Design

```mermaid
flowchart TB
    classDef user fill:#FFF1F2,stroke:#F43F5E,stroke-width:2px,color:#881337
    classDef convo fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef wellness fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef memory fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59
    classDef safety fill:#FEF2F2,stroke:#DC2626,stroke-width:2px,color:#991B1B

    User["User entity"]:::user

    subgraph Conversation["Conversation domain"]
        Session["Session — active/peak tracking"]:::convo
        Message["Message — conversational history"]:::convo
        EmotionSnapshot["EmotionSnapshot — turn-level fused emotion"]:::convo
        SessionSummary["SessionSummary — final summary, handoff"]:::convo
    end

    subgraph Wellness["Wellness and technique domain"]
        MoodLog["MoodLog — self-reports"]:::wellness
        TechniqueOutcome["TechniqueOutcome — pending/resolved"]:::wellness
        UserTechniquePreference["UserTechniquePreference — consent"]:::wellness
        PsychProfile["PsychProfile — trait tracking"]:::wellness
    end

    subgraph MemoryDomain["Memory domain"]
        UserMemory["UserMemory — long-term profile"]:::memory
        SemanticMemory["SemanticMemory — embeddings"]:::memory
        ExplicitFact["ExplicitFact — extracted facts"]:::memory
    end

    subgraph SafetyDomain["Safety and audit domain"]
        CrisisEvent["CrisisEvent — trigger logs"]:::safety
        CrisisResource["CrisisResource — help desks"]:::safety
        TrustedContact["TrustedContact — emergency verification"]:::safety
        AuditLog["AuditLog — admin/usage audits"]:::safety
    end

    User --> Session
    Session --> Message & EmotionSnapshot & SessionSummary
    User --> MoodLog & TechniqueOutcome & UserTechniquePreference & PsychProfile
    User --> UserMemory & SemanticMemory & ExplicitFact
    User --> CrisisEvent & TrustedContact & AuditLog
    CrisisEvent --> CrisisResource
```

### Schema Reference

| Table | Purpose |
|---|---|
| `Session` | Session state, mood summary, peak intensity tracking |
| `Message` | User and assistant messages plus technique-offer flags |
| `EmotionSnapshot` | Emotion, intensity, lifecycle type, fusion metadata, technique linkage |
| `TechniqueOutcome` | Pending and resolved intervention outcomes |
| `SessionSummary` | Final emotion, final intensity, turn-type counts, handoff data |
| `MoodLog` | Explicit mood logging and legacy trend support |
| Memory tables | User facts, semantic memories, profile signals |
| Crisis/audit tables | Safety and compliance-oriented records |

---

## API Surface

### Chat and Pipeline

```mermaid
flowchart TD
    classDef client fill:#FFF1F2,stroke:#F43F5E,stroke-width:2px,color:#881337
    classDef route fill:#FDF4FF,stroke:#D946EF,stroke-width:1px,color:#701A75
    classDef node fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef main fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef output fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    ChatClient["Chat UI or API client"]:::client
    Entry{"Chat endpoint"}:::route
    Audio["Voice transcriber & emotion extractor"]:::node
    SmartGate["Smart gate & early crisis router"]:::node
    Graph["5-node agent graph"]:::main
    Persist["Parallel background persistence"]:::main
    Response["ChatResponse or SSE stream"]:::output

    ChatClient --> Entry
    Entry -- Text or stream --> SmartGate
    Entry -- Voice --> Audio --> SmartGate
    Entry -- Diagnostic pipeline --> SmartGate
    SmartGate --> Graph --> Persist --> Response
```

| Method | Route | Handler |
|---|---|---|
| GET | `/` | `root` |
| GET | `/health` | `health_check` |
| POST | `/api/chat` | `chat` |
| POST | `/api/chat/stream` | `chat_stream` |
| POST | `/api/chat/voice` | `chat_voice` |
| POST | `/api/pipeline/complete` | `pipeline_complete` |

### Authentication and User Bootstrap

| Method | Route | Handler |
|---|---|---|
| POST | `/api/user/create` | `create_user` |
| POST | `/api/auth/signup` | `auth_signup` |
| POST | `/api/auth/login` | `auth_login` |
| POST | `/api/user/ensure` | `ensure_user` |

### Sessions

| Method | Route | Handler |
|---|---|---|
| GET | `/api/user/{user_id}/sessions` | `get_user_sessions` |
| GET | `/api/session/{session_id}/messages` | `get_session_messages` |
| PATCH | `/api/session/{session_id}/rename` | `rename_session` |
| DELETE | `/api/session/{session_id}` | `delete_session` |
| POST | `/api/session/new` | `create_new_chat_session` |

### Dashboard and Profile

| Method | Route | Handler |
|---|---|---|
| GET | `/api/dashboard/user/{user_id}` | `get_user_dashboard` |
| GET | `/dashboard/user/{user_id}` | `dashboard_user_direct_no_api_prefix` |
| GET | `/api/dashboard/health` | `dashboard_health` |
| GET | `/api/dashboard/stats` | `get_dashboard_stats` |
| GET | `/api/user/{user_id}/stats` | `get_user_stats_legacy` |
| GET | `/api/user/{user_id}/profile` | `get_user_profile` |

### Settings, Onboarding, Consent, Data Rights

| Method | Route | Handler |
|---|---|---|
| POST | `/api/user/settings` | `save_user_settings` |
| POST | `/api/user/onboarding` | `save_onboarding` |
| DELETE | `/api/user/{user_id}` | `delete_user_account` |
| POST | `/api/user/{user_id}/consent` | `record_consent` |
| POST | `/api/user/{user_id}/consent/withdraw` | `withdraw_consent` |
| GET | `/api/user/{user_id}/data-export` | `export_user_data` |
| DELETE | `/api/user/{user_id}/data` | `delete_user_data` |

### Techniques and Wellness

| Method | Route | Handler |
|---|---|---|
| GET | `/api/wellness/tips` | `get_wellness_tips` |
| GET | `/api/techniques` | `get_techniques` |
| POST | `/api/technique/rate` | `rate_technique` |

### Crisis Router — `/api/crisis`

```mermaid
flowchart TD
    classDef client fill:#FFF1F2,stroke:#F43F5E,stroke-width:2px,color:#881337
    classDef main fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef ext fill:#FFF7ED,stroke:#F97316,stroke-width:2px,color:#9A3412
    classDef audit fill:#ECFDF5,stroke:#059669,stroke-width:2px,color:#065F46

    CrisisUI["Crisis UI, safety trigger, or Twilio webhook"]:::client
    Endpoints["Crisis gateway routes"]:::main
    CrisisServices["Crisis resource & country services"]:::main
    TwilioService["Twilio SMS & WhatsApp dispatchers"]:::ext
    Audit["Crisis audit logging"]:::audit

    CrisisUI --> Endpoints
    Endpoints --> CrisisServices & TwilioService
    CrisisServices --> Audit
    TwilioService --> Audit
```

| Method | Route | Handler |
|---|---|---|
| POST | `/api/crisis/resources` | `get_resources` |
| POST | `/api/crisis/detect-country` | `detect_country` |
| POST | `/api/crisis/initiate-call` | `initiate_crisis_call` |
| POST | `/api/crisis/send-sms` | `send_crisis_sms` |
| GET | `/api/crisis/call-status/{call_sid}` | `get_call_status` |
| GET | `/api/crisis/health` | `crisis_health` |
| POST | `/api/crisis/pakistan/alert` | `alert_pakistan_crisis_center` |
| POST | `/api/crisis/pakistan/whatsapp-alert` | `alert_pakistan_whatsapp` |
| POST | `/api/crisis/twilio/response` | `handle_twilio_response` |
| POST | `/api/crisis/twilio/status` | `handle_twilio_status` |
| POST | `/api/crisis/test-whatsapp-alert` | `test_whatsapp_alert` |
| POST | `/api/crisis/send-location` | `send_location_alert` |
| POST | `/api/crisis/send-location-auto` | `send_location_auto` |

### Active Frontend API Calls

The frontend API base is `NEXT_PUBLIC_API_URL`, defaulting to `http://localhost:8000/api`.

**Auth:** NextAuth credentials provider calls `POST /api/auth/signup`, `POST /api/auth/login`, and auth server action calls `POST /api/user/ensure`.

**Chat:** Streaming chat calls `POST /api/chat/stream`. Browser crisis GPS helper calls `POST /api/crisis/send-location`. Session actions call the session list, message list, rename, and delete routes.

**Profile and onboarding:** Profile action calls `GET /api/user/{user_id}/profile`, `POST /api/user/settings`, `GET /api/user/{user_id}/data-export`, `POST /api/user/{user_id}/consent/withdraw`, and (legacy) `DELETE /api/user/{user_id}`. Onboarding action calls `POST /api/user/onboarding`.

> **Known route mismatch:** `frontend/src/actions/profile.ts` references `POST /api/user/erasure-request`, but no matching FastAPI route is currently registered. The correct backend data-deletion route is `DELETE /api/user/{user_id}/data`.

---

## Frontend Architecture

```mermaid
flowchart TB
    classDef client fill:#EEF2FF,stroke:#6366F1,stroke-width:2px,color:#1E1B4B
    classDef main fill:#FDF4FF,stroke:#D946EF,stroke-width:2px,color:#701A75
    classDef backend fill:#F0FDFA,stroke:#0D9488,stroke-width:2px,color:#115E59

    AppRouter["Next.js App Router"]:::client
    Pages["Route pages — chat, dashboard, profile"]:::client
    Components["Reusable UI components"]:::client
    Hooks["Custom hooks — useAudio, useChat"]:::client
    Lib["API and utility layer"]:::client
    Contexts["Context providers — auth, theme"]:::client
    Backend["FastAPI backend"]:::backend

    AppRouter --> Pages --> Components
    Components --> Hooks --> Lib --> Backend
    Components --> Contexts
```

### Pages

| Page | Path |
|---|---|
| Chat | `/chat` and `/chat/[sessionId]` |
| Dashboard | `/dashboard` |
| Profile | `/profile` |
| Crisis | `/crisis` |
| Auth | `/login` and `/signup` |
| Onboarding | `/onboarding` |
| Info | `/` · `/privacy` · `/terms` |

**Key folders:** `frontend/src/app` · `frontend/src/components` · `frontend/src/hooks` · `frontend/src/lib` · `frontend/src/contexts` · `frontend/src/types`

---

## Repository Structure

```
FYP/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── contexts/
│   │   └── types/
│   └── package.json
│
├── mental_health_wellness/
│   ├── api_server.py
│   ├── prisma/
│   │   └── schema.prisma
│   ├── src/mental_health_wellness/
│   │   ├── agent/
│   │   ├── api/
│   │   ├── nodes/
│   │   ├── services/
│   │   └── utils/
│   └── tests/
│
└── README.md
```

---

## Environment Variables

### Backend

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Prisma primary connection string |
| `DIRECT_URL` | Prisma direct connection for migrations |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_API_KEY` | Google API key (audio/transcription) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio originating phone number |
| `ENVIRONMENT` | Runtime environment (`development` / `production`) |
| `LOG_LEVEL` | Logging verbosity |
| `FRONTEND_URL` | CORS allowed origin |

### Frontend

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key |

> **Security:** Never commit secrets to source control. Use local `.env` files or your deployment provider's secret management.

---

## Setup

### Backend

```powershell
cd E:\FYP\mental_health_wellness
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m prisma generate
```

### Frontend

```powershell
cd E:\FYP\frontend
npm install
```

---

## Running the Project

### Backend — `http://localhost:8000`

```powershell
cd E:\FYP\mental_health_wellness
python -m api_server
```

### Frontend — `http://localhost:3000`

```powershell
cd E:\FYP\frontend
npm run dev
```

---

## Validation

### Backend Checks

```powershell
cd E:\FYP
python -m py_compile mental_health_wellness\src\mental_health_wellness\agent\graph.py
python -m py_compile mental_health_wellness\src\mental_health_wellness\nodes\optimized_response_generator.py
pytest -q mental_health_wellness\tests
```

### Lifecycle and Voice Checks

```powershell
cd E:\FYP
pytest -q mental_health_wellness\tests\test_lifecycle_outcome_layer.py
pytest -q mental_health_wellness\tests\test_voice_authoritative.py
pytest -q mental_health_wellness\tests\test_context_complete_technique_gate.py
pytest -q mental_health_wellness\tests\test_short_acknowledgement_context.py
```

### Frontend Checks

```powershell
cd E:\FYP\frontend
npm run lint
npm run build
```

### Manual Smoke Test

1. Start backend and frontend
2. Send an initial emotional disclosure → confirm `INITIAL_DISCLOSURE` is stored
3. Continue with a follow-up emotional update → confirm `FOLLOW_UP_DISCLOSURE` is stored
4. Provide enough context for a technique offer → confirm the assistant message has `techniqueOfferedThisTurn: true`
5. Reply with a real reaction after trying it → confirm the pending `TechniqueOutcome` resolves
6. Open the dashboard → verify the mood trend excludes context-only turns

---

## Operational Notes

- Do not run multiple backend servers on port `8000`
- If Prisma reports a query-engine mismatch, regenerate with `python -m prisma generate`
- If Supabase schema changes are made manually, keep `schema.prisma` synchronized
- Additive enum migrations can leave legacy enum values in PostgreSQL; app normalization handles the known old `POST_RECOMMENDATION` value
- Runtime logs and generated reports should not be treated as source documentation
- The real Python test suite under `mental_health_wellness/tests` should be kept

---

## Credits

<div align="center">

**Developer:** Taha Mehmood &nbsp;·&nbsp; **Co-Developer:** Hasnain Gul

</div>
