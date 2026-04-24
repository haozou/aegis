-- Memory entries table for tracking ChromaDB documents
CREATE TABLE IF NOT EXISTS memory_entries (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
    content_preview TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_memory_conversation ON memory_entries(conversation_id);
CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_entries(created_at DESC);
