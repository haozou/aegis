# Aegis Codebase Exploration Report

## Project Overview
**Aegis** is an AI Agent Factory Platform built with FastAPI (Python 3.11+).
- **Total Lines of Code**: ~9,749 Python files
- **Architecture**: Async Python with FastAPI, WebSocket support, multi-provider LLM support
- **Database**: SQLite (dev) / PostgreSQL (prod) with async migration system
- **Auth**: JWT-based authentication with user isolation
- **Status**: Alpha (v0.1.0)

---

## 1. Full Directory Structure of `src/aegis/`

```
src/aegis/
├── __init__.py
├── __main__.py
├── app.py                          # FastAPI app factory with lifespan
├── api/
│   ├── routes/
│   │   ├── agents.py              # Agent CRUD (create, list, get, update, delete)
│   │   ├── agent_api.py           # Public API: send messages to agents
│   │   ├── api_keys.py            # API key management
│   │   ├── auth.py                # User auth (login, register)
│   │   ├── conversations.py       # Conversation CRUD + message listing
│   │   ├── health.py              # Health check endpoint
│   │   ├── knowledge.py           # Knowledge base upload/retrieval
│   │   ├── mcp_oauth.py           # MCP OAuth callbacks
│   │   ├── scheduled_tasks.py     # Task scheduling CRUD
│   │   ├── webhooks.py            # Webhook CRUD + inbound trigger
│   │   └── __init__.py
│   ├── middleware/
│   ├── websocket.py               # WebSocket message handler
│   └── __init__.py
├── auth/
│   ├── dependencies.py            # JWT dependency injection
│   ├── models.py                  # User model
│   ├── service.py                 # AuthService (JWT generation, password hashing)
│   └── __init__.py
├── config/
│   ├── loader.py                  # Pydantic settings loader
│   └── __init__.py
├── core/
│   ├── orchestrator.py            # **AgentOrchestrator** - main agent runner
│   ├── session.py                 # AgentSession - per-connection state
│   ├── tool_loop.py               # ToolLoop - agentic loop implementation
│   ├── types.py                   # StreamEvent, StreamEventType, AgentConfig
│   ├── title_generator.py
│   └── __init__.py
├── knowledge/                      # Auto-RAG knowledge base integration
├── llm/
│   ├── registry.py                # LLM provider registry (Anthropic, OpenAI, Ollama)
│   ├── context.py                 # Message context management
│   ├── types.py                   # LLMMessage, LLMRequest, StreamDelta
│   └── ...
├── memory/
│   ├── store.py                   # ChromaDB memory store integration
│   └── ...
├── services/
│   ├── cron_scheduler.py          # Task scheduling service
│   ├── webhook_dispatcher.py      # Outbound webhook service
│   └── __init__.py
├── skills/
│   ├── loader.py                  # Skills system (Markdown-based skills)
│   ├── types.py
│   ├── builtin/
│   └── __init__.py
├── storage/
│   ├── database.py                # **Database class** - async SQLite/PostgreSQL
│   ├── migrations/
│   │   ├── sqlite/               # SQLite migration files
│   │   ├── pg/                   # PostgreSQL migration files
│   │   └── (numbered .sql files)
│   ├── repositories/
│   │   ├── __init__.py           # Repositories dataclass
│   │   ├── agents.py             # **Agent model + AgentRepository**
│   │   ├── api_keys.py
│   │   ├── conversations.py      # **Conversation model + repository**
│   │   ├── messages.py           # **Message model + repository**
│   │   ├── knowledge.py
│   │   ├── scheduled_tasks.py
│   │   ├── sessions.py
│   │   ├── users.py
│   │   ├── webhooks.py
│   │   └── __init__.py
│   └── __init__.py
├── tools/
│   ├── registry.py               # Tool registry (builtin tools)
│   ├── types.py                  # ToolContext type
│   ├── builtin/                  # Built-in tools (web_fetch, file_ops, bash, etc.)
│   └── ...
├── tasks/
├── utils/
│   ├── ids.py                    # ID generators (agent_id, conversation_id, etc.)
│   ├── logging.py                # Structured logging setup
│   ├── errors.py                 # Custom exceptions
│   └── ...
└── __init__.py
```

