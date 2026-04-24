"""Aegis error hierarchy."""

from __future__ import annotations


class AegisError(Exception):
    """Base error for all Aegis exceptions."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__

    def __str__(self) -> str:
        return self.message


class ConfigError(AegisError):
    """Configuration-related errors."""


class LLMError(AegisError):
    """LLM provider errors."""


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""


class LLMAuthError(LLMError):
    """Authentication/API key error."""


class LLMTimeoutError(LLMError):
    """Request timed out."""


class ToolError(AegisError):
    """Tool execution errors."""


class ToolTimeoutError(ToolError):
    """Tool execution timed out."""


class StorageError(AegisError):
    """Storage/database errors."""


class SessionNotFoundError(AegisError):
    """WebSocket session not found."""


class ConversationNotFoundError(AegisError):
    """Conversation not found."""


class MemoryError(AegisError):
    """Memory/embedding errors."""


class SkillError(AegisError):
    """Skills system errors."""


class AuthError(AegisError):
    """Authentication/authorization errors."""


class AuthTokenExpiredError(AuthError):
    """JWT token has expired."""


class UserNotFoundError(AegisError):
    """User not found."""
