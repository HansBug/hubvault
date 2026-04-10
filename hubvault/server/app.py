"""FastAPI app factory for the embedded server."""

from pathlib import Path
from typing import Optional

from ..api import HubVaultApi
from .._optional import import_optional_dependency
from ..repo import LARGE_FILE_THRESHOLD
from .config import ServerConfig
from .deps import get_token_authorizer
from .exception_handlers import register_exception_handlers
from .routes.meta import create_meta_router


def _coerce_config(config: Optional[ServerConfig], **kwargs) -> ServerConfig:
    if config is not None and kwargs:
        raise TypeError("Pass either a ServerConfig instance or explicit keyword arguments, not both.")
    if config is not None:
        return config
    if kwargs:
        return ServerConfig(**kwargs)
    return ServerConfig.from_env()


def _prepare_repo_api(config: ServerConfig) -> HubVaultApi:
    api = HubVaultApi(config.repo_path)
    if config.init:
        api.create_repo(
            exist_ok=True,
            default_branch=config.initial_branch,
            large_file_threshold=config.large_file_threshold or LARGE_FILE_THRESHOLD,
        )
    else:
        api.repo_info()
    return api


def _static_webui_dir() -> Path:
    return Path(__file__).resolve().parent / "static" / "webui"


def _register_frontend_routes(app, static_dir: Path) -> None:
    from .._optional import import_optional_dependency

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
        return FileResponse(str(index_path))

    @app.get("/{requested_path:path}", include_in_schema=False)
    def _frontend_fallback(requested_path: str):
        if requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = static_dir / requested_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(index_path))


def create_app(config: Optional[ServerConfig] = None, **kwargs):
    """Create one FastAPI app bound to a single repository root."""

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="hubvault server app factory",
        missing_names={"starlette", "pydantic"},
    )
    FastAPI = fastapi.FastAPI

    config = _coerce_config(config, **kwargs)
    api = _prepare_repo_api(config)
    authorizer = get_token_authorizer(config)
    static_dir = _static_webui_dir()

    app = FastAPI(
        title="hubvault",
        version="1",
        docs_url="/docs" if config.mode == "api" else None,
        redoc_url="/redoc" if config.mode == "api" else None,
    )
    app.state.server_config = config
    app.state.repo_api = api
    app.state.token_authorizer = authorizer

    register_exception_handlers(app)
    app.include_router(create_meta_router(config=config, api=api, authorizer=authorizer))

    if config.ui_enabled:
        _register_frontend_routes(app, static_dir)

    return app
