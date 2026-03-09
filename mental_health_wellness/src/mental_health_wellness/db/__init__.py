"""
Database Module - Prisma client and database operations
"""

from .client import get_prisma_client, close_prisma_client

__all__ = ["get_prisma_client", "close_prisma_client"]