**NO existing `/channels/` directory** — this is where the new feature will be added.

---

## 2. AgentOrchestrator Class Signature & Key Methods

**File**: `src/aegis/core/orchestrator.py`

### Constructor
```python
class AgentOrchestrator:
    """Manages agent sessions and the tool execution loop."""

    def __init__(
        self,
        db: Any,                              # Database instance
        repositories: Any,                    # Repositories dataclass
        tool_registry: Any,                   # ToolRegistry instance
        memory_store: Any | None = None,      # MemoryStore for semantic search
        skills_loader: Any | None = None,     # SkillsLoader
    ) -> None:
        self._db = db
        self._repos = repositories
        self._tools = tool_registry
        self._memory = memory_store
        self._skills = skills_loader
        self._sessions: dict[str, AgentSession] = {}
        self._tool_loop = ToolLoop(...)  # Manages the agentic loop
```

### Key Methods

#### 1. **create_session()** — Create a new agent session
```python
def create_session(
    self,
    session_id: str | None = None,
    conversation_id: str | None = None,
    config: AgentConfig | None = None,
) -> AgentSession:
    """Create a new agent session."""
    sess = AgentSession(
        session_id=session_id or new_session_id(),
        conversation_id=conversation_id,
        config=config or AgentConfig(),
    )
    self._sessions[sess.id] = sess
    logger.info("Session created", session_id=sess.id, conversation_id=conversation_id)
    return sess
```

#### 2. **send_message()** — Run agent and stream response (MAIN INTERFACE)
```python
async def send_message(
    self,
    session_id: str,
    conversation_id: str,
    content: str,                              # User message
    config: AgentConfig | None = None,
) -> AsyncIterator[StreamEvent]:
    """Send a message and stream the response.
    
    Yields StreamEvent objects (TEXT_DELTA, TOOL_START, TOOL_RESULT, DONE, ERROR).
    """
    sess = self.get_session(session_id)
    sess.reset_cancel()
    sess.set_streaming(True)
    sess.touch()

    effective_config = config or sess.config

    try:
        async for event in self._tool_loop.run(
            session=sess,
            conversation_id=conversation_id,
            user_message=content,
            config=effective_config,
        ):
            yield event
    except Exception as e:
        logger.error("Tool loop error", session_id=session_id, error=str(e))
        yield StreamEvent(type=StreamEventType.ERROR, error=str(e))
    finally:
        sess.set_streaming(False)
```

#### 3. Other Methods
```python
def get_session(self, session_id: str) -> AgentSession
def cancel_session(self, session_id: str) -> None
def close_session(self, session_id: str) -> None
@property
def active_sessions(self) -> int
```

---

## 3. AgentConfig Type Definition

**File**: `src/aegis/core/types.py`

```python
class AgentConfig(BaseModel):
    """Configuration for an agent run."""
    provider: str = "anthropic"           # "anthropic", "openai", "ollama"
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = True
    enable_skills: bool = True
    tool_names: list[str] | None = None   # None = all available
    max_tool_iterations: int = 50
    agent_id: str = ""                    # Agent ID (optional)
    user_id: str = ""                     # User ID (optional)
```

---

## 4. StreamEventType & StreamEvent

**File**: `src/aegis/core/types.py`

```python
class StreamEventType(str, Enum):
    SESSION_READY = "session_ready"
    TEXT_DELTA = "text_delta"             # Incremental LLM output
    TOOL_START = "tool_start"             # Tool invocation starting
    TOOL_RESULT = "tool_result"           # Tool result returned
    DONE = "done"                         # Response complete
    ERROR = "error"                       # Error occurred
    CANCELLED = "cancelled"

class StreamEvent(BaseModel):
    """An event emitted during agent streaming."""
    type: StreamEventType
    text: str | None = None               # For TEXT_DELTA
    tool_name: str | None = None          # For TOOL_START
    tool_id: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None        # For TOOL_RESULT
    is_error: bool | None = None
    message_id: str | None = None         # For DONE
    usage: dict[str, int] | None = None   # Token counts
    error: str | None = None              # For ERROR
```

