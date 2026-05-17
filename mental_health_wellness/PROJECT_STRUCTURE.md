# Backend Project Structure

```text
mental_health_wellness/
  api_server.py                     FastAPI entry point
  pyproject.toml                    Python package metadata
  requirements.txt                  Runtime dependencies
  prisma/
    schema.prisma                   Database schema
  scripts/                          Database checks and seed scripts
  tests/                            Clinical/manual test harnesses and results
  src/mental_health_wellness/
    agent/
      graph.py                      LangGraph assembly and chat entry points
      state.py                      Shared graph state schema
      prompts.py                    Prompt templates
      preprocessing.py              Shared normalization/classification helpers
    nodes/
      README.md                     Active node architecture guide
      parallel_intake.py            First graph node: concurrent startup work
      context_loader.py             Context/memory helper used by parallel intake
      analysis_and_planning.py      Fused analysis/planning node
      response_pipeline.py          Fused technique/role selection node
      optimized_response_generator.py
      crisis_handler.py
      parallel_persist.py           Background persistence
    tools/                          LangChain tools and database-backed helpers
    llm/                            LLM clients and classifiers
    db/                             Prisma client helpers
    memory/                         Explicit facts and session memory
    api/                            Additional FastAPI routers
    services/                       External integrations
```

The graph entry point is `src/mental_health_wellness/agent/graph.py`.
For the current agent flow, start with `src/mental_health_wellness/nodes/README.md`.
