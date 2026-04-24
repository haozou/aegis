"""Configuration loader."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .defaults import DEFAULT_CONFIG_YAML
from .settings import AppConfig


def get_config_dir() -> Path:
    """Get the config directory, respecting XDG."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "aegis"
    return Path.home() / ".config" / "aegis"


def ensure_config_dir() -> Path:
    """Create config directory if it doesn't exist."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def write_default_config() -> Path:
    """Write the default config file if it doesn't exist."""
    config_dir = ensure_config_dir()
    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        config_file.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    return config_file


def load_settings() -> AppConfig:
    """Load settings from config file and environment variables."""
    config_file = write_default_config()

    # Load YAML config
    yaml_config: dict[str, object] = {}
    if config_file.exists():
        try:
            content = config_file.read_text(encoding="utf-8")
            yaml_config = yaml.safe_load(content) or {}
        except Exception:
            pass

    # Also check project-level config
    project_config = Path("config/default.yaml")
    if project_config.exists():
        try:
            content = project_config.read_text(encoding="utf-8")
            project_yaml = yaml.safe_load(content) or {}
            # Project config is lower priority than user config
            merged: dict[str, object] = {**project_yaml, **yaml_config}
            yaml_config = merged
        except Exception:
            pass

    # Create settings - env vars + .env override yaml
    # We pass yaml values as defaults but env vars will win
    return AppConfig(**yaml_config)  # type: ignore[arg-type]
