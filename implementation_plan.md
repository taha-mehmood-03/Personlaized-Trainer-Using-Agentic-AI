# Clinical Severity Assessment — Implementation Plan

> **Objective 3:** Validate the system through controlled trials with mental health professionals, ensuring consistency with clinical tools.

## What This Changes

The LLM will assess **clinical severity** using PHQ-9 (depression) and GAD-7 (anxiety) criteria embedded directly in its prompt — on **every therapeutic turn**. This severity score will then drive **which exercises get selected from the DB**, replacing the current custom intensity-only threshold with a clinically validated severity-to-difficulty mapping.

---

## Current Flow (Before)

```
User message
    ↓
analyze_mood → emotion="sadness", intensity=0.78
    ↓
technique_selector_node → _intensity_tier(0.78) = "high"
    ↓
DB query: WHERE targetEmotions HAS "SADNESS" AND categoryId IN ["Breathing", "DBT"]
    ↓
Returns: Box Breathing (EASY), Emotion Surfing (MODERATE), etc.
    ↓
Top technique by rating score → delivered to user
```

**Problem:** The intensity tier only considers emotional intensity (how strong the feeling is). It doesn't consider **clinical severity** (how persistent, pervasive, and functionally impairing the distress is). A user who says "I'm very stressed about my exam" (high intensity, low severity) gets the same treatment as someone showing signs of moderate clinical depression (high intensity, HIGH severity).

---

## New Flow (After)

```
User message
    ↓
analyze_mood → emotion="sadness", intensity=0.78
    ↓
[NEW] clinical_severity_check (LLM) → severity="moderate", phq9_estimated=14, gad7_estimated=8
    ↓ (both severity AND intensity feed into technique selection)
technique_selector_node → uses severity to pick DIFFICULTY level
    ↓
DB query: WHERE targetEmotions HAS "SADNESS"
          AND difficulty IN ["MODERATE", "HARD"]     ← severity-driven
          AND categoryId IN ["Breathing", "DBT"]     ← intensity-driven (unchanged)
    ↓
Returns: Socratic Questioning (MODERATE), Emotion Surfing (MODERATE), etc.
    ↓
Top technique by rating score → delivered to user
```

---

## Architecture Diagram — Where It Plugs In

```
NODE 2: ANALYSIS & PLANNING (analysis_and_planning.py)
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│  Sub-node 1: emotion_fusion_node     ← unchanged                │
│      → fused_emotion, fused_intensity                            │
│                                                                   │
│  Sub-node 2: parallel_analysis       ← MODIFIED                 │
│      → distortion, trend                                         │
│      → [NEW] clinical_severity_check (runs in parallel           │
│              with distortion + trend)                             │
│      → clinical_severity, clinical_scores                        │
│                                                                   │
│  Sub-node 3: conversation_planner    ← MODIFIED                 │
│      → NOW reads clinical_severity to adjust strategy            │
│      → severe → always suggest_technique + crisis-aware          │
│      → minimal → validate_only (don't push techniques)           │
│                                                                   │
│  Sub-node 4: behavioral_activation   ← unchanged                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                          ↓
NODE 3: RESPONSE PIPELINE
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│  technique_selector_node             ← MODIFIED                  │
│      → NOW uses clinical_severity to filter by difficulty        │
│      → severity→difficulty mapping:                              │
│           minimal  → [EASY]                                      │
│           mild     → [EASY, MODERATE]                            │
│           moderate → [MODERATE, HARD]                            │
│           moderately_severe → [HARD] + professional referral hint│
│           severe   → SKIP exercises, crisis pathway              │
│                                                                   │
│  role_selector_node                  ← unchanged                 │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
                          ↓
NODE 4: RESPONSE GENERATOR
┌──────────────────────────────────────────────────────────────────┐
│  _build_structured_context()         ← MODIFIED                  │
│      → Injects severity label into LLM context                  │
│      → "CLINICAL SEVERITY: MODERATE (PHQ-9 est. ~14)"           │
│      → LLM adapts tone/depth based on severity                  │
└──────────────────────────────────────────────────────────────────┘
                          ↓
NODE 5: PARALLEL PERSIST
┌──────────────────────────────────────────────────────────────────┐
│  session_saver                       ← MODIFIED                  │
│      → Saves clinical_severity + scores to ClinicalAssessmentLog│
│      → Enables longitudinal tracking of severity over sessions  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Proposed Changes — File by File

---

### 1. [NEW] `llm_classifier.py` — Add `clinical_severity_check()`

> [!IMPORTANT]
> This is the core new function. It's an LLM classifier (same pattern as `llm_crisis_check`, `llm_distortion_check`) that evaluates the user's message + recent context against PHQ-9 and GAD-7 scoring criteria.

**Location:** [llm_classifier.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/llm/llm_classifier.py) — add new function after `llm_distortion_check()` (~line 493)

**What it does:**
- Takes user message + recent conversation context
- The LLM prompt contains the **full PHQ-9 and GAD-7 criteria** as reference
- LLM estimates: which PHQ-9 items show evidence, what score range, what severity level
- Returns structured JSON with severity classification

```python
async def clinical_severity_check(
    message: str,
    recent_context: str = "",
    emotion: str = "neutral",
    intensity: float = 0.5,
    emotional_trend: str = "stable",
) -> dict:
    """
    Clinical severity assessment using PHQ-9 and GAD-7 criteria.
    
    The LLM evaluates conversational cues against standardized clinical
    instrument criteria to estimate severity level.
    
    Returns:
      {
        "severity": "minimal" | "mild" | "moderate" | "moderately_severe" | "severe",
        "phq9_estimated": int (0-27),
        "gad7_estimated": int (0-21),
        "clinical_indicators": ["sleep_disturbance", "anhedonia", ...],
        "confidence": float (0.0-1.0),
        "reasoning": str
      }
    """