---

## 5. Database Schema & Migrations

**Backend Support**: SQLite (dev) + PostgreSQL (prod)

### Database Class

**File**: `src/aegis/storage/database.py`

```python
class Database:
    """Async database wrapper supporting SQLite and PostgreSQL."""

    def __init__(
        self,
        database_url: str = "",
        db_path: str | Path = "data/aegis.db",
        wal_mode: bool = True,
        pool_min: int = 2,
        pool_max: int = 10,
    ) -> None:
        # Auto-detects backend from database_url
        # SQLite if empty or starts with "sqlite"
        # PostgreSQL if starts with "postgresql"
        ...

    async def connect(self) -> None:
        """Open connection and run migrations."""
        
    async def execute(self, sql: str, params: tuple = ()) -> Any
    async def fetchone(self, sql: str, params: tuple = ()) -> Any | None
    async def fetchall(self, sql: str, params: tuple = ()) -> list[Any]
    async def commit(self) -> None
    
    async def _run_migrations(self) -> None:
        """Auto-runs .sql files from migrations/sqlite/ or migrations/pg/"""
```

**Parameter Style**: Uses PostgreSQL-style `$1, $2` placeholders.
- For SQLite: auto-converts to `?`
- For PostgreSQL: uses native `$N` style

### Core Tables (from SQLite migrations)

#### conversations
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'anthropic',
    model TEXT NOT NULL DEFAULT 'claude-sonnet-4-5',
    system_prompt TEXT,
    user_id TEXT,                    -- FK to users (added in migration 003)
    agent_id TEXT,                   -- FK to agents (added in migration 004)
    metadata TEXT DEFAULT '{}'
);
```

#### messages
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,   -- FK to conversations
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system')),
    content TEXT NOT NULL DEFAULT '[]',  -- JSON
    tool_calls TEXT DEFAULT NULL,        -- JSON
    tool_call_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}'
);
```

#### agents
```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,              -- FK to users
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    avatar_url TEXT,
    status TEXT DEFAULT 'active' 
        CHECK (status IN ('draft', 'active', 'paused', 'archived')),
    is_public INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    provider TEXT DEFAULT 'anthropic',
    model TEXT DEFAULT 'claude-sonnet-4-5',
    temperature REAL DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 4096,
    system_prompt TEXT DEFAULT '',
    enable_memory INTEGER DEFAULT 0,
    enable_skills INTEGER DEFAULT 0,
    max_tool_iterations INTEGER DEFAULT 10,
    allowed_tools TEXT DEFAULT '["web_fetch","file_read",...]',  -- JSON
    metadata TEXT DEFAULT '{}',
    UNIQUE(user_id, slug)
);
```

#### users (from migration 003)
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);
```

**Migration Pattern**: 
- Files are numbered (001_, 002_, etc.) and executed in order
- Schema tracking via `schema_migrations` table
- SQLite uses `migrations/sqlite/`, PostgreSQL uses `migrations/pg/`
- **No existing channel-related migrations**

---

## 6. Agent Model & Repository

**File**: `src/aegis/storage/repositories/agents.py`

### Agent Model
```python
class Agent(BaseModel):
    id: str
    user_id: str
    slug: str
    name: str
    description: str = ""
    avatar_url: str | None = None
    status: str = "active"                    # draft, active, paused, archived
    is_public: bool = False
    created_at: str
    updated_at: str
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = False
    enable_skills: bool = False
    max_tool_iterations: int = 10
    allowed_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### AgentCreate (for creation)
```python
class AgentCreate(BaseModel):
    user_id: str
    name: str
    slug: str
    description: str = ""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    system_prompt: str = ""
    enable_memory: bool = False
    enable_skills: bool = False
    max_tool_iterations: int = 10
    allowed_tools: list[str] = Field(...)
```

