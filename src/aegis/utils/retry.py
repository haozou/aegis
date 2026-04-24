"""Async retry decorator with exponential backoff."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from .errors import LLMRateLimitError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (LLMRateLimitError,),
) -> Callable[[F], F]:
    """Retry decorator with exponential backoff for async functions."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            delay = base_delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait = min(delay, max_delay)
                        logger.warning(
                            "Retrying %s after %.1fs (attempt %d/%d): %s",
                            func.__name__,
                            wait,
                            attempt + 1,
                            max_attempts,
                            str(e),
                        )
                        await asyncio.sleep(wait)
                        delay *= backoff_factor
                    else:
                        raise

            if last_exception is not None:
                raise last_exception
            return None  # unreachable

        return wrapper  # type: ignore[return-value]

    return decorator
