# Aegis

**AI Agent Factory Platform** — Build, deploy, and run AI agents with tools, knowledge bases, and multi-channel delivery.

Aegis is a self-hosted platform for creating and managing AI agents powered by multiple LLM providers. Each agent gets its own system prompt, tool set, knowledge base, and can be deployed across channels like Discord, Telegram, email, and more.

## Features

- **Multi-provider LLM support** — Anthropic, OpenAI, Ollama, or any provider via LiteLLM proxy
- **Agentic tool loop** — Agents autonomously use tools (bash, web fetch, file ops, Python REPL, video editing, image generation, etc.)
- **Knowledge base (RAG)** — Per-agent document ingestion with semantic search via ChromaDB
- **Semantic memory** — Conversation-aware memory with SentenceTransformer embeddings
- **Skills system** — Markdown-based skill files with keyword triggers and hot-reload
- **Multi-channel** — Discord, Telegram, Email, SMS, WeChat adapters
- **MCP support** — Model Context Protocol client for stdio and HTTP+SSE transports
- **Agent delegation** — Agents can delegate tasks to other agents
- **Scheduled tasks** — Cron-based agent task scheduling
- **Webhooks** — Inbound/outbound webhook support with retry logic
- **OAuth** — Google, GitHub, Microsoft login + JWT auth
- **Real-time streaming** — WebSocket-based streaming with reconnection support
- **React frontend** — Modern UI built with React 19, Tailwind CSS 4, and shadcn/ui

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4, Zustand |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Embeddings | ChromaDB, SentenceTransformers |
| LLM | Anthropic, OpenAI, Ollama, LiteLLM |
| Auth | JWT + OAuth (Google, GitHub, Microsoft) |
| Containerization | Docker, Docker Compose |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 22+ (for frontend and MCP servers)
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Local Development

```bash
# Clone the repository
git clone https://github.com/haozou/aegis.git
cd aegis

# Install backend dependencies
make dev          # dev dependencies
make full         # all optional dependencies (ChromaDB, Playwright, etc.)

# Install frontend dependencies
make web-install

# Start both backend and frontend
make dev-all
```

The API server starts at `http://localhost:8000` and the frontend at `http://localhost:5173`.

### Environment Variables

Create a `.env` file in the project root:

```env
# LLM Providers (at least one required)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
LITELLM_BASE_URL=http://localhost:5000  # or use LiteLLM proxy

# Auth
JWT_SECRET=your-secret-key-min-32-chars

# Database (optional, defaults to SQLite)
DATABASE_URL=postgresql://aegis:aegis@localhost:5432/aegis

# OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
```

See [docs/configuration.md](docs/configuration.md) for all configuration options.

### Docker

```bash
# Start full stack (API + PostgreSQL + Frontend)
make docker-up

# With Cloudflare tunnel for public access
make docker-tunnel

# Stop
make docker-down
```

## Project Structure

```
aegis/
├── src/aegis/              # Backend application
│   ├── api/                # FastAPI routes & WebSocket
│   ├── auth/               # JWT & OAuth authentication
│   ├── channels/           # Multi-channel adapters
│   ├── config/             # Pydantic settings
│   ├── core/               # Agent orchestrator & tool loop
│   ├── knowledge/          # RAG knowledge base service
│   ├── llm/                # LLM provider abstraction
│   ├── memory/             # ChromaDB semantic memory
│   ├── services/           # Cron scheduler, webhook dispatcher
│   ├── skills/             # Markdown skill system
│   ├── storage/            # Database, migrations, repositories
│   ├── tools/              # Built-in tools & MCP client
│   └── utils/              # Logging, error handling, utilities
├── web/                    # React frontend
├── config/                 # Runtime configuration files
├── skills/                 # User-defined skill files
├── tests/                  # Unit, integration, e2e tests
├── docs/                   # Documentation
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── pyproject.toml
```

See [docs/architecture.md](docs/architecture.md) for a detailed architecture overview.

## Documentation

- [Architecture](docs/architecture.md) — System design, data flow, and component interactions
- [Configuration](docs/configuration.md) — All configuration options and environment variables
- [API Reference](docs/api.md) — REST API and WebSocket protocol
- [Tools](docs/tools.md) — Built-in tools and MCP integration
- [Skills](docs/skills.md) — Creating and managing agent skills

## Development

```bash
make test          # Run all tests
make test-unit     # Run unit tests only
make lint          # Run linter (ruff)
make format        # Format code
make typecheck     # Run mypy type checker
```

## License

MIT
