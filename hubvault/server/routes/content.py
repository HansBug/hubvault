"""
Content route factory for :mod:`hubvault.server`.

This module exposes read-only repository browsing and download endpoints,
including tree listings, single-file reads, range reads, and snapshot-plan
manifests used by the remote client.

The module contains:

* :func:`create_content_router` - Build the ``/api/v1/content`` router
"""

from fnmatch import fnmatch
from typing import Iterable, List, Optional
from urllib.parse import quote, urlencode

from ..auth import build_read_auth_dependency
from ..schemas import normalize_paths_request, normalize_snapshot_plan_request
from ..serde import build_snapshot_plan_payload, encode_repo_entries
from ...errors import HubVaultValidationError
from ...models import RepoFile


def _normalize_patterns(values: Iterable[str]) -> List[str]:
    """
    Normalize glob-pattern inputs for snapshot plans.

    :param values: Raw pattern values
    :type values: Iterable[str]
    :return: Normalized pattern list
    :rtype: List[str]
    """

    normalized = []
    for item in values:
        text = str(item)
        if text.endswith("/"):
            normalized.append(text + "*")
        else:
            normalized.append(text)
    return normalized


def _filter_repo_paths(paths: Iterable[str], allow_patterns: Iterable[str], ignore_patterns: Iterable[str]) -> List[str]:
    """
    Filter repo-relative paths using HF-style glob semantics.

    :param paths: Candidate repo-relative file paths
    :type paths: Iterable[str]
    :param allow_patterns: Allowlist patterns
    :type allow_patterns: Iterable[str]
    :param ignore_patterns: Denylist patterns
    :type ignore_patterns: Iterable[str]
    :return: Filtered file paths
    :rtype: List[str]
    """

    normalized_allow = _normalize_patterns(allow_patterns)
    normalized_ignore = _normalize_patterns(ignore_patterns)

    filtered = []
    for item in paths:
        if normalized_allow and not any(fnmatch(item, rule) for rule in normalized_allow):
            continue
        if normalized_ignore and any(fnmatch(item, rule) for rule in normalized_ignore):
            continue
        filtered.append(item)
    return filtered


def _download_url_for(path_in_repo: str, revision: str) -> str:
    """
    Build one relative download URL for a manifest entry.

    :param path_in_repo: Repo-relative file path
    :type path_in_repo: str
    :param revision: Immutable revision string used for the download
    :type revision: str
    :return: Relative download URL
    :rtype: str
    """

    return "/api/v1/content/download/{path}?{query}".format(
        path=quote(path_in_repo, safe="/"),
        query=urlencode({"revision": revision}),
    )


