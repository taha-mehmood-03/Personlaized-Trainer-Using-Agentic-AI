"""
Shared rate-limiter instance.

Import `limiter` here in both app.py and route files so that
per-route @limiter.limit() decorators work without circular imports.
"""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

_DEFAULT = os.getenv("SENTIMIND_RATE_LIMIT_DEFAULT", "120/minute")

limiter = Limiter(key_func=get_remote_address, default_limits=[_DEFAULT])
