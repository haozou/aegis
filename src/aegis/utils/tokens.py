"""Token counting utilities."""

from __future__ import annotations

import tiktoken


_ENCODING_CACHE: dict[str, tiktoken.Encoding] = {}


def _get_encoding(model: str) -> tiktoken.Encoding:
    """Get cached encoding for model."""
    if model in _ENCODING_CACHE:
        return _ENCODING_CACHE[model]
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # Default to cl100k_base for unknown models
        enc = tiktoken.get_encoding("cl100k_base")
    _ENCODING_CACHE[model] = enc
    return enc


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count the number of tokens in text."""
    enc = _get_encoding(model)
    return len(enc.encode(text))


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    """Truncate text to at most max_tokens tokens."""
    enc = _get_encoding(model)
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    truncated = tokens[:max_tokens]
    return enc.decode(truncated)