```

**Prompt design:** The LLM prompt will contain:
- All 9 PHQ-9 items (depression screening)
- All 7 GAD-7 items (anxiety screening)
- Instructions to evaluate which items show evidence from the conversation
- Scoring: each item 0-3 (not at all → nearly every day)
- Final severity mapping:
  - PHQ-9: 0-4 minimal, 5-9 mild, 10-14 moderate, 15-19 moderately_severe, 20-27 severe
  - GAD-7: 0-4 minimal, 5-9 mild, 10-14 moderate, 15-21 severe
  - Overall severity = max(PHQ-9 severity, GAD-7 severity)

**Model used:** `MODEL_HEAVY` (llama-3.3-70b-instruct) — clinical assessment is safety-adjacent, needs the 70b model

**When it runs:** Only on therapeutic turns (NOT chitchat, accept_technique, list_techniques, memory_query, rejection)

---

### 2. [MODIFY] `state.py` — Add clinical severity state fields

**File:** [state.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/agent/state.py)

Add after the existing `v5.4: GATE ROUTE` section (~line 178):

```python
# ============================================
# v9.0: CLINICAL SEVERITY (PHQ-9/GAD-7)
# ============================================
clinical_severity: str            # "minimal" | "mild" | "moderate" | "moderately_severe" | "severe"
clinical_phq9_score: int          # estimated PHQ-9 total (0-27)
clinical_gad7_score: int          # estimated GAD-7 total (0-21)
clinical_indicators: list[str]    # detected clinical indicators
clinical_confidence: float        # 0.0-1.0 confidence in assessment
```

And add defaults in `get_initial_state()`:

```python
# v9.0: Clinical Severity
clinical_severity="minimal",
clinical_phq9_score=0,
clinical_gad7_score=0,
clinical_indicators=[],
clinical_confidence=0.0,
```

---

### 3. [MODIFY] `analysis_and_planning.py` — Wire clinical severity check

**File:** [analysis_and_planning.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/analysis_and_planning.py)

**Change:** In `run_analysis_and_planning()`, after the parallel analysis step (sub-node 2), add the clinical severity check. It runs **in parallel** with distortion + trend (it's another LLM call that can overlap).

```python
# Sub-node 2: Parallel Analysis + Clinical Severity
# Run distortion + trend + clinical severity concurrently
import asyncio

async def _run_clinical():
    from ..llm.llm_classifier import clinical_severity_check
    user_msg = messages[-1].content if messages else ""
    recent_ctx = ... # last 4 messages
    return await clinical_severity_check(
        message=user_msg,
        recent_context=recent_ctx,
        emotion=merged.get("fused_emotion", "neutral"),
        intensity=merged.get("fused_intensity", 0.5),
        emotional_trend=merged.get("emotional_trend", "stable"),
    )

# Run all three concurrently
analysis_task = asyncio.create_task(run_parallel_analysis(state_after_fusion))
clinical_task = asyncio.create_task(_run_clinical())

analysis_result = await analysis_task
clinical_result = await clinical_task

