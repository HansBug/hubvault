"""
Exception handler registration for :mod:`hubvault.server`.

This module translates public ``hubvault`` exceptions into stable HTTP error
payloads for the embedded FastAPI app.

The module contains:

* :func:`register_exception_handlers` - Attach ``hubvault`` error handlers
"""

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
    """
    Map one public ``hubvault`` exception to an HTTP status code.

    :param err: Repository-layer exception
    :type err: hubvault.errors.HubVaultError
    :return: HTTP status code aligned with the public error category
    :rtype: int
    """

    if isinstance(err, (RepositoryNotFoundError, RevisionNotFoundError, EntryNotFoundError)):
        return 404
    if isinstance(err, (ConflictError, RepositoryAlreadyExistsError)):
        return 409
    if isinstance(err, HubVaultValidationError):
        return 400
    return 500


def register_exception_handlers(app) -> None:
    """
    Attach ``hubvault``-specific exception handlers to one FastAPI app.

    :param app: FastAPI application receiving the handlers
    :type app: fastapi.FastAPI
    :return: ``None``.
    :rtype: None
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    """

    from ..optional import import_optional_dependency

    fastapi_responses = import_optional_dependency(
        "fastapi.responses",
        extra="api",
        feature="server exception handlers",
        missing_names={"fastapi", "starlette", "pydantic"},
    )
    JSONResponse = fastapi_responses.JSONResponse

    @app.exception_handler(HubVaultError)
    async def _hubvault_error_handler(_, err: HubVaultError):
        """
        Translate one public ``hubvault`` exception into JSON.

        :param _: Request object ignored by the shared handler
        :type _: object
        :param err: Repository-layer exception
        :type err: hubvault.errors.HubVaultError
        :return: JSON error response
        :rtype: fastapi.responses.JSONResponse
        """

        return JSONResponse(
            status_code=_status_for_error(err),
            content=build_error_payload(type(err).__name__, str(err)),
        )
