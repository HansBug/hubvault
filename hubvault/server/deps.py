"""
Shared dependency helpers for :mod:`hubvault.server`.

This module centralizes lightweight dependency-construction helpers that are
shared by route factories and app bootstrap code.
"""

from typing import Callable, Optional

from ..api import HubVaultApi
from ..repo.backend import RepositoryBackend
from .auth import TokenAuthorizer
from .config import ServerConfig


def _resolve_default_branch(config: ServerConfig) -> str:
    """
    Resolve the current repository default branch for one server config.

    :param config: Server configuration bound to one repository root
    :type config: ServerConfig
    :return: Current repository default branch name
    :rtype: str
    :raises hubvault.errors.RepositoryNotFoundError: Raised when the configured
        repository does not exist.
    """

    return RepositoryBackend(config.repo_path).repo_info(revision=None).default_branch


def get_repo_api_factory(config: ServerConfig) -> Callable[[], HubVaultApi]:
    """
    Build a request-safe repository API factory for one server app.

    Each invocation returns a fresh :class:`hubvault.api.HubVaultApi` instance
    bound to the repository's current default branch. This avoids sharing
    mutable backend transaction state across concurrent HTTP requests.

    :param config: Server configuration bound to one repository root
    :type config: ServerConfig
    :return: Zero-argument callable that creates repository API wrappers
    :rtype: Callable[[], hubvault.api.HubVaultApi]
    """

    def _build_repo_api() -> HubVaultApi:
        return HubVaultApi(config.repo_path, revision=_resolve_default_branch(config))

    return _build_repo_api


def build_repo_api_getter(
    api: Optional[object] = None,
    api_factory: Optional[Callable[[], object]] = None,
) -> Callable[[], object]:
    """
    Normalize route-factory repository inputs to one getter callable.

    Route factories accept either a concrete API instance for focused tests or
    a zero-argument factory for production request handling.

    :param api: Optional concrete API object reused by the route
    :type api: Optional[object]
    :param api_factory: Optional factory returning API-like objects
    :type api_factory: Optional[Callable[[], object]]
    :return: Zero-argument callable that yields one API-like object
    :rtype: Callable[[], object]
    :raises TypeError: Raised when both ``api`` and ``api_factory`` are
        provided or when neither is provided.
    """

    if api is not None and api_factory is not None:
        raise TypeError("Pass either a concrete api instance or an api_factory, not both.")
    if api is None and api_factory is None:
        raise TypeError("A concrete api instance or api_factory is required.")
    if api is not None:
        return lambda: api
    return api_factory


def get_token_authorizer(config) -> TokenAuthorizer:
    """
    Build the shared token authorizer for one server app.

    :param config: Server configuration carrying normalized token lists
    :type config: hubvault.server.config.ServerConfig
    :return: Token authorizer bound to the config tokens
    :rtype: TokenAuthorizer
    """

    return TokenAuthorizer(token_ro=config.token_ro, token_rw=config.token_rw)