merged.update(analysis_result)
merged.update({
    "clinical_severity": clinical_result.get("severity", "minimal"),
    "clinical_phq9_score": clinical_result.get("phq9_estimated", 0),
    "clinical_gad7_score": clinical_result.get("gad7_estimated", 0),
    "clinical_indicators": clinical_result.get("clinical_indicators", []),
    "clinical_confidence": clinical_result.get("confidence", 0.0),
})
```

**Skip condition:** Same as distortion — skip for chitchat, technique_request, etc. Only run on therapeutic turns.

---

### 4. [MODIFY] `technique_selector_node.py` — Severity-driven difficulty filtering

**File:** [technique_selector_node.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/technique_selector_node.py)

**Current behavior:** Calls `recommend_technique()` with just `emotion` + `intensity` + `user_id`.

**New behavior:** Also passes `clinical_severity` which gets translated to difficulty filter.

```python
# NEW: severity → difficulty mapping
SEVERITY_DIFFICULTY_MAP = {
    "minimal":            ["EASY"],
    "mild":               ["EASY", "MODERATE"],
    "moderate":           ["MODERATE", "HARD"],
    "moderately_severe":  ["HARD"],
    "severe":             [],  # No exercises — crisis pathway
}

severity = state.get("clinical_severity", "minimal")
allowed_difficulties = SEVERITY_DIFFICULTY_MAP.get(severity, ["EASY", "MODERATE"])
```

Then pass `allowed_difficulties` to `recommend_technique()`.

---

### 5. [MODIFY] `technique_tools.py` — Accept difficulty filter

**File:** [technique_tools.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/tools/technique_tools.py)

**Change:** `recommend_technique()` gains a new parameter `allowed_difficulties: List[str] = None`.

When provided, the DB query adds:
```python
if allowed_difficulties:
    where_clause["difficulty"] = {"in": allowed_difficulties}
```

This filters techniques by the difficulty levels that match the clinical severity.

---

### 6. [MODIFY] `conversation_planner_node.py` — Severity-aware strategy selection

**File:** [conversation_planner_node.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/conversation_planner_node.py)

**Change:** In `_select_strategy()`, add severity-aware overrides:

```python
severity = state.get("clinical_severity", "minimal")

# Severe → always suggest technique + flag for professional referral
if severity == "severe":
    print("[NODE: PLANNER] ⚠ Severe clinical severity → suggest_technique + referral hint")
    return "suggest_technique"

# Moderately severe → push technique earlier (don't wait for readiness)
if severity == "moderately_severe" and intensity >= 0.5:
    print("[NODE: PLANNER] ⚠ Moderately severe → suggest_technique (early push)")
    return "suggest_technique"

# Minimal → don't push techniques, just validate
if severity == "minimal" and intensity < 0.5:
    return "validate_only"
```

---

### 7. [MODIFY] `optimized_response_generator.py` — Inject severity into prompt

**File:** [optimized_response_generator.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/optimized_response_generator.py)

**Change in `_build_structured_context()`:** Add a `CLINICAL ASSESSMENT` section:

```python
clinical_info = ""
severity = state.get("clinical_severity", "minimal")
if severity and severity != "minimal":
    phq9 = state.get("clinical_phq9_score", 0)
    gad7 = state.get("clinical_gad7_score", 0)
    indicators = state.get("clinical_indicators", [])
    clinical_info = f"""
CLINICAL SEVERITY ASSESSMENT (PHQ-9/GAD-7 based):
- Overall Severity: {severity.upper().replace('_', ' ')}
- Depression Screen (PHQ-9 est.): {phq9}/27
- Anxiety Screen (GAD-7 est.): {gad7}/21
- Indicators: {', '.join(indicators) if indicators else 'none detected'}

INSTRUCTION: Adjust response depth and urgency to match severity level.
- moderate/moderately_severe → be more directive, introduce technique with confidence
- severe → prioritize safety, validate deeply, gently mention professional support
"""
```

Also in `_build_optimized_system_prompt()`, add severity-aware guidance:

```python
if severity == "moderately_severe":
    system_prompt += "\n⚠ CLINICAL NOTE: User shows signs of moderately severe distress. "
    "Alongside the technique, gently mention that speaking with a professional "
    "could also be helpful. Frame it as 'in addition to' not 'instead of'."

if severity == "severe":
    system_prompt += "\n🚨 CLINICAL NOTE: User shows signs of severe distress. "
    "Exercise extreme care. Validate deeply. Gently encourage professional support."
```

---

### 8. [MODIFY] `schema.prisma` — Add `ClinicalAssessmentLog` for tracking

**File:** [schema.prisma](file:///e:/FYP/mental_health_wellness/prisma/schema.prisma)

Add a new model to track severity assessments over time:

```prisma
enum ClinicalSeverity {
  MINIMAL
  MILD
  MODERATE
  MODERATELY_SEVERE
  SEVERE
}

