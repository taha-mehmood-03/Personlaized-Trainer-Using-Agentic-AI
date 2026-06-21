"""
Pipeline sub-components — inline helpers called from within the graph nodes.

These modules are NOT registered as LangGraph nodes themselves. They are called
inline inside the 6 registered nodes (parallel_intake, analysis_and_planning,
response_pipeline, parallel_persist, crisis_handler, optimized_response_generator)
to implement the pipeline logic without extra graph checkpoint overhead.
"""
