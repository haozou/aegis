"""Aegis entry point — run with `python -m aegis`."""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    """Start the Aegis server."""
    settings = get_settings()

    uvicorn.run(
        "aegis.app:create_app",
        factory=True,
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
