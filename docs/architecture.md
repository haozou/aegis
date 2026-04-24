# Architecture

## Overview

Aegis follows a layered architecture with clear separation of concerns. The backend is an async Python application built on FastAPI, with a React single-page application as the frontend.

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                       │
│              (React 19 + Tailwind + Zustand)            │
└──────────┬──────────────────────────┬───────────────────┘
           │ REST API                 │ WebSocket
┌──────────▼──────────────────────────▼───────────────────┐
│                   FastAPI Server                        │
│                  (Routes + Middleware)                   │
├─────────────────────────────────────────────────────────┤
│                 AgentOrchestrator                       │
│            (Session management + streaming)              │
├──────────┬──────────┬───────────┬───────────────────────┤
│ ToolLoop │ LLM      │ Memory    │ Knowledge             │
│          │ Registry  │ Store     │ Service               │
├──────────┴──────────┴───────────┴───────────────────────┤
│              Storage Layer (Repositories)                │
│             SQLite (dev) / PostgreSQL (prod)             │
└─────────────────────────────────────────────────────────┘
```

## Application Lifecycle

The app factory (`create_app()` in `app.py`) initializes all components during startup via FastAPI's lifespan:

1. **Logging** — Structured logging with `structlog` (rich or JSON format)
2. **Database** — Async SQLite or PostgreSQL with automatic migrations
3. **Repositories** — Data access layer for all entities
4. **AuthService** — JWT token generation and validation
5. **LLM Providers** — Register available providers (LiteLLM, Anthropic, OpenAI, Ollama)
6. **ToolRegistry** — Register built-in tools based on configuration
7. **MemoryStore** — ChromaDB for semantic memory and embeddings
8. **KnowledgeService** — RAG document ingestion and retrieval
9. **AgentOrchestrator** — Core agent session and message engine
10. **WebhookDispatcher** — Outbound webhook delivery with retries
11. **CronScheduler** — Periodic agent task execution
12. **ChannelManager** — Start multi-channel adapters (Discord, Telegram, etc.)

Shutdown reverses this: stop channels → stop cron → close database.

## Core Components

### AgentOrchestrator

The central component that manages agent sessions and coordinates the tool loop.

```
User Message
    │
    ▼
AgentOrchestrator.send_message()
    │
    ▼
ToolLoop.run()
    │
    ├──► LLM Provider (stream response)
    │       │
    │       ├── Text chunks → StreamEvent(TEXT_DELTA)
    │       └── Tool calls → StreamEvent(TOOL_START)
    │                           │
    │                           ▼
    │                     ToolRegistry.execute()
    │                           │
    │                           ▼
    │                     StreamEvent(TOOL_RESULT)
    │                           │
    │                     ◄─────┘ (loop back to LLM with results)
    │
    └──► StreamEvent(DONE)
```

The tool loop runs up to `max_tool_iterations` (default: 50) cycles, allowing the agent to autonomously use tools until it produces a final text response.

### Session Management

Each WebSocket connection creates an `AgentSession` that tracks:
- Session and conversation IDs
- Agent configuration (provider, model, tools, system prompt)
- Streaming state and cancellation
- Stream buffer for reconnection (kept 60 seconds)

### LLM Provider Registry

Providers are resolved in priority order:
1. **LiteLLM proxy** — Universal router, preferred when configured
2. **Named provider** — Directly by name (anthropic, openai, ollama)
3. **First registered** — Fallback to first available

All providers implement the same interface: `complete()`, `stream()`, `health_check()`.

### Tool System

Tools implement `BaseTool` with:
- `name` — Unique identifier
- `description` — Shown to the LLM
- `parameters_schema` — JSON Schema for input validation
- `execute(context, **kwargs)` — Async execution returning `ToolResult`

The `ToolContext` provides sandboxed access to session info, allowed paths, repositories, and memory.

MCP (Model Context Protocol) tools are dynamically loaded from external servers and wrapped as `BaseTool` instances with names prefixed `mcp__{server_id}__{tool_name}`.

### Knowledge Base (RAG)

Per-agent document collections stored in ChromaDB:
- Documents are chunked (1000 chars, 200 overlap) and embedded
- Sources: direct text, URLs (fetched and converted), file uploads
- Relevant context is injected into the system prompt before each LLM call

### Memory System

Conversation-aware semantic memory using ChromaDB + SentenceTransformer (`all-MiniLM-L6-v2`):
- Messages are auto-embedded after each conversation turn
- Relevant memories are retrieved and injected as context
- Per-conversation isolation with metadata filtering

### Skills System

Skills are Markdown files (`SKILL.md`) with YAML frontmatter:
- **Triggers**: `keyword` (matched against user message), `always`, `never`
- **Hot-reload**: File watcher detects changes and reloads automatically
- Matched skills inject their content as additional system prompt sections

### Channel System

Multi-channel delivery with a shared base class:
- Each channel adapter connects to its platform (Discord bot, Telegram bot, IMAP/SMTP, etc.)
- Inbound messages are routed through the agent orchestrator
- Responses are sent back through the platform's API
- Connections are stored in the database and hot-reloadable

## Data Flow

### WebSocket Message Flow

```
Client                    Server
  │                         │
  ├── {type: "auth"}  ────► │ Validate JWT
  │◄── {type: "auth_ok"} ──┤
  │                         │
  ├── {type: "message"} ──► │ Create/load conversation
  │                         │ Run agent through tool loop
  │◄── {type: "text_delta"} │ Stream text chunks
  │◄── {type: "tool_start"} │ Tool invocation
  │◄── {type: "tool_result"}│ Tool output
  │◄── {type: "done"} ─────│ Response complete
  │                         │
  ├── {type: "cancel"} ───► │ Cancel current stream
  │◄── {type: "cancelled"} ─│
```

### REST API Flow

External integrations use the Agent API endpoint:
```
POST /api/agents/{agent_id}/api/message
Authorization: Bearer <api_key>
{"message": "..."}
```

This runs the agent synchronously and returns the full response.

## Database

### Supported Backends
- **SQLite** — Default for development, uses WAL mode for concurrent reads
- **PostgreSQL** — Production, with connection pooling (asyncpg)

### Migration System
Migrations are SQL files in `src/aegis/storage/migrations/sqlite/` and `src/aegis/storage/migrations/pg/`, applied automatically on startup in order.

### Key Entities
| Entity | Description |
|--------|-------------|
| Users | Authentication accounts |
| Agents | Agent definitions (name, model, system prompt, tools) |
| Conversations | Chat threads per agent per user |
| Messages | Individual messages in conversations |
| API Keys | Per-agent API keys for external access |
| Webhooks | Outbound webhook configurations |
| Scheduled Tasks | Cron-based agent tasks |
| Channel Connections | Multi-channel adapter configs |
| Knowledge Documents | RAG document metadata |
| Sessions | Active agent sessions |
