"""Exception handler registration for the FastAPI server app."""

from ..errors import (
    ConflictError,
    EntryNotFoundError,
    HubVaultError,
    HubVaultValidationError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)
from .schemas import build_error_payload


def _status_for_error(err: HubVaultError) -> int:
    if isinstance(err, (RepositoryNotFoundError, RevisionNotFoundError, EntryNotFoundError)):
        return 404
    if isinstance(err, (ConflictError, RepositoryAlreadyExistsError)):
        return 409
    if isinstance(err, HubVaultValidationError):
        return 400
    return 500


def register_exception_handlers(app) -> None:
    """Attach hubvault-specific exception handlers to one FastAPI app."""

    from .._optional import import_optional_dependency

    fastapi_responses = import_optional_dependency(
        "fastapi.responses",
        extra="api",
        feature="server exception handlers",
        missing_names={"fastapi", "starlette", "pydantic"},
    )
    JSONResponse = fastapi_responses.JSONResponse

    @app.exception_handler(HubVaultError)
    async def _hubvault_error_handler(_, err: HubVaultError):
        return JSONResponse(
            status_code=_status_for_error(err),
            content=build_error_payload(type(err).__name__, str(err)),
        )
