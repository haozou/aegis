"""Configuration module."""

from .loader import load_settings
from .settings import AppConfig

__all__ = ["AppConfig", "load_settings"]

# Module-level settings instance (lazy)
_settings: AppConfig | None = None


def get_settings() -> AppConfig:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
