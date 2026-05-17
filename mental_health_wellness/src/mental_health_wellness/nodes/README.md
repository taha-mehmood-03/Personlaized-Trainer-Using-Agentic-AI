# Agent Node Structure

The active LangGraph path is intentionally small:

1. `parallel_intake.py`
   Runs independent startup work concurrently: crisis screening, context loading, mood analysis, intent prefetch, and optional voice preprocessing.
2. `analysis_and_planning.py`
   Fuses emotion, clinical severity, cognitive distortion, trend analysis, conversation planning, and behavioral activation.
3. `response_pipeline.py`
   Selects therapeutic techniques and the assistant role.
4. `optimized_response_generator.py`
   Produces the final user-facing response.
5. `crisis_handler.py`
   Handles crisis-safe state before the final response is generated.
6. `parallel_persist.py`
   Saves profile, session, and outcome data in the background after the user response is ready.

Supporting modules:

- `context_loader.py` loads user preferences, user history metadata, and semantic memory for `parallel_intake.py`.
- `parallel_analysis.py` is a helper used by `analysis_and_planning.py`.
- `voice_preprocessing.py` can be called by `parallel_intake.py` or API endpoints when audio is present.
- Individual analysis helpers such as `mood_analyzer_node.py`, `emotion_fusion_node.py`, `conversation_planner_node.py`, and `technique_selector_node.py` are composed by the fused nodes above.

Removed legacy architecture:

- The old standalone `intake.py` graph node has been replaced by `parallel_intake.py` plus `context_loader.py`.
- The old `agentic.py` pipeline, `crisis_router.py`, and non-optimized `response_generator.py` were removed because the current graph no longer imports or executes them.
