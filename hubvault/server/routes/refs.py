"""
Reference route factory for :mod:`hubvault.server`.

This module exposes read-only git-reference listings over HTTP.

The module contains:

* :func:`create_refs_router` - Build the ``/api/v1/refs`` router
"""

from ..auth import build_read_auth_dependency
from ..serde import encode_git_refs


def create_refs_router(*, api, authorizer):
    """
    Build the reference router for the server app.

    :param api: Repository API bound to the current app
    :type api: hubvault.api.HubVaultApi
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing git-reference endpoints
    :rtype: fastapi.APIRouter
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
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
        return encode_git_refs(api.list_repo_refs(include_pull_requests=include_pull_requests))

    return router
