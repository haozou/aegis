-- Channel connections (PostgreSQL)

CREATE TABLE IF NOT EXISTS channel_connections (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    config JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_channel_connections_agent ON channel_connections(agent_id);
CREATE INDEX IF NOT EXISTS idx_channel_connections_user ON channel_connections(user_id);