### AgentRepository
```python
class AgentRepository:
    async def create(self, data: AgentCreate) -> Agent
    async def get(self, agent_id: str) -> Agent | None
    async def get_by_slug(self, user_id: str, slug: str) -> Agent | None
    async def list_by_user(self, user_id: str, status: str | None = None,
                          limit: int = 100, offset: int = 0) -> list[Agent]
    async def update(self, agent_id: str, data: AgentUpdate) -> Agent | None
    async def delete(self, agent_id: str) -> bool
```

---

## 7. Conversation & Message Models

**File**: `src/aegis/storage/repositories/conversations.py` & `messages.py`

### Conversation Model
```python
class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    provider: str
    model: str
    system_prompt: str | None = None
    user_id: str | None = None             # Owner
    agent_id: str | None = None            # Associated agent (optional)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ConversationCreate(BaseModel):
    title: str = "New Conversation"
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    system_prompt: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Message Model
```python
class ContentPart(BaseModel):
    type: str                               # "text", "tool_use", etc.
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    content: Any = None
    is_error: bool | None = None

class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: str | None = None
    is_error: bool = False

class Message(BaseModel):
    id: str
    conversation_id: str
    role: str                               # "user", "assistant", "tool", "system"
    content: list[ContentPart] | str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    created_at: str
    tokens_used: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_text_content(self) -> str:
        """Extract plain text from content."""
```

### ConversationRepository
```python
class ConversationRepository:
    async def create(self, data: ConversationCreate) -> Conversation
    async def get(self, conv_id: str) -> Conversation
    async def list_all(self, limit: int = 100, offset: int = 0,
                      user_id: str | None = None,
                      agent_id: str | None = None) -> list[Conversation]
    async def update(self, conv_id: str, data: ConversationUpdate) -> Conversation
    async def delete(self, conv_id: str) -> None
    async def touch(self, conv_id: str) -> None  # Update updated_at timestamp
```

### MessageRepository
```python
class MessageRepository:
    async def create(self, data: MessageCreate) -> Message
    async def get_by_conversation(self, conversation_id: str) -> list[Message]
    async def get(self, message_id: str) -> Message | None
```

---

## 8. Lifespan Services Wiring

**File**: `src/aegis/app.py` — **create_app() and lifespan context manager**

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown."""
    settings = app.state.settings

    # 1. Configure logging
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    # 2. Initialize database
    db = Database(
        database_url=settings.storage.database_url,
        db_path=settings.storage.db_path,
        wal_mode=settings.storage.wal_mode,
        pool_min=settings.storage.pool_min,
        pool_max=settings.storage.pool_max,
    )
    await db.connect()  # Runs migrations automatically
    set_db_instance(db)  # Module-level singleton

    # 3. Create repositories
    repos = get_repositories(db)
    app.state.db = db
    app.state.repositories = repos

    # 4. Initialize auth service
    app.state.jwt_secret = settings.auth.jwt_secret
    app.state.auth_service = AuthService(...)

    # 5. Initialize LLM providers
    initialize_providers(
        anthropic_api_key=settings.llm.anthropic_api_key,
        anthropic_base_url=settings.llm.anthropic_base_url,
        openai_api_key=settings.llm.openai_api_key,
        ollama_base_url=settings.llm.ollama_base_url,
    )

    # 6. Initialize tool registry
    tool_registry = ToolRegistry()
    tool_registry.register_builtins(
        bash_enabled=settings.tools.bash_enabled,
        web_fetch_enabled=settings.tools.web_fetch_enabled,
        file_ops_enabled=settings.tools.file_ops_enabled,
    )
    app.state.tool_registry = tool_registry

    # 7. Initialize memory store (ChromaDB)
    memory_store = None
    knowledge_service = None
    try:
        from .memory.store import MemoryStore
        memory_store = MemoryStore(...)
        await memory_store.initialize()
        ...
    except Exception as e:
        logger.warning("Memory initialization failed (optional)", error=str(e))
    app.state.memory_store = memory_store
    app.state.knowledge_service = knowledge_service

    # 8. Initialize orchestrator (**KEY OBJECT**)
    orchestrator = AgentOrchestrator(
        db=db,
        repositories=repos,
        tool_registry=tool_registry,
        memory_store=memory_store,
    )
    app.state.orchestrator = orchestrator

    # 9. Initialize webhook dispatcher
    webhook_dispatcher = WebhookDispatcher(...)
    app.state.webhook_dispatcher = webhook_dispatcher

    # 10. Initialize and start cron scheduler
    cron_scheduler = None
    if settings.cron.enabled:
        cron_scheduler = CronScheduler(...)
        await cron_scheduler.start()
    app.state.cron_scheduler = cron_scheduler

    yield

    # Shutdown
    if cron_scheduler:
        await cron_scheduler.stop()
    await db.close()
```

