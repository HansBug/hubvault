"""ASGI import target for production-style server startup."""

from typing import Optional

from .app import create_app as _create_app
from .config import ServerConfig


def create_app(config: Optional[ServerConfig] = None, **kwargs):
    """Create an ASGI app from environment variables or explicit config."""

    return _create_app(config=config, **kwargs)
