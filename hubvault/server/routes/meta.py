"""
Metadata route factory for :mod:`hubvault.server`.

This module builds the small Phase 1-3 metadata router that reports server
identity and the caller's resolved access level.

The module contains:

* :func:`create_meta_router` - Build the ``/api/v1/meta`` router
"""

from ...config.meta import __TITLE__, __VERSION__
from ..auth import build_read_auth_dependency
from ..deps import build_repo_api_getter
from ..serde import build_meta_service_payload, build_whoami_payload


def create_meta_router(*, config, api=None, api_factory=None, authorizer):
    """
    Build the metadata router for the server app.

    :param config: Server configuration bound to the current app
    :type config: hubvault.server.config.ServerConfig
    :param api: Optional repository API reused by the router
    :type api: Optional[hubvault.api.HubVaultApi]
    :param api_factory: Optional zero-argument factory returning one fresh
        repository API per request
    :type api_factory: Optional[Callable[[], hubvault.api.HubVaultApi]]
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing the metadata endpoints
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
        feature="server meta routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Depends = fastapi.Depends

    router = APIRouter(prefix="/api/v1/meta", tags=["meta"])
    get_api = build_repo_api_getter(api=api, api_factory=api_factory)
    require_read = build_read_auth_dependency(authorizer)

    @router.get("/service")
    def get_service(auth=Depends(require_read)):
        """
        Return service metadata for the current repository binding.

        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible service payload
        :rtype: dict
        """

        repo_info = get_api().repo_info()
        return build_meta_service_payload(
            service=__TITLE__,
            version=__VERSION__,
            mode=config.mode,
            repo_path=str(config.repo_path),
            ui_enabled=config.ui_enabled,
            default_branch=repo_info.default_branch,
            head=repo_info.head,
            auth={
                "access": auth.access,
                "can_write": auth.can_write,
            },
        )

    @router.get("/whoami")
    def get_whoami(auth=Depends(require_read)):
        """
        Return the caller's resolved access level.

        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible caller payload
        :rtype: dict
        """

        return build_whoami_payload(access=auth.access, can_write=auth.can_write)

    return router