model ClinicalAssessmentLog {
  id               String            @id @default(cuid())
  sessionId        String
  session          Session           @relation(fields: [sessionId], references: [id], onDelete: Cascade)
  userId           String

  severity         ClinicalSeverity
  phq9Score        Int               // 0-27
  gad7Score        Int               // 0-21
  indicators       String[]          // e.g. ["anhedonia", "sleep_disturbance", "concentration"]
  confidence       Float             // 0.0-1.0

  assessedAt       DateTime          @default(now())

  @@index([userId])
  @@index([sessionId])
  @@index([assessedAt])
}
```

---

### 9. [MODIFY] `session_saver.py` — Persist clinical severity

**File:** `session_saver.py` (in parallel_persist)

**Change:** After saving the session/message, also save the clinical assessment log:

```python
severity = state.get("clinical_severity", "minimal")
if severity and severity != "minimal":
    await prisma.clinicalassessmentlog.create(
        data={
            "sessionId": session_id,
            "userId": user_id,
            "severity": severity.upper().replace(" ", "_"),
            "phq9Score": state.get("clinical_phq9_score", 0),
            "gad7Score": state.get("clinical_gad7_score", 0),
            "indicators": state.get("clinical_indicators", []),
            "confidence": state.get("clinical_confidence", 0.0),
        }
    )
```

---

## Summary of All Changes

| File | Change | Impact |
|------|--------|--------|
| [llm_classifier.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/llm/llm_classifier.py) | **Add** `clinical_severity_check()` function (~80 lines) | Core new classifier with PHQ-9/GAD-7 prompt |
| [state.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/agent/state.py) | **Add** 5 new state fields + defaults | State carries severity through pipeline |
| [analysis_and_planning.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/analysis_and_planning.py) | **Add** clinical severity call in parallel with distortion + trend | Severity assessed on every therapeutic turn |
| [technique_selector_node.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/technique_selector_node.py) | **Add** severity→difficulty mapping + pass to DB query | Exercises matched to clinical severity |
| [technique_tools.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/tools/technique_tools.py) | **Add** `allowed_difficulties` parameter to `recommend_technique()` | DB query filters by difficulty |
| [conversation_planner_node.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/conversation_planner_node.py) | **Add** severity-aware strategy overrides in `_select_strategy()` | Severe → always suggest, minimal → validate only |
| [optimized_response_generator.py](file:///e:/FYP/mental_health_wellness/src/mental_health_wellness/nodes/optimized_response_generator.py) | **Add** severity context in prompt + severity-aware system prompt notes | LLM response adapts to severity |
| [schema.prisma](file:///e:/FYP/mental_health_wellness/prisma/schema.prisma) | **Add** `ClinicalSeverity` enum + `ClinicalAssessmentLog` model | Longitudinal severity tracking |
| `session_saver.py` | **Add** clinical assessment log save | Persist severity per session |

---

## Verification Plan

### Automated Testing
1. **Unit test `clinical_severity_check()`** with known messages:
   - "I'm stressed about my exam" → minimal/mild
   - "I can't sleep, can't eat, don't enjoy anything anymore, been feeling this way for weeks" → moderate/moderately_severe
   - "I don't see any point in living" → severe (+ crisis pathway)

2. **Integration test**: Send therapeutic message through full pipeline → verify `clinical_severity` state field is populated → verify technique difficulty matches severity

3. **DB verification**: Check `ClinicalAssessmentLog` records are created with correct scores

### Manual Verification
- Run the agent, express various levels of distress, verify:
  - Mild distress → EASY exercises (breathing, grounding)
  - Moderate distress → MODERATE exercises (CBT worksheets, DBT skills)
  - High severity → HARD exercises + professional referral hint
  - Severe → crisis pathway, no exercises

---

## Open Questions

> [!IMPORTANT]
> **Latency cost:** The clinical severity check adds one additional LLM call (~400-600ms) on therapeutic turns. Since it runs **in parallel** with distortion detection + trend analysis, the actual wall-clock impact should be ~0ms (hidden behind the existing LLM calls). However, it does add an additional OpenRouter API call per therapeutic turn. Is this acceptable?

> [!IMPORTANT]
> **Score persistence frequency:** Should we save a `ClinicalAssessmentLog` record on **every** therapeutic turn, or only when severity changes from the previous assessment? Every turn gives more data but more DB writes. On severity change only is lighter but could miss nuance.

> [!WARNING]
> **Severity accuracy from single messages:** PHQ-9/GAD-7 are designed for 2-week recall. A single message can't perfectly estimate severity. The LLM will use conversational cues + trend data to approximate, but we should clearly document this as an **estimated** severity, not a clinical diagnosis. This is important for academic honesty in your FYP report.
