"""
Repository route factory for :mod:`hubvault.server`.

This module builds the read-only repository metadata endpoints that expose the
public :class:`hubvault.api.HubVaultApi.repo_info` behavior over HTTP.

The module contains:

* :func:`create_repo_router` - Build the ``/api/v1/repo`` router
"""

from typing import Optional

from ..auth import build_read_auth_dependency
from ..deps import build_repo_api_getter
from ..serde import encode_repo_info


def create_repo_router(*, api=None, api_factory=None, authorizer):
    """
    Build the repository metadata router for the server app.

    :param api: Optional repository API reused by the router
    :type api: Optional[hubvault.api.HubVaultApi]
    :param api_factory: Optional zero-argument factory returning one fresh
        repository API per request
    :type api_factory: Optional[Callable[[], hubvault.api.HubVaultApi]]
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing the repository metadata endpoints
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
        feature="server repository routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Depends = fastapi.Depends

    router = APIRouter(prefix="/api/v1/repo", tags=["repo"])
    get_api = build_repo_api_getter(api=api, api_factory=api_factory)
    require_read = build_read_auth_dependency(authorizer)

    @router.get("")
    def get_repo(revision: Optional[str] = None, auth=Depends(require_read)):
        """
        Return repository metadata for one revision selection.

        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible repository metadata
        :rtype: dict
        """

        del auth
        return encode_repo_info(get_api().repo_info(revision=revision))

    return router
