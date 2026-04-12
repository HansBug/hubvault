"""
FastAPI app factory for :mod:`hubvault.server`.

This module builds the embedded HTTP application shared by import-based
startup, CLI startup, and ASGI factory deployment. Optional server dependencies
are imported lazily so the base installation remains importable without the API
extra.

The module contains:

* :func:`create_app` - Build one server app for a repository root
"""

from pathlib import Path
from typing import Optional

from ..api import HubVaultApi
from ..optional import import_optional_dependency
from ..repo import LARGE_FILE_THRESHOLD
from ..repo.backend import RepositoryBackend
from .config import ServerConfig
from .deps import get_repo_api_factory, get_token_authorizer
from .exception_handlers import register_exception_handlers
from .routes.content import create_content_router
from .routes.history import create_history_router
from .routes.maintenance import create_maintenance_router
from .routes.meta import create_meta_router
from .routes.refs import create_refs_router
from .routes.repo import create_repo_router
from .routes.writes import create_writes_router


def _coerce_config(config: Optional[ServerConfig], **kwargs) -> ServerConfig:
    """
    Normalize explicit config input and keyword overrides.

    :param config: Optional pre-built server configuration
    :type config: Optional[ServerConfig]
    :param kwargs: Keyword arguments used to construct :class:`ServerConfig`
    :type kwargs: dict
    :return: Normalized server configuration
    :rtype: ServerConfig
    :raises TypeError: Raised when both ``config`` and keyword overrides are
        supplied.
    """

    if config is not None and kwargs:
        raise TypeError("Pass either a ServerConfig instance or explicit keyword arguments, not both.")
    if config is not None:
        return config
    if kwargs:
        return ServerConfig(**kwargs)
    return ServerConfig.from_env()


def _prepare_repo_api(config: ServerConfig) -> HubVaultApi:
    """
    Open or initialize the repository API bound to one server config.

    :param config: Normalized server configuration
    :type config: ServerConfig
    :return: Repository API bound to ``config.repo_path``
    :rtype: hubvault.api.HubVaultApi
    :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
        does not exist and ``config.init`` is disabled.
    """

    api = HubVaultApi(config.repo_path, revision=config.initial_branch if config.init else "main")
    if config.init:
        repo_info = api.create_repo(
            exist_ok=True,
            default_branch=config.initial_branch,
            large_file_threshold=config.large_file_threshold or LARGE_FILE_THRESHOLD,
        )
        return HubVaultApi(config.repo_path, revision=repo_info.default_branch)

    # Existing repositories may use a non-``main`` default branch, so resolve
    # repository-wide metadata without assuming the API wrapper's default
    # revision first.
    repo_info = RepositoryBackend(config.repo_path).repo_info(revision=None)
    return HubVaultApi(config.repo_path, revision=repo_info.default_branch)


def _static_webui_dir() -> Path:
    """
    Return the packaged static web UI directory.

    :return: Filesystem path to the bundled web UI assets
    :rtype: pathlib.Path
    """

    return Path(__file__).resolve().parent / "static" / "webui"


def _register_frontend_routes(app, static_dir: Path) -> None:
    """
    Attach static-frontend routes to one FastAPI app.

    :param app: FastAPI application receiving frontend routes
    :type app: fastapi.FastAPI
    :param static_dir: Directory containing built frontend assets
    :type static_dir: pathlib.Path
    :return: ``None``.
    :rtype: None
    """

    from ..optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="frontend routes",
        missing_names={"starlette", "pydantic"},
    )
    responses = import_optional_dependency(
        "fastapi.responses",
        extra="api",
        feature="frontend routes",
        missing_names={"fastapi", "starlette", "pydantic"},
    )
    HTTPException = fastapi.HTTPException
    FileResponse = responses.FileResponse

    index_path = static_dir / "index.html"

    @app.get("/", include_in_schema=False)
    def _frontend_index():
        """
        Serve the frontend entry document.

        :return: Static file response for ``index.html``
        :rtype: fastapi.responses.FileResponse
        """

        return FileResponse(str(index_path))

    @app.get("/{requested_path:path}", include_in_schema=False)
    def _frontend_fallback(requested_path: str):
        """
        Serve frontend assets or fall back to the SPA entry document.

        :param requested_path: Requested frontend path
        :type requested_path: str
        :return: Static asset response or the frontend entry document
        :rtype: fastapi.responses.FileResponse
        :raises fastapi.HTTPException: Raised when the request targets the API
            namespace but no route matched.
        """

        if requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = static_dir / requested_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(index_path))


def create_app(config: Optional[ServerConfig] = None, **kwargs):
    """
    Create one FastAPI app bound to a single repository root.

    :param config: Optional pre-built server configuration
    :type config: Optional[ServerConfig]
    :param kwargs: Keyword arguments used to build :class:`ServerConfig` when
        ``config`` is omitted
    :type kwargs: dict
    :return: Configured FastAPI application
    :rtype: fastapi.FastAPI
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    :raises TypeError: Raised when both ``config`` and keyword overrides are
        supplied.

    Example::

        >>> from pathlib import Path
        >>> config = ServerConfig(repo_path=Path('repo'), token_rw=('rw',))
        >>> callable(create_app) and isinstance(config.port, int)
        True
    """

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="hubvault server app factory",
        missing_names={"starlette", "pydantic"},
    )
    FastAPI = fastapi.FastAPI

    config = _coerce_config(config, **kwargs)
    _prepare_repo_api(config)
    api_factory = get_repo_api_factory(config)
    authorizer = get_token_authorizer(config)
    static_dir = _static_webui_dir()

    app = FastAPI(
        title="hubvault",
        version="1",
        docs_url="/docs" if config.mode == "api" else None,
        redoc_url="/redoc" if config.mode == "api" else None,
    )
    app.state.server_config = config
    app.state.repo_api_factory = api_factory
    app.state.token_authorizer = authorizer

    register_exception_handlers(app)
    app.include_router(create_meta_router(config=config, api_factory=api_factory, authorizer=authorizer))
    app.include_router(create_repo_router(api_factory=api_factory, authorizer=authorizer))
    app.include_router(create_content_router(api_factory=api_factory, authorizer=authorizer))
    app.include_router(create_refs_router(api_factory=api_factory, authorizer=authorizer))
    app.include_router(create_history_router(api_factory=api_factory, authorizer=authorizer))
    app.include_router(create_maintenance_router(api_factory=api_factory, authorizer=authorizer))
    app.include_router(create_writes_router(api_factory=api_factory, authorizer=authorizer))

    if config.ui_enabled:
        _register_frontend_routes(app, static_dir)

    return app