**All key services are stored in `app.state` and accessible in routes via `request.app.state`.**

---

## 9. Channel-Related Code Check

✅ **Result**: NO existing channel-related code found.

```bash
$ find /home/hazo/projects/aegis/src/aegis -type d -name "*channel*"
# (no output — doesn't exist)

$ grep -r "channel" /home/hazo/projects/aegis/src/aegis/ --include="*.py"
# (no matches)
```

However, there IS existing multi-platform webhook support (Slack, Discord, Teams) in:
- `src/aegis/api/routes/webhooks.py` — Shows integration patterns

---

## 10. API Routes Directory Structure

**File**: `src/aegis/api/routes/`

```
routes/
├── agents.py              # Agent CRUD
├── agent_api.py           # Public API: POST /v1/agents/{id}/messages
├── api_keys.py            # API key management
├── auth.py                # Login, register
├── conversations.py       # Conversation CRUD + message listing
├── health.py              # GET /api/health
├── knowledge.py           # Knowledge base upload/search
├── mcp_oauth.py           # MCP OAuth callbacks
├── scheduled_tasks.py     # Task scheduler CRUD
├── webhooks.py            # **Webhook CRUD + inbound trigger** (already handles Slack/Discord/Teams)
└── __init__.py
```

---

## 11. Dependencies

**File**: `pyproject.toml`

### Core Dependencies
```toml
# Web Framework
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
websockets>=13.0
python-multipart>=0.0.12

# LLM Providers
anthropic>=0.40.0
openai>=1.55.0
ollama>=0.4.0
tiktoken>=0.8.0

# Storage
aiosqlite>=0.20.0
asyncpg>=0.30.0

# Auth
pyjwt>=2.9.0
bcrypt>=4.2.0

# Configuration
pydantic>=2.10.0
pydantic-settings>=2.6.0

# Utilities
httpx>=0.28.0
structlog>=24.4.0
rich>=13.9.0
jinja2>=3.1.0
pyyaml>=6.0.0
croniter>=2.0.0
pyngrok>=7.0.0
html2text>=2024.2.26
```

### Optional Dependencies
```toml
[optional]
chromadb>=0.5.0          # Memory/semantic search
playwright>=1.48.0       # Browser automation
apscheduler>=3.10.0      # Task scheduling
python-frontmatter>=1.1.0 # Skills parsing
```

---

## 12. Real-World Usage Examples

### Example 1: Send Message via Public API (from `agent_api.py`)

```python
# 1. Create session
config = AgentConfig(
    provider=agent.provider,
    model=agent.model,
    temperature=agent.temperature,
    max_tokens=agent.max_tokens,
    system_prompt=agent.system_prompt,
    enable_memory=agent.enable_memory,
    enable_skills=agent.enable_skills,
    tool_names=agent.allowed_tools,
    max_tool_iterations=agent.max_tool_iterations,
)
session = orchestrator.create_session(config=config)

# 2. Run agent
full_text = ""
message_id = ""
usage = {"input": 0, "output": 0}

try:
    async for event in orchestrator.send_message(
        session_id=session.id,
        conversation_id=conversation_id,
        content=data.message,
        config=config,
    ):
        if event.type == StreamEventType.TEXT_DELTA and event.text:
            full_text += event.text
        elif event.type == StreamEventType.DONE:
            message_id = event.message_id or ""
            usage = event.usage or {"input": 0, "output": 0}
        elif event.type == StreamEventType.ERROR:
            raise HTTPException(status_code=500, detail=event.error)
finally:
    orchestrator.close_session(session.id)

# 3. Return response
return {
    "conversation_id": conversation_id,
    "message_id": message_id,
    "response": full_text,
    "usage": usage,
}
```

