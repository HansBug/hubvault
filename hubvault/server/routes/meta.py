"""Meta routes for the embedded server."""

from ...config.meta import __TITLE__, __VERSION__
from ..auth import build_read_auth_dependency
from ..serde import build_meta_service_payload, build_whoami_payload


def create_meta_router(*, config, api, authorizer):
    """Build the metadata router for the server app."""

    from ..._optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server meta routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Depends = fastapi.Depends

    router = APIRouter(prefix="/api/v1/meta", tags=["meta"])
    require_read = build_read_auth_dependency(authorizer)

    @router.get("/service")
    def get_service(auth=Depends(require_read)):
        repo_info = api.repo_info()
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
        return build_whoami_payload(access=auth.access, can_write=auth.can_write)

    return router
