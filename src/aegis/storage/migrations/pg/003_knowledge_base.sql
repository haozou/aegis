-- Knowledge base documents
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'text',
    source_url TEXT,
    content_hash TEXT,
    chunk_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    error TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_agent ON knowledge_documents(agent_id);