### Example 2: Webhook-Based Trigger (from `webhooks.py`)

```python
# 1. Lookup webhook by slug
webhook = await repos.webhooks.get_by_slug(slug)
if not webhook or webhook.direction != "inbound":
    raise HTTPException(status_code=404, detail="Webhook not found")

# 2. Extract message (auto-detects Slack/Discord/Teams format)
message = _extract_message_from_dict(payload)

# 3. Get agent and create conversation
agent = await repos.agents.get(webhook.agent_id)
conv = await repos.conversations.create(ConversationCreate(...))

# 4. Run agent (same pattern as public API)
config = _agent_to_config(agent)
session = orchestrator.create_session(config=config)

full_text = ""
try:
    async for event in orchestrator.send_message(
        session_id=session.id,
        conversation_id=conv.id,
        content=message,
        config=config,
    ):
        if event.type == StreamEventType.TEXT_DELTA and event.text:
            full_text += event.text
        # ... handle other event types ...
finally:
    orchestrator.close_session(session.id)

# 5. Return response in platform-specific format
if response_format == "slack":
    return {"text": full_text}
elif response_format == "discord":
    return {"content": full_text}
elif response_format == "teams":
    return {"type": "message", "text": full_text}
```

---

## Summary: How to Use AgentOrchestrator

### Pattern for Non-Streaming (Request/Response)

```python
# 1. Create session
session = orchestrator.create_session(
    conversation_id=conv_id,
    config=AgentConfig(...)
)

# 2. Stream events and accumulate response
full_text = ""
message_id = ""
usage = {}

try:
    async for event in orchestrator.send_message(
        session_id=session.id,
        conversation_id=conv_id,
        content=user_message,
        config=session.config,
    ):
        if event.type == StreamEventType.TEXT_DELTA:
            full_text += event.text or ""
        elif event.type == StreamEventType.DONE:
            message_id = event.message_id
            usage = event.usage
        elif event.type == StreamEventType.ERROR:
            # Handle error
            raise Exception(event.error)
finally:
    orchestrator.close_session(session.id)

# 3. Return accumulated response
return {"response": full_text, "message_id": message_id, "usage": usage}
```

### Pattern for Streaming (WebSocket)

```python
async for event in orchestrator.send_message(...):
    # Send each event to WebSocket client
    await websocket.send_json(event.to_ws_dict())
```

---

## Database Migration Pattern

To add a new table (e.g., for channels):

1. **Create migration files**:
   - `src/aegis/storage/migrations/sqlite/NNN_channels.sql`
   - `src/aegis/storage/migrations/pg/NNN_channels.sql`

2. **Example migration** (SQLite):
```sql
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_type TEXT NOT NULL,  -- "slack", "telegram", "discord", etc.
    external_id TEXT NOT NULL,   -- Slack channel ID, etc.
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}',
    UNIQUE(agent_id, channel_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_channels_agent ON channels(agent_id);
CREATE INDEX IF NOT EXISTS idx_channels_type ON channels(channel_type);
```

3. **Automatic execution**:
   - When `db.connect()` is called in lifespan
   - Database class auto-runs all `.sql` files in numerical order
   - Tracks via `schema_migrations` table to avoid re-running

---

## Key Takeaways

1. ✅ **AgentOrchestrator** is the single interface for running agents
   - Methods: `create_session()`, `send_message()`, `close_session()`
   - `send_message()` returns `AsyncIterator[StreamEvent]` (streaming)

2. ✅ **Database** supports both SQLite and PostgreSQL with automatic migrations

3. ✅ **Conversation + Message models** store full chat history

4. ✅ **Agent model** has `metadata` field for extensibility (add channel connection details there)

5. ✅ **Webhook infrastructure** exists and already handles Slack/Discord/Teams detection

6. ✅ **NO channels module exists** — ready for new implementation

7. ✅ **Repositories pattern** allows clean separation of concerns

8. ✅ **Stream events** allow both real-time WebSocket streaming and non-streaming request/response
