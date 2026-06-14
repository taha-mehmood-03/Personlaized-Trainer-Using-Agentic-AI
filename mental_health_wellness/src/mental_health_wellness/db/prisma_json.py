"""Small helpers for prisma-client-py JSON fields."""

from __future__ import annotations

from typing import Any

from prisma import Json


def prisma_json(value: Any) -> Json:
    """Wrap a Python value for Prisma Json/Json? fields."""
    if isinstance(value, Json):
        return value
    return Json(value if value is not None else {})


__all__ = ["prisma_json"]
