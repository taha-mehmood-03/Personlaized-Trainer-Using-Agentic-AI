<div align="center">
  
# 🧠 SentiMind v5.0: Deterministic Hybrid Mental Health Agent

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Architecture-orange.svg)](https://python.langchain.com/docs/langgraph)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Ready-336791.svg?logo=postgresql)](https://www.postgresql.org/)
[![Prisma](https://img.shields.io/badge/Prisma-ORM-2D3748.svg?logo=prisma)](https://www.prisma.io/)

</div>

Welcome to **SentiMind v5.0**, a state-of-the-art mental health support AI built on a **Deterministic Hybrid Architecture** using LangGraph. Unlike traditional "ReAct" LLM agents that loop arbitrarily and incur high latency and token costs, SentiMind offloads critical reasoning and safety logic to fast, deterministic Python nodes and local Machine Learning models. The LLM is invoked **exactly once** at the end of the pipeline purely for natural language generation.

This repository structure and architecture guarantee a safer, cheaper, faster, and highly empathetic mental health intervention system.

---

## � Key Features

*   **Hybrid Intelligence:** Combines the strict safety of deterministic Python functions with the conversational empathy of Llama 3.1.
*   **Zero-Hallucination Crisis Detection (Two-Layer):** Hard-coded keyword pre-screening and DistilBERT/ELECTRA emotion classification intercept severe distress (e.g., self-harm). Now features a latency-saving gate that bypasses the 70B LLM check if the local model is extremely confident in user safety.
*   **Chitchat Fast-Path (Sub-Second Latency):** A conditional router bypasses the entire therapeutic pipeline (cognitive distortion checks, technique DB lookups) if the initial nodes detect casual chitchat, vastly improving response times for non-clinical messages.
*   **Sub-Second NLP:** Uses local HuggingFace `distilroberta-base` for sub-second 7-dimensional emotion tracking without wasting paid API tokens.
*   **Semantic Memory Retrieval:** Utilizes ChromaDB to recall specific past user discussions to inform the current context (RAG).
*   **Determinc Crisis Routing:** Router validates both high emotional intensity (>= 0.8) *and* negative valence (sadness, fear, anger) to prevent false-positive crisis alerts for high-intensity joy.
*   **Clinical Technique Database:** Uses PostgreSQL to recommend DB-curated coping strategies (e.g., Box Breathing, CBT re-framing) matched dynamically to user mood.
*   **Voice-Emotion Ready:** Built-in hooks for merging acoustic voice analysis (arousal/valence) with text sentiment.
*   **GDPR Compliant:** Comprehensive data pipelines mapped for explicit consent, Right to Access (data export), and Right to Erasure (cascade deletion).

---

## 🏗️ Architecture Overview & Decision Flow

The core system is built on **LangGraph** and executes a strict 14-node deterministic pipeline.

### 1. The Core Graph Pipeline (LangGraph)
```mermaid
graph TD
    %% Node Styling
    classDef llmNode fill:#ffcc00,stroke:#333,stroke-width:2px,color:black,stroke-dasharray: 5 5;
    classDef pythonNode fill:#69b3a2,stroke:#333,stroke-width:2px,color:white;
    classDef dbNode fill:#4db8ff,stroke:#333,stroke-width:2px,color:black;
    classDef crisisNode fill:#ff4d4d,stroke:#333,stroke-width:3px,color:white;

    START --> PreScreener[1. Crisis Pre-Screener]
    
    PreScreener -- "Keywords Found" --> CrisisHandler
    PreScreener -- "Safe" --> Intake[2. Intake Node]:::dbNode
    
    Intake --> MoodAnalyzer[3. Mood Analyzer]:::pythonNode
    MoodAnalyzer --> EmotionFusion[4. Emotion Fusion]:::pythonNode
    EmotionFusion --> CognitiveDistortion[5. Cognitive Distortion]:::pythonNode
    CognitiveDistortion --> TrendAnalyzer[6. Trend Analyzer]:::dbNode
    TrendAnalyzer --> ConversationPlanner[7. Conversation Planner]:::pythonNode
    ConversationPlanner --> BehavioralActivation[8. Behavioral Activation]:::pythonNode
    BehavioralActivation --> TechniqueSelector[9. Technique Selector]:::dbNode
    TechniqueSelector --> CrisisRouter{"10. Router\nIntensity >= 0.8?"}
    
    CrisisRouter -- "Yes / Distress" --> CrisisHandler[12b. Crisis Handler]:::crisisNode
    CrisisRouter -- "No / Normal" --> RoleSelector[11. Role Selector]:::pythonNode
    
    RoleSelector --> ResponseGenerator[12a. Response Generator]:::llmNode
    
    ResponseGenerator --> PsychProfileUpdater[13. Psych Profile Updater]:::dbNode
    CrisisHandler --> PsychProfileUpdater
    
    PsychProfileUpdater --> SessionSaver[14. Session Saver]:::dbNode
    SessionSaver --> OutcomeTracker[15. Outcome Tracker]:::dbNode
    OutcomeTracker --> END

    %% Legend
    subgraph Legend
        n1[Python Logic Node]:::pythonNode
        n2[Database / Retrieval Node]:::dbNode
        n3[Single LLM Call]:::llmNode
        n4[Hard-Coded Crisis Response]:::crisisNode
    end
```

### 2. API Request Lifecycle (Sequence Flow)
```mermaid
sequenceDiagram
    participant User/Client
    participant FastAPI (api_server)
    participant Prisma (PostgreSQL)
    participant LangGraph Agent
    participant DistilBERT (Local NLP)
    participant Groq/Llama3.1 (LLM)

    User/Client->>FastAPI (api_server): POST /api/chat {message, session_id}
    FastAPI (api_server)->>Prisma (PostgreSQL): Verify/Create User & Session
    Prisma (PostgreSQL)-->>FastAPI (api_server): session_id confirmed
    
    FastAPI (api_server)->>LangGraph Agent: invoke(message)
    
    rect rgb(240, 248, 255)
        Note right of LangGraph Agent: DETERMINISTIC PRE-PROCESSING
        LangGraph Agent->>Prisma (PostgreSQL): Fetch history & profile (Intake)
        LangGraph Agent->>DistilBERT (Local NLP): Classify Emotion (MoodAnalyzer)
        DistilBERT (Local NLP)-->>LangGraph Agent: {emotion: Anxiety, intensity: 0.6}
        LangGraph Agent->>LangGraph Agent: Detect CBT Distortions & Plan Strategy
        LangGraph Agent->>Prisma (PostgreSQL): Fetch best technique for Anxiety
    end

    rect rgb(255, 245, 238)
        Note right of LangGraph Agent: LLM GENERATION (Exactly 1 Call)
        LangGraph Agent->>Groq/Llama3.1 (LLM): Generate prose based on strict rules
        Groq/Llama3.1 (LLM)-->>LangGraph Agent: Empathetic narrative response
    end
    
    LangGraph Agent->>Prisma (PostgreSQL): Save Message, Emotion metrics, Phase
    LangGraph Agent-->>FastAPI (api_server): Final Payload
    FastAPI (api_server)-->>User/Client: {response, emotion, techniques}
```

### 🧠 The Node-by-Node Breakdown (LangGraph Pipeline)

1. **`crisis_pre_screener_node` (Safety Net):** Runs **before** everything. Uses hard-coded keywords (Layer 1) and a specialist ELECTRA model (Layer 2) to catch self-harm language. Bypasses the 70B LLM if ELECTRA confidence of safety is very high to save 3-5 seconds of latency.
2. **`intake_node`:** Loads user context, history, session data (from PostgreSQL), and relevant past memories via ChromaDB semantic search.
3. **`mood_analyzer_node`:** Local DistilBERT emotion detection pipeline. *Does not use the LLM.* Classifies emotion across 7 dimensions + sentiment and intensity.
4. **`emotion_fusion_node`:** Merges text-based emotion with voice emotion to produce a fused, holistic emotional profile.
5. **`cognitive_distortion_node`:** *[v3 NEW]* Pure Python logic detecting CBT (Cognitive Behavioral Therapy) distortion patterns.
6. **`trend_analyzer_node`:** Analyzes past interactions via SQL to plot an emotional trajectory (improving, worsening, stable).
7. **`conversation_planner_node`:** The strategic decision-maker. Determines the core intervention strategy. Evaluates intent using an 8B LLM. Also incorporates a "Chitchat Bypass Gate" to skip therapeutic steps if the message is purely casual.
8. **`behavioral_activation_node`:** *[v3 NEW]* Proposes real-world micro-actions based on current emotional status.
9. **`technique_selector_node`:** Queries PostgreSQL via Prisma to select a coping technique based on mood and past success ratings.
10. **`role_selector_node`:** Sets the "Persona" (Friend, Coach, Trainer) based on emotional intensity trends.
11. **`response_generator_node`:** The **ONLY** LLM call in the normal pipeline. Uses a densely packed prompt to generate an empathetic narrative matching the chosen strategy, persona, and technique.
12. **`crisis_handler_node`:** Alternative to `response_generator`. Triggers hard-coded template responses with emergency resources (988 lifeline). *Zero hallucinations.*
13. **`psych_profile_updater_node`:** *[v3 NEW]* Persistently updates the user's ongoing psychological/behavioral model.
14. **`session_saver_node`:** Asynchronously persists session state, conversation phase, and summary.
15. **`outcome_tracker_node`:** Triggers post-session logic relating to how well techniques performed over time.

---

## 🗄️ Database Schema & Entities (ER Diagram)

Driven by **Prisma** (PostgreSQL), the core data structure establishes a robust foundation for long-term user tracking and personalized psychological profiling:

```mermaid
erDiagram
    USER ||--o{ SESSION : has
    USER ||--o| USER_STATISTICS : tracks
    USER ||--o| PSYCH_PROFILE : develops
    USER ||--o{ DAILY_CHECK_IN : logs
    
    SESSION ||--o{ MESSAGE : contains
    SESSION ||--o{ EMOTION_SNAPSHOT : captures
    
    MESSAGE }o--o| TECHNIQUE : "may recommend"
    
    TECHNIQUE_CATEGORY ||--o{ TECHNIQUE : categorizes
    USER ||--o{ USER_TECHNIQUE_RATING : submits
    TECHNIQUE ||--o{ USER_TECHNIQUE_RATING : receives
    
    USER {
        String id PK
        String email
        String name
        Boolean consentGiven
    }
    SESSION {
        String id PK
        String title
        Enum status
        Enum phase
    }
    MESSAGE {
        String id PK
        Enum role
        Text content
        Enum emotion
        Float intensity
    }
    PSYCH_PROFILE {
        String id PK
        String copingStyle
        Float resilienceScore
        Float anxietyBaseline
    }
    TECHNIQUE {
        String id PK
        String name
        Int durationMinutes
        Float avgRating
    }
```

### Key Entity Relationships
*   **`User` & `PsychProfile`**: A 1-to-1 mapping that continuously evolves as the user interacts, tracking coping styles and cognitive distortions over time.
*   **`Session` & `Message`**: Relational store tracing user inputs against the Agent's responses, logging timestamped emotion metrics for every interaction.
*   **`Technique` & `Category`**: A normalized catalog of therapeutic coping strategies, recording average success rates and assigned difficulty.
*   **`UserTechniqueRating`**: Logs user feedback post-technique to optimize future recommendations dynamically based on success.

---

## 🤖 Models & AI Infrastructure

SentiMind segregates duties effectively to the best tool for the job.

*   **Emotion Detection:** `distilroberta-base` (HuggingFace Transformers, local execution). Used in `mood_analyzer_node` to categorize 7 emotions reliably in ~400ms.
*   **Memory / Embeddings:** `all-MiniLM-L6-v2` with **ChromaDB**. Embeds text for high-fidelity semantic RAG without blowing up LLM context.
*   **Voice Processing:** Uses `opensmile`, `librosa`, and `torchaudio` for parsing acoustic features of emotional state.
*   **Text Generation (LLM):** `Groq API` featuring **Llama 3.1** (or fallback providers). Responsible *only* for empathetic rendering.

---

## 🔌 API Endpoints Overview

The `api_server.py` FastAPI application exposes the following primary endpoints:

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/api/chat` | `POST` | Core agent interaction endpoint. Accepts text input and returns the generated agent response along with emotion data and recommended techniques. |
| `/api/user/create` | `POST` | Provisions a new user in the PostgreSQL database with default stats and preferences. |
| `/api/user/ensure` | `POST` | Checks if a user ID exists, initializing an anonymous user footprint if not found. |
| `/api/user/{id}/sessions` | `GET` | Retrieves the conversation history divided by distinct check-in sessions. |
| `/api/techniques` | `GET` | Fetches the clinical repertoire of coping techniques, optionally filtered by target emotion. |
| `/api/technique/rate` | `POST` | Records user feedback (1-5 stars) on a technique to influence future AI recommendations. |
| `/api/user/{id}/data-export`| `GET` | **GDPR:** Compiles a full JSON payload of all user data stored across the relational databases. |

---

## � Example Usage

### Chatting with the Agent
Using `curl` to interact with the mental health agent:

```bash
curl -X POST "http://localhost:8000/api/chat" \
     -H "Content-Type: application/json" \
     -d '{
           "user_id": "usr_12345",
           "session_id": "sess_9876",
           "message": "I feel extremely overwhelmed with my upcoming finals. I cannot focus at all."
         }'
```

**Expected JSON Response:**
```json
{
  "response": "I can hear how overwhelmed you are right now, and it's completely valid to feel that way with finals approaching. That kind of pressure is heavy. Let's take a small step back together. Would you be open to trying a quick 5-minute Box Breathing exercise to help steady your focus before diving back in?",
  "session_id": "sess_9876",
  "emotion": "anxiety",
  "crisis_detected": false,
  "tools_used": ["mood_analyzer", "technique_selector"],
  "recommended_techniques_by_category": {
    "Breathing": {
      "id": "tech_box_breath",
      "name": "Box Breathing",
      "duration_minutes": 5
    }
  },
  "timestamp": "2026-03-09T12:00:00Z"
}
```

---

## �🛠️ Tech Stack & Integrations

*   **Backend:** FastAPI (Powers the API orchestration layer).
*   **Graph/Agent Execution:** LangGraph, LangChain.
*   **Database:** PostgreSQL with **Prisma ORM**.
*   **Checkpointer:** PostgreSQL `langgraph-checkpoint-postgres`.
*   **Vector Database:** ChromaDB.

---

## 📁 Repository Structure

```bash
mental_health_wellness/
├── api_server.py                 # FastAPI App entrypoint and endpoints.
├── prisma/                       # Prisma Schema and migrations.
├── docs/                         # Project architecture & comparison docs.
├── requirements.txt              # Pipeline dependencies.
└── src/mental_health_wellness/
    ├── agent/
    │   ├── graph.py              # The LangGraph layout & Router config.
    │   └── state.py              # Central `MentalHealthState` TypedDict.
    ├── nodes/                    # Each node exists as an isolated module here.
    ├── db/                       # Prisma client initialization & db ops.
    ├── memory/                   # ChromaDB semantic retrieval logic.
    ├── tools/                    # ReAct fallback tools (crisis, mood, voice, tech).
    └── utils/                    # Helper scripts.
```

---

## 🚀 Setup & Installation

### 1. Environment Setup

*   Ensure Python 3.10+ is installed.
*   Install PostgreSQL and ensure the daemon is running.

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file referencing the structure of your system:
```ini
# Add API Keys
GROQ_API_KEY="your_groq_key"
OPENAI_API_KEY="your_optional_openai_key"

# Database Configuration
DATABASE_URL="postgresql://user:password@localhost:5432/sentimind"
```

### 3. Database Initialization (Prisma)

```bash
# Generate the Prisma Client
prisma generate

# Push schema to database
prisma db push
```

### 4. Running the Application

```bash
# SentiMind will automatically preload all ML models on boot 
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🤝 For Collaborators

If you are expanding functionality:
1. **Never put reasoning into the LLM.** If a decision must be made (e.g., "should I mention eating disorders?"), write a new **Python Node** that updates the `MentalHealthState` with a binary or category. Pass that strict instruction into the `response_generator`.
2. **State Management:** All state properties are managed in `src/mental_health_wellness/agent/state.py`.
3. **Adding a node:** Define it in `src/mental_health_wellness/nodes/`, then wire it into `build_graph()` in `graph.py`. Use exact edge routing!

## 🔐 Data & Security (GDPR Ready)

The backend exposes fully mapped endpoints (`/api/user/{id}/data-export` and `/api/user/{id}/data`) to handle GDPR requirements including Right to Access (Article 15) and Right to Erasure (Article 17). User consent records are also explicitly tracked via the `User` Prisma model.
