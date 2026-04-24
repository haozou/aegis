# Configuration

Aegis uses [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for configuration. All settings can be set via environment variables or a `.env` file in the project root.

Nested settings use the `__` (double underscore) delimiter in environment variables. For example, `llm__default_model` becomes `LLM__DEFAULT_MODEL`.

## Top-Level Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `APP_NAME` | string | `"Aegis"` | Application name |
| `DEBUG` | bool | `false` | Enable debug mode |
| `LOG_LEVEL` | string | `"INFO"` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | string | `"rich"` | Log format: `rich` (console) or `json` |
| `DATA_DIR` | path | `data` | Base directory for runtime data |

## LLM Providers

| Variable | Default | Description |
|----------|---------|-------------|
| `LITELLM_BASE_URL` | — | LiteLLM proxy URL (when set, only LiteLLM is registered) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `ANTHROPIC_BASE_URL` | — | Custom Anthropic endpoint |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_BASE_URL` | — | Custom OpenAI-compatible endpoint |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `LLM__DEFAULT_PROVIDER` | `"anthropic"` | Default LLM provider |
| `LLM__DEFAULT_MODEL` | `"claude-sonnet-4-5"` | Default model |
| `LLM__TEMPERATURE` | `0.7` | Default temperature |
| `LLM__MAX_TOKENS` | `4096` | Default max tokens |
| `LLM__TIMEOUT` | `120.0` | Request timeout (seconds) |
| `LLM__MAX_RETRIES` | `3` | Max retry attempts |

**Provider priority**: If `LITELLM_BASE_URL` is set, only LiteLLM is registered (acts as a universal router). Otherwise, individual providers are registered based on available API keys.

## Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string (e.g., `postgresql://user:pass@host:5432/db`) |
| `STORAGE__DB_PATH` | `data/aegis.db` | SQLite database path (used when `DATABASE_URL` is empty) |
| `STORAGE__WAL_MODE` | `true` | Enable WAL mode for SQLite |
| `STORAGE__CONNECTION_TIMEOUT` | `30.0` | Connection timeout (seconds) |
| `STORAGE__POOL_MIN` | `2` | Minimum connection pool size (PostgreSQL) |
| `STORAGE__POOL_MAX` | `10` | Maximum connection pool size (PostgreSQL) |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | `"change-me-in-production-please"` | **Required in production**. JWT signing secret (min 32 chars) |
| `AUTH__ACCESS_TOKEN_EXPIRE_SECONDS` | `3600` | Access token lifetime (1 hour) |
| `AUTH__REFRESH_TOKEN_EXPIRE_SECONDS` | `604800` | Refresh token lifetime (7 days) |
| `AUTH__ALLOW_REGISTRATION` | `true` | Allow new user registration |

## OAuth

| Variable | Default | Description |
|----------|---------|-------------|
| `OAUTH_REDIRECT_BASE` | `http://localhost:8000` | Base URL for OAuth callbacks |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `GITHUB_CLIENT_ID` | — | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | — | GitHub OAuth client secret |
| `MICROSOFT_CLIENT_ID` | — | Microsoft OAuth client ID |
| `MICROSOFT_CLIENT_SECRET` | — | Microsoft OAuth client secret |
| `MICROSOFT_TENANT` | `"common"` | Microsoft tenant ID |

## Memory

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY__ENABLED` | `true` | Enable semantic memory |
| `MEMORY__CHROMA_PATH` | `data/chroma` | ChromaDB storage path |
| `MEMORY__COLLECTION_NAME` | `"aegis_memory"` | Default collection name |
| `MEMORY__EMBEDDING_MODEL` | `"all-MiniLM-L6-v2"` | SentenceTransformer model |
| `MEMORY__MAX_RESULTS` | `5` | Max memory results per query |
| `MEMORY__MIN_RELEVANCE` | `0.3` | Minimum relevance threshold |
| `MEMORY__AUTO_EMBED` | `true` | Auto-embed messages |

## Tools

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS__BASH_ENABLED` | `true` | Enable bash tool |
| `TOOLS__BASH_TIMEOUT` | `30` | Bash command timeout (seconds) |
| `TOOLS__BASH_MAX_OUTPUT` | `51200` | Max bash output (bytes, 50KB) |
| `TOOLS__WEB_FETCH_ENABLED` | `true` | Enable web fetch tool |
| `TOOLS__WEB_FETCH_TIMEOUT` | `30` | Fetch timeout (seconds) |
| `TOOLS__WEB_FETCH_MAX_CHARS` | `20000` | Max fetched content length |
| `TOOLS__FILE_OPS_ENABLED` | `true` | Enable file operations |
| `TOOLS__FILE_SANDBOX_PATH` | `data/sandbox` | File sandbox directory |
| `TOOLS__ALLOWED_PATHS` | `["data/sandbox", "~"]` | Allowed file access paths |
| `TOOLS__VIDEO_ENABLED` | `true` | Enable video tools |
| `TOOLS__VIDEO_TIMEOUT` | `600` | Video operation timeout (10 min) |
| `TOOLS__IMAGE_GEN_ENABLED` | `true` | Enable image generation |
| `TOOLS__DOCUMENT_EXPORT_ENABLED` | `true` | Enable document export |
| `TOOLS__PYTHON_INTERPRETER_ENABLED` | `true` | Enable Python REPL |
| `TOOLS__PYTHON_INTERPRETER_TIMEOUT` | `120` | Python execution timeout (seconds) |

## Skills

| Variable | Default | Description |
|----------|---------|-------------|
| `SKILLS__ENABLED` | `true` | Enable skills system |
| `SKILLS__SKILLS_DIR` | `skills` | Skills directory path |
| `SKILLS__HOT_RELOAD` | `true` | Watch for skill file changes |
| `SKILLS__BUILTIN_SKILLS` | `true` | Load built-in skills |

## API Server

| Variable | Default | Description |
|----------|---------|-------------|
| `API__HOST` | `127.0.0.1` | Server bind address |
| `API__PORT` | `8000` | Server port |
| `API__CORS_ORIGINS` | `["http://localhost:5173", ...]` | Allowed CORS origins |
| `API__CORS_ALLOW_CREDENTIALS` | `true` | Allow credentials in CORS |
| `API__LOG_REQUESTS` | `true` | Log HTTP requests |

## Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOKS__ENABLED` | `true` | Enable webhook dispatcher |
| `WEBHOOKS__MAX_RETRIES` | `3` | Max delivery retries |
| `WEBHOOKS__RETRY_DELAY` | `5` | Retry delay (seconds) |
| `WEBHOOKS__TIMEOUT` | `30` | Delivery timeout (seconds) |

## Cron Scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `CRON__ENABLED` | `true` | Enable cron scheduler |
| `CRON__TICK_INTERVAL` | `60` | Scheduler tick interval (seconds) |

## Example `.env` File

```env
# Required
JWT_SECRET=your-secret-key-at-least-32-characters-long

# LLM - pick one or more
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...
# LITELLM_BASE_URL=http://localhost:5000

# Database (omit for SQLite)
# DATABASE_URL=postgresql://aegis:aegis@localhost:5432/aegis

# Optional: OAuth
# GOOGLE_CLIENT_ID=...
# GOOGLE_CLIENT_SECRET=...

# Optional: Tuning
# LOG_LEVEL=DEBUG
# LLM__DEFAULT_MODEL=gpt-4o
# TOOLS__BASH_TIMEOUT=60
```
