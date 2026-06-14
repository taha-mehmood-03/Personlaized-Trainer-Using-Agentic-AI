"""
Compatibility entrypoint for the SentiMind FastAPI backend.

The application, middleware, lifespan, and route definitions live in
src.mental_health_wellness.api.app. Keep this file small so the project root is
only a server launcher, not the API implementation.
"""

from __future__ import annotations

import os

from src.mental_health_wellness.api.app import app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "src.mental_health_wellness.api.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
