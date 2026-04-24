"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes.agents import router as agents_router
from .api.routes.agent_api import router as agent_api_router
from .api.routes.api_keys import router as api_keys_router
from .api.routes.auth import router as auth_router
from .api.routes.oauth import router as oauth_router
from .api.routes.channels import router as channels_router
from .api.routes.conversations import router as conversations_router
from .api.routes.files import router as files_router
from .api.routes.health import router as health_router
from .api.routes.knowledge import router as knowledge_router
from .api.routes.mcp_oauth import router as mcp_oauth_router
from .api.routes.models import router as models_router
from .api.routes.scheduled_tasks import router as schedules_router
from .api.routes.webhooks import router as webhooks_router
from .api.websocket import router as websocket_router
from .auth.service import AuthService
from .config import get_settings
from .core.orchestrator import AgentOrchestrator
from .llm.registry import initialize_providers
from .services.cron_scheduler import CronScheduler
from .services.webhook_dispatcher import WebhookDispatcher
from .channels.manager import ChannelManager
from .storage.database import Database, set_db_instance
from .storage.repositories import get_repositories
from .tools.registry import ToolRegistry
from .utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown."""
    settings = app.state.settings

    # Configure logging
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    # Initialize database
    db = Database(
        database_url=settings.storage.database_url,
        db_path=settings.storage.db_path,
        wal_mode=settings.storage.wal_mode,
        pool_min=settings.storage.pool_min,
        pool_max=settings.storage.pool_max,
    )
    await db.connect()
    set_db_instance(db)

    # Create repositories
    repos = get_repositories(db)
    app.state.db = db
    app.state.repositories = repos

    # Initialize auth service
    app.state.jwt_secret = settings.auth.jwt_secret
    app.state.auth_service = AuthService(
        user_repo=repos.users,
        jwt_secret=settings.auth.jwt_secret,
    )

    # Initialize LLM providers
    initialize_providers(
        anthropic_api_key=settings.llm.anthropic_api_key,
        anthropic_base_url=settings.llm.anthropic_base_url,
        openai_api_key=settings.llm.openai_api_key,
        openai_base_url=settings.llm.openai_base_url,
        litellm_base_url=settings.llm.litellm_base_url,
        ollama_base_url=settings.llm.ollama_base_url,
    )
    # Warm up model list cache
    try:
        from .llm.registry import get_provider
        _p = get_provider()
        if hasattr(_p, "list_models"):
            await _p.list_models()
            logger.info("LLM model list cached", provider=type(_p).__name__)
    except Exception as e:
        logger.warning("LLM warm-up failed", error=str(e))

    # Initialize tool registry
    tool_registry = ToolRegistry()
    tool_registry.register_builtins(
        bash_enabled=settings.tools.bash_enabled,
        web_fetch_enabled=settings.tools.web_fetch_enabled,
        file_ops_enabled=settings.tools.file_ops_enabled,
        video_enabled=settings.tools.video_enabled,
        image_gen_enabled=settings.tools.image_gen_enabled,
        document_export_enabled=settings.tools.document_export_enabled,
        python_interpreter_enabled=settings.tools.python_interpreter_enabled,
    )
    app.state.tool_registry = tool_registry

    # Initialize memory store (ChromaDB)
    memory_store = None
    knowledge_service = None
    try:
        from .memory.store import MemoryStore
        memory_store = MemoryStore(
            chroma_path=getattr(settings.memory, 'chroma_path', 'data/chroma'),
            embedding_model=getattr(settings.memory, 'embedding_model', 'all-MiniLM-L6-v2'),
        )
        await memory_store.initialize()
        if memory_store.available:
            logger.info("Memory store initialized")
            # Initialize knowledge service on top of memory store
            from .knowledge.service import KnowledgeService
            knowledge_service = KnowledgeService(memory_store)
    except Exception as e:
        logger.warning("Memory/knowledge initialization failed (optional)", error=str(e))
    app.state.memory_store = memory_store
    app.state.knowledge_service = knowledge_service

    # Initialize orchestrator
    orchestrator = AgentOrchestrator(
        db=db,
        repositories=repos,
        tool_registry=tool_registry,
        memory_store=memory_store,
    )
    app.state.orchestrator = orchestrator

    # Initialize webhook dispatcher
    webhook_dispatcher = WebhookDispatcher(
        repositories=repos,
        max_retries=settings.webhooks.max_retries,
        retry_delay=settings.webhooks.retry_delay,
        timeout=settings.webhooks.timeout,
    )
    app.state.webhook_dispatcher = webhook_dispatcher

    # Initialize and start cron scheduler
    cron_scheduler: CronScheduler | None = None
    if settings.cron.enabled:
        cron_scheduler = CronScheduler(
            repositories=repos,
            orchestrator=orchestrator,
            tool_registry=tool_registry,
            db=db,
            memory_store=memory_store,
            webhook_dispatcher=webhook_dispatcher,
            tick_interval=settings.cron.tick_interval,
        )
        await cron_scheduler.start()
    app.state.cron_scheduler = cron_scheduler

    logger.info(
        "Aegis started",
        host=settings.api.host,
        port=settings.api.port,
        debug=settings.debug,
        tools=tool_registry.list_tools(),
        cron_enabled=settings.cron.enabled,
        webhooks_enabled=settings.webhooks.enabled,
    )

    # Initialize and start channel manager
    channel_manager = ChannelManager(repos=repos, orchestrator=orchestrator, db=db)
    await channel_manager.start()
    app.state.channel_manager = channel_manager

    yield

    # Shutdown
    await channel_manager.stop()
    if cron_scheduler:
        await cron_scheduler.stop()
    await db.close()
    logger.info("Aegis stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Aegis",
        description="Agent Factory Platform — Build, deploy, and run AI agents in the cloud",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store settings on app state for access in routes
    app.state.settings = settings

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=settings.api.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register route handlers
    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(oauth_router, prefix="/api")
    app.include_router(conversations_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")
    app.include_router(api_keys_router, prefix="/api")
    app.include_router(agent_api_router, prefix="/api")
    app.include_router(models_router, prefix="/api")
    app.include_router(webhooks_router, prefix="/api")
    app.include_router(channels_router, prefix="/api")
    app.include_router(schedules_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(mcp_oauth_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(websocket_router)

    return app
