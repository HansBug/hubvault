"""
History route factory for :mod:`hubvault.server`.

This module exposes read-only commit-history and reflog listings over HTTP.

The module contains:

* :func:`create_history_router` - Build the ``/api/v1/history`` router
"""

from typing import Optional

from ..auth import build_read_auth_dependency
from ..serde import encode_git_commit_list, encode_reflog_entries


def create_history_router(*, api, authorizer):
    """
    Build the history router for the server app.

    :param api: Repository API bound to the current app
    :type api: hubvault.api.HubVaultApi
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing history endpoints
    :rtype: fastapi.APIRouter
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    """

    from ...optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server history routes",
        missing_names={"starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Depends = fastapi.Depends

    router = APIRouter(prefix="/api/v1/history", tags=["history"])
    require_read = build_read_auth_dependency(authorizer)

    @router.get("/commits")
    def list_repo_commits(revision: Optional[str] = None, formatted: bool = False, auth=Depends(require_read)):
        """
        Return commit-list entries for one revision selection.

        :param revision: Optional revision override
        :type revision: Optional[str]
        :param formatted: Whether HTML-formatted title/message fields should be included
        :type formatted: bool
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible commit-list payload
        :rtype: List[dict]
        """

        del auth
        return encode_git_commit_list(api.list_repo_commits(revision=revision, formatted=formatted))

    @router.get("/reflog/{ref_name:path}")
    def list_repo_reflog(ref_name: str, limit: Optional[int] = None, auth=Depends(require_read)):
        """
        Return reflog entries for one branch or tag ref.

        :param ref_name: Full or short ref name
        :type ref_name: str
        :param limit: Optional maximum number of entries
        :type limit: Optional[int]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible reflog payload
        :rtype: List[dict]
        """

        del auth
        return encode_reflog_entries(api.list_repo_reflog(ref_name, limit=limit))

    return router
