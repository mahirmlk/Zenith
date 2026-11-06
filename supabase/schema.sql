-- NOTE: migrations/ (0001-0006) are the source of truth for production installs.
-- This file is the legacy baseline for fresh single-file installs; it is kept
-- for reference and should be regenerated from migrations. See
-- docs/MIGRATIONS_RUNBOOK.md.
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Papers table with vector search
CREATE TABLE IF NOT EXISTS papers (
  id           TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  abstract     TEXT,
  authors      JSONB DEFAULT '[]',
  url          TEXT,
  published_at TIMESTAMPTZ,
  summary_tldr TEXT,
  embedding    VECTOR(1536),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_papers_embedding ON papers USING ivfflat (embedding vector_cosine_ops);

-- Index for recent papers
CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers (published_at DESC);

-- User saved papers
CREATE TABLE IF NOT EXISTS user_papers (
  user_id    UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  paper_id   TEXT REFERENCES papers(id) ON DELETE CASCADE,
  saved_at   TIMESTAMPTZ DEFAULT NOW(),
  dismissed  BOOLEAN DEFAULT FALSE,
  PRIMARY KEY (user_id, paper_id)
);

-- User preferences
CREATE TABLE IF NOT EXISTS user_prefs (
  user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  preferred_model  TEXT DEFAULT 'anthropic/claude-sonnet-4-5',
  interests        TEXT[] DEFAULT '{}',
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Citation graph edges, cached from Semantic Scholar on first fetch.
-- This is the backing table for GET /api/graph/{paper_id}; without it the
-- endpoint would hit the rate-limited S2 API on every graph load.
CREATE TABLE IF NOT EXISTS citations (
  paper_id    TEXT REFERENCES papers(id) ON DELETE CASCADE,
  root_title  TEXT,
  cited_id    TEXT,
  cited_title TEXT,
  fetched_at  TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (paper_id, cited_id)
);

CREATE INDEX IF NOT EXISTS idx_citations_paper_id ON citations (paper_id, fetched_at DESC);

-- Full-text crawl cache for Firecrawl pulls, keyed by paper ID so popular
-- papers are crawled once instead of once per user.
CREATE TABLE IF NOT EXISTS crawled_content (
  paper_id   TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
  url        TEXT,
  content    TEXT,
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);

-- Compound index for the personalised feed query on user_papers
-- (user_id, dismissed, saved_at).
CREATE INDEX IF NOT EXISTS idx_user_papers_feed
  ON user_papers (user_id, dismissed, saved_at DESC);

-- Function to search papers by vector similarity
CREATE OR REPLACE FUNCTION match_papers(
  query_embedding VECTOR(1536),
  match_threshold FLOAT,
  match_count INT
)
RETURNS TABLE(
  id TEXT,
  title TEXT,
  abstract TEXT,
  authors JSONB,
  url TEXT,
  published_at TIMESTAMPTZ,
  summary_tldr TEXT,
  similarity FLOAT
)
LANGUAGE SQL STABLE
AS $$
  SELECT
    papers.id,
    papers.title,
    papers.abstract,
    papers.authors,
    papers.url,
    papers.published_at,
    papers.summary_tldr,
    1 - (papers.embedding <=> query_embedding) AS similarity
  FROM papers
  WHERE 1 - (papers.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
$$;

-- Add summary_contributions column idempotently
ALTER TABLE IF EXISTS papers ADD COLUMN IF NOT EXISTS summary_contributions JSONB DEFAULT NULL;