def create_content_router(*, api, authorizer):
    """
    Build the content router for the server app.

    :param api: Repository API bound to the current app
    :type api: hubvault.api.HubVaultApi
    :param authorizer: Shared token authorizer
    :type authorizer: hubvault.server.auth.TokenAuthorizer
    :return: Router exposing read-only content endpoints
    :rtype: fastapi.APIRouter
    :raises hubvault.optional.MissingOptionalDependencyError: Raised when the
        API extra is not installed.
    """

    from ...optional import import_optional_dependency

    fastapi = import_optional_dependency(
        "fastapi",
        extra="api",
        feature="server content routes",
        missing_names={"starlette", "pydantic"},
    )
    fastapi_responses = import_optional_dependency(
        "fastapi.responses",
        extra="api",
        feature="server content routes",
        missing_names={"fastapi", "starlette", "pydantic"},
    )
    APIRouter = fastapi.APIRouter
    Body = fastapi.Body
    Depends = fastapi.Depends
    Response = fastapi_responses.Response

    router = APIRouter(prefix="/api/v1/content", tags=["content"])
    require_read = build_read_auth_dependency(authorizer)

    @router.post("/paths-info")
    def get_paths_info(payload=Body(...), revision: Optional[str] = None, auth=Depends(require_read)):
        """
        Return public metadata for selected repo paths.

        :param payload: Request body describing target paths
        :type payload: object
        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible path metadata
        :rtype: List[dict]
        """

        del auth
        paths = normalize_paths_request(payload)
        return encode_repo_entries(api.get_paths_info(paths, revision=revision))

    @router.get("/tree")
    def list_repo_tree(
        path_in_repo: Optional[str] = None,
        recursive: bool = False,
        revision: Optional[str] = None,
        auth=Depends(require_read),
    ):
        """
        Return tree entries under one repo directory.

        :param path_in_repo: Optional repo-relative directory path
        :type path_in_repo: Optional[str]
        :param recursive: Whether descendant entries should be included
        :type recursive: bool
        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible tree entries
        :rtype: List[dict]
        """

        del auth
        return encode_repo_entries(api.list_repo_tree(path_in_repo, recursive=recursive, revision=revision))

    @router.get("/files")
    def list_repo_files(revision: Optional[str] = None, auth=Depends(require_read)):
        """
        Return all repo-relative file paths for one revision.

        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: Repo-relative file paths
        :rtype: List[str]
        """

        del auth
        return list(api.list_repo_files(revision=revision))

    @router.get("/blob/{path_in_repo:path}/range")
    def read_range(
        path_in_repo: str,
        start: int,
        length: int,
        revision: Optional[str] = None,
        auth=Depends(require_read),
    ):
        """
        Return a byte range from one repository file.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param start: Starting byte offset
        :type start: int
        :param length: Requested byte length
        :type length: int
        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: Binary range response
        :rtype: fastapi.responses.Response
        """

        del auth
        try:
            payload = api.read_range(path_in_repo, start=start, length=length, revision=revision)
        except ValueError as err:
            raise HubVaultValidationError(str(err))
        return Response(content=payload, media_type="application/octet-stream")

    @router.get("/blob/{path_in_repo:path}")
    def read_bytes(path_in_repo: str, revision: Optional[str] = None, auth=Depends(require_read)):
        """
        Return the full bytes of one repository file.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: Binary file response
        :rtype: fastapi.responses.Response
        """

        del auth
        return Response(content=api.read_bytes(path_in_repo, revision=revision), media_type="application/octet-stream")

    @router.get("/download/{path_in_repo:path}")
    def download_file(path_in_repo: str, revision: Optional[str] = None, auth=Depends(require_read)):
        """
        Return the detached-download bytes for one repository file.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: Binary download response
        :rtype: fastapi.responses.Response
        """

        del auth
        file_info = api.get_paths_info(path_in_repo, revision=revision)
        headers = {
            "X-HubVault-Repo-Path": path_in_repo,
            "Content-Disposition": 'attachment; filename="%s"' % (path_in_repo.split("/")[-1],),
        }
        if file_info and isinstance(file_info[0], RepoFile) and file_info[0].etag is not None:
            headers["ETag"] = str(file_info[0].etag)
        return Response(
            content=api.read_bytes(path_in_repo, revision=revision),
            media_type="application/octet-stream",
            headers=headers,
        )

    @router.post("/snapshot-plan")
    def build_snapshot_plan(payload=Body(default=None), revision: Optional[str] = None, auth=Depends(require_read)):
        """
        Build a remote-consumable snapshot manifest.

        :param payload: Request body carrying optional path filters
        :type payload: object
        :param revision: Optional revision override
        :type revision: Optional[str]
        :param auth: Resolved caller authorization context
        :type auth: hubvault.server.auth.AuthContext
        :return: JSON-compatible snapshot manifest
        :rtype: dict
        """

        del auth
        options = normalize_snapshot_plan_request(payload)
        repo_info = api.repo_info(revision=revision)
        selected_revision = revision or repo_info.default_branch
        resolved_revision = repo_info.head or selected_revision
        file_paths = _filter_repo_paths(
            api.list_repo_files(revision=revision),
            allow_patterns=options["allow_patterns"],
            ignore_patterns=options["ignore_patterns"],
        )
        file_infos = api.get_paths_info(file_paths, revision=revision) if file_paths else []
        files = []
        for item in file_infos:
            if not isinstance(item, RepoFile):
                raise HubVaultValidationError("Snapshot plans can only contain file entries.")
            files.append(
                {
                    "path": item.path,
                    "size": item.size,
                    "blob_id": item.blob_id,
                    "oid": item.oid,
                    "sha256": item.sha256,
                    "etag": item.etag,
                    "download_url": _download_url_for(item.path, resolved_revision),
                }
            )

        return build_snapshot_plan_payload(
            revision=selected_revision,
            resolved_revision=resolved_revision,
            head=repo_info.head,
            files=files,
            allow_patterns=options["allow_patterns"],
            ignore_patterns=options["ignore_patterns"],
        )

    return router
