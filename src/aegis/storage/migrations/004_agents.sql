-- Agents and agent configuration tables

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    avatar_url TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    is_public INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- Inline config (simpler than separate table for MVP)
    provider TEXT NOT NULL DEFAULT 'anthropic',
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-5',
    temperature REAL NOT NULL DEFAULT 0.7,
    max_tokens INTEGER NOT NULL DEFAULT 4096,
    system_prompt TEXT NOT NULL DEFAULT '',
    enable_memory INTEGER NOT NULL DEFAULT 0,
    enable_skills INTEGER NOT NULL DEFAULT 0,
    max_tool_iterations INTEGER NOT NULL DEFAULT 10,
    allowed_tools TEXT NOT NULL DEFAULT '["web_fetch","file_read","file_write","file_list"]',
    metadata TEXT DEFAULT '{}',
    UNIQUE(user_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_agents_user ON agents(user_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_slug ON agents(user_id, slug);
