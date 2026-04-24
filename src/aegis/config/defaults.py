"""Default configuration values."""

from __future__ import annotations

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4.1",
    "ollama": "llama3.2",
}

DEFAULT_CONFIG_YAML = """# Aegis Configuration File
# Located at ~/.config/aegis/config.yaml
# All values can be overridden via environment variables

app_name: "Aegis"
debug: false
log_level: "INFO"
log_format: "rich"  # "rich" for development, "json" for production

# LLM Provider Settings
llm:
  default_provider: "anthropic"  # anthropic, openai, ollama
  default_model: "claude-sonnet-4-5"
  temperature: 0.7
  max_tokens: 4096
  timeout: 120.0
  max_retries: 3
  ollama_base_url: "http://localhost:11434"
  # API keys - prefer setting these as environment variables:
  # ANTHROPIC_API_KEY, OPENAI_API_KEY

# Memory / RAG Settings
memory:
  enabled: true
  chroma_path: "data/chroma"
  collection_name: "aegis_memory"
  embedding_model: "all-MiniLM-L6-v2"
  max_results: 5
  min_relevance: 0.3
  auto_embed: true

# Storage Settings
storage:
  db_path: "data/aegis.db"
  wal_mode: true

# Skills Settings
skills:
  enabled: true
  skills_dir: "skills"
  hot_reload: true
  builtin_skills: true

# Tools Settings
tools:
  bash_enabled: true
  bash_timeout: 30
  web_fetch_enabled: true
  web_fetch_timeout: 30
  file_ops_enabled: true
  file_sandbox_path: "data/sandbox"

# API Settings
api:
  host: "127.0.0.1"
  port: 8000
  cors_origins:
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"
    - "http://localhost:3000"
"""
