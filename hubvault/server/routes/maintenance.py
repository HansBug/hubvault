"""
Maintenance route factory for :mod:`hubvault.server`.

This module exposes repository verification, storage-analysis, and
operator-triggered maintenance endpoints over HTTP so the bundled frontend can
render diagnostics and run controlled maintenance actions without importing
backend internals.

The module contains:

* :func:`create_maintenance_router` - Build the ``/api/v1/maintenance`` router
"""

from ..auth import build_read_auth_dependency, build_write_auth_dependency
from ..deps import build_repo_api_getter
from ..schemas import normalize_gc_request, normalize_squash_history_request
from ..serde import encode_gc_report, encode_squash_report, encode_storage_overview, encode_verify_report


def create_maintenance_router(*, api=None, api_factory=None, authorizer):
    """
    Build the maintenance router for the server app.

    :param api: Optional repository API reused by the router
    :type api: Optional[hubvault.api.HubVaultApi]
    :param api_factory: Optional zero-argument factory returning one fresh
        repository API per request
    :type api_factory: Optional[Callable[[], hubvault.api.HubVaultApi]]
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing read-only maintenance endpoints
    :rtype: fastapi.APIRouter
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    :raises TypeError: Raised when both ``api`` and ``api_factory`` are
        provided or when neither input is provided.
    """

    from ...optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server maintenance routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Depends = fastapi.Depends

    router = APIRouter(prefix="/api/v1/maintenance", tags=["maintenance"])
    get_api = build_repo_api_getter(api=api, api_factory=api_factory)
    require_read = build_read_auth_dependency(authorizer)
    require_write = build_write_auth_dependency(authorizer)

    @router.post("/quick-verify")
    def quick_verify(auth=Depends(require_read)):
        """
        Return the minimal repository verification result.

        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible verification payload
        :rtype: dict
        """

        del auth
        return encode_verify_report(get_api().quick_verify())

    @router.post("/full-verify")
    def full_verify(auth=Depends(require_read)):
        """
        Return the complete repository verification result.

        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible verification payload
        :rtype: dict
        """

        del auth
        return encode_verify_report(get_api().full_verify())

    @router.get("/storage-overview")
    def get_storage_overview(auth=Depends(require_read)):
        """
        Return repository storage analysis and reclamation guidance.

        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible storage overview payload
        :rtype: dict
        """

        del auth
        return encode_storage_overview(get_api().get_storage_overview())

    @router.post("/gc")
    def run_gc(payload=fastapi.Body(default=None), auth=Depends(require_write)):
        """
        Run one repository GC pass.

        :param payload: Raw GC request body
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible GC report
        :rtype: dict
        """

        del auth
        options = normalize_gc_request(payload)
        return encode_gc_report(get_api().gc(**options))

    @router.post("/squash-history")
    def squash_history(payload=fastapi.Body(...), auth=Depends(require_write)):
        """
        Rewrite one branch history chain.

        :param payload: Raw squash-history request body
        :type payload: object
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible squash report
        :rtype: dict
        """

        del auth
        options = normalize_squash_history_request(payload)
        return encode_squash_report(get_api().squash_history(**options))

    return router
