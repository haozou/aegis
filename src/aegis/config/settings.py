"""Application settings using pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LiteLLM proxy — set this to route ALL models through one endpoint
    litellm_base_url: str = Field(default="", alias="LITELLM_BASE_URL")
    # Legacy individual-provider settings (used when litellm_base_url is not set)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_base_url: str = Field(default="", alias="ANTHROPIC_BASE_URL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="", alias="OPENAI_BASE_URL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    default_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    default_model: str = "claude-sonnet-4-5"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 120.0
    max_retries: int = 3


class MemoryConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    chroma_path: Path = Path("data/chroma")
    collection_name: str = "aegis_memory"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_results: int = 5
    min_relevance: float = 0.3
    auto_embed: bool = True


class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default="", alias="DATABASE_URL")
    db_path: Path = Path("data/aegis.db")
    wal_mode: bool = True
    connection_timeout: float = 30.0
    pool_min: int = 2
    pool_max: int = 10


class SkillsConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    skills_dir: Path = Path("skills")
    hot_reload: bool = True
    builtin_skills: bool = True


class ToolsConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    bash_enabled: bool = True
    bash_timeout: int = 30
    bash_max_output: int = 51200  # 50KB
    web_fetch_enabled: bool = True
    web_fetch_timeout: int = 30
    web_fetch_max_chars: int = 20000
    file_ops_enabled: bool = True
    file_sandbox_path: Path = Path("data/sandbox")
    allowed_paths: list[str] = Field(default_factory=lambda: ["data/sandbox", "~"])
    video_enabled: bool = True
    video_timeout: int = 600  # 10 minutes for long ffmpeg operations
    image_gen_enabled: bool = True
    document_export_enabled: bool = True
    python_interpreter_enabled: bool = True
    python_interpreter_timeout: int = 120


class APIConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ])
    cors_allow_credentials: bool = True
    log_requests: bool = True


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    jwt_secret: str = Field(default="change-me-in-production-please", alias="JWT_SECRET")
    access_token_expire_seconds: int = 3600  # 1 hour
    refresh_token_expire_seconds: int = 604800  # 7 days
    allow_registration: bool = True


class OAuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base URL for OAuth redirect URIs (e.g. https://app.creativeaegis.com)
    redirect_base: str = Field(default="http://localhost:8000", alias="OAUTH_REDIRECT_BASE")

    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")

    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")

    microsoft_client_id: str = Field(default="", alias="MICROSOFT_CLIENT_ID")
    microsoft_client_secret: str = Field(default="", alias="MICROSOFT_CLIENT_SECRET")
    microsoft_tenant: str = Field(default="common", alias="MICROSOFT_TENANT")


class WebhooksConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 5
    timeout: int = 30


class CronConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    tick_interval: int = 60


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "Aegis"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["rich", "json"] = "rich"
    data_dir: Path = Path("data")

    llm: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    oauth: OAuthConfig = Field(default_factory=OAuthConfig)
    webhooks: WebhooksConfig = Field(default_factory=WebhooksConfig)
    cron: CronConfig = Field(default_factory=CronConfig)

    @field_validator("data_dir", "storage", "memory", mode="before")
    @classmethod
    def resolve_paths(cls, v: object) -> object:
        return v
