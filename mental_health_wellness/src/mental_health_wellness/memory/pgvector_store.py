"""
Pgvector-backed semantic retrieval.

This module intentionally uses raw SQL because Prisma's Python client does not
model the Postgres `vector` type cleanly. Core application tables remain normal
Prisma models; this table is a retrieval index pointing back to those records.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

logger = logging.getLogger("sentimind.pgvector")

VECTOR_DIM = 384
TABLE_NAME = '"SemanticEmbedding"'
_initialized = False


def _vector_literal(vector: list[float]) -> str:
    values = [f"{float(v):.8f}" for v in vector]
    return "[" + ",".join(values) + "]"


def _quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _json_literal(value: dict[str, Any] | None) -> str:
    return _quote(json.dumps(value or {}, ensure_ascii=False))


def _source_list(values: Iterable[str]) -> str:
    quoted = [_quote(v) for v in values if v]
    return ", ".join(quoted) or "''"


async def _execute(sql: str):
    from ..db.client import get_prisma_client

    prisma = await get_prisma_client()
    return await prisma.execute_raw(sql)


async def _query(sql: str):
    from ..db.client import get_prisma_client

    prisma = await get_prisma_client()
    return await prisma.query_raw(sql)


async def ensure_pgvector_schema() -> None:
    """Create the pgvector extension and retrieval index table if missing."""
    global _initialized
    if _initialized:
        return

    await _execute("CREATE EXTENSION IF NOT EXISTS vector")
    await _execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id TEXT PRIMARY KEY,
            "userId" TEXT,
            "sessionId" TEXT,
            "sourceType" TEXT NOT NULL,
            "sourceId" TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding vector({VECTOR_DIM}) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
            "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await _execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS "SemanticEmbedding_source_unique"
        ON {TABLE_NAME} ("sourceType", "sourceId")
        """
    )
    await _execute(
        f"""
        CREATE INDEX IF NOT EXISTS "SemanticEmbedding_user_source_idx"
        ON {TABLE_NAME} ("userId", "sourceType")
        """
    )
    await _execute(
        f"""
        CREATE INDEX IF NOT EXISTS "SemanticEmbedding_session_idx"
        ON {TABLE_NAME} ("sessionId")
        """
    )
    # Try HNSW first (pgvector ≥0.5, no minimum-row requirement).
    # Fall back to IVFFlat (requires ≥3900 rows to train — fails on empty tables).
    # If both fail, skip the ANN index: cosine search falls back to sequential scan,
    # which is fine for small tables and still returns correct results.
    try:
        await _execute(
            f"""
            CREATE INDEX IF NOT EXISTS "SemanticEmbedding_embedding_idx"
            ON {TABLE_NAME}
            USING hnsw (embedding vector_cosine_ops)
            """
        )
        logger.info("pgvector | ANN index: HNSW created")
    except Exception:
        try:
            await _execute(
                f"""
                CREATE INDEX IF NOT EXISTS "SemanticEmbedding_embedding_idx"
                ON {TABLE_NAME}
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
            logger.info("pgvector | ANN index: IVFFlat created")
        except Exception as idx_err:
            logger.warning(
                "pgvector | ANN index creation skipped (sequential scan will be used): %s",
                str(idx_err)[:120],
            )
    _initialized = True


def embed_text(text: str) -> list[float]:
    from . import _get_embeddings

    return _get_embeddings().embed_query(text)


async def upsert_embedding(
    *,
    source_type: str,
    source_id: str,
    content: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    embedding: list[float] | None = None,
) -> bool:
    """Upsert a source record into the pgvector retrieval table."""
    if not source_type or not source_id or not content or not content.strip():
        return False

    try:
        await ensure_pgvector_schema()
        vector = embedding or embed_text(content)
        vector_sql = _quote(_vector_literal(vector))
        row_id = f"{source_type}:{source_id}"
        await _execute(
            f"""
            INSERT INTO {TABLE_NAME}
                (id, "userId", "sessionId", "sourceType", "sourceId", content, embedding, metadata, "updatedAt")
            VALUES (
                {_quote(row_id)},
                {_quote(user_id) if user_id else 'NULL'},
                {_quote(session_id) if session_id else 'NULL'},
                {_quote(source_type)},
                {_quote(source_id)},
                {_quote(content[:4000])},
                {vector_sql}::vector,
                {_json_literal(metadata)}::jsonb,
                now()
            )
            ON CONFLICT ("sourceType", "sourceId")
            DO UPDATE SET
                "userId" = EXCLUDED."userId",
                "sessionId" = EXCLUDED."sessionId",
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                "updatedAt" = now()
            """
        )
        return True
    except Exception as err:
        logger.warning("pgvector upsert failed | source=%s id=%s error=%s", source_type, source_id, str(err)[:120])
        return False


async def search_embeddings(
    *,
    query: str,
    user_id: str | None = None,
    source_types: list[str] | None = None,
    limit: int = 5,
    exclude_session_id: str | None = None,
    source_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search the retrieval table by cosine distance."""
    if not query or not query.strip():
        return []

    try:
        await ensure_pgvector_schema()
        vector = embed_text(query)
        where = []
        if user_id:
            where.append(f'"userId" = {_quote(user_id)}')
        if source_types:
            where.append(f'"sourceType" IN ({_source_list(source_types)})')
        if exclude_session_id:
            where.append(f'COALESCE("sessionId", \'\') <> {_quote(exclude_session_id)}')
        if source_ids:
            where.append(f'"sourceId" IN ({_source_list(source_ids)})')
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = await _query(
            f"""
            SELECT
                id,
                "userId",
                "sessionId",
                "sourceType",
                "sourceId",
                content,
                metadata,
                1 - (embedding <=> {_quote(_vector_literal(vector))}::vector) AS similarity
            FROM {TABLE_NAME}
            {where_sql}
            ORDER BY embedding <=> {_quote(_vector_literal(vector))}::vector
            LIMIT {int(limit)}
            """
        )
        return [dict(row) for row in rows or []]
    except Exception as err:
        logger.warning("pgvector search failed | error=%s", str(err)[:120])
        return []


async def delete_embeddings(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
) -> int:
    """Delete retrieval rows by scope."""
    try:
        await ensure_pgvector_schema()
        where = []
        if user_id:
            where.append(f'"userId" = {_quote(user_id)}')
        if session_id:
            where.append(f'"sessionId" = {_quote(session_id)}')
        if source_type:
            where.append(f'"sourceType" = {_quote(source_type)}')
        if source_id:
            where.append(f'"sourceId" = {_quote(source_id)}')
        if not where:
            return 0
        return await _execute(f"DELETE FROM {TABLE_NAME} WHERE {' AND '.join(where)}")
    except Exception as err:
        logger.warning("pgvector delete failed | error=%s", str(err)[:120])
        return 0


async def rank_source_ids(
    *,
    query: str,
    source_type: str,
    source_ids: list[str],
    limit: int = 10,
    user_id: str | None = None,
) -> dict[str, float]:
    """Return semantic similarity scores for a constrained set of source ids.

    Pass user_id to scope results to a specific user (required for message/fact
    embeddings). Leave as None for global source types like techniques.
    """
    rows = await search_embeddings(
        query=query,
        source_types=[source_type],
        source_ids=source_ids,
        limit=limit,
        user_id=user_id,
    )
    return {
        str(row.get("sourceId")): float(row.get("similarity") or 0.0)
        for row in rows
    }
