-- Pgvector retrieval index for SentiMind semantic memory.
-- Run this once in Supabase SQL editor or through your migration workflow.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS "SemanticEmbedding" (
    id TEXT PRIMARY KEY,
    "userId" TEXT,
    "sessionId" TEXT,
    "sourceType" TEXT NOT NULL,
    "sourceId" TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    "createdAt" TIMESTAMPTZ NOT NULL DEFAULT now(),
    "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS "SemanticEmbedding_source_unique"
ON "SemanticEmbedding" ("sourceType", "sourceId");

CREATE INDEX IF NOT EXISTS "SemanticEmbedding_user_source_idx"
ON "SemanticEmbedding" ("userId", "sourceType");

CREATE INDEX IF NOT EXISTS "SemanticEmbedding_session_idx"
ON "SemanticEmbedding" ("sessionId");

CREATE INDEX IF NOT EXISTS "SemanticEmbedding_embedding_idx"
ON "SemanticEmbedding"
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
