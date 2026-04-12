"""
ASGI import target for :mod:`hubvault.server`.

Deployment tools such as ``uvicorn`` and ``gunicorn`` can import
``hubvault.server.asgi:create_app`` directly and still reach the same runtime
factory used by the quick-start helpers.
"""

from typing import Optional

from .app import create_app as _create_app
from .config import ServerConfig


def create_app(config: Optional[ServerConfig] = None, **kwargs):
    """
    Create an ASGI app from environment variables or explicit config.

    :param config: Optional pre-built server configuration
    :type config: Optional[ServerConfig]
    :param kwargs: Keyword arguments used to build :class:`ServerConfig` when
        ``config`` is omitted
    :type kwargs: dict
    :return: Configured FastAPI application
    :rtype: fastapi.FastAPI
    """

    return _create_app(config=config, **kwargs)
