"""
Reference route factory for :mod:`hubvault.server`.

This module exposes read-only git-reference listings over HTTP.

The module contains:

* :func:`create_refs_router` - Build the ``/api/v1/refs`` router
"""

from ..auth import build_read_auth_dependency
from ..deps import build_repo_api_getter
from ..serde import encode_git_refs


def create_refs_router(*, api=None, api_factory=None, authorizer):
    """
    Build the reference router for the server app.

    :param api: Optional repository API reused by the router
    :type api: Optional[hubvault.api.HubVaultApi]
    :param api_factory: Optional zero-argument factory returning one fresh
        repository API per request
    :type api_factory: Optional[Callable[[], hubvault.api.HubVaultApi]]
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing git-reference endpoints
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
        feature="server reference routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Depends = fastapi.Depends

    router = APIRouter(prefix="/api/v1/refs", tags=["refs"])
    get_api = build_repo_api_getter(api=api, api_factory=api_factory)
    require_read = build_read_auth_dependency(authorizer)

    @router.get("")
    def list_repo_refs(include_pull_requests: bool = False, auth=Depends(require_read)):
        """
        Return visible branch and tag refs.

        :param include_pull_requests: Whether pull-request refs should be included
        :type include_pull_requests: bool
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible refs payload
        :rtype: dict
        """

        del auth
        return encode_git_refs(get_api().list_repo_refs(include_pull_requests=include_pull_requests))

    return router
