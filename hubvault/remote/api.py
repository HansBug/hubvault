"""
Public remote API surface for :mod:`hubvault.remote`.

This module defines the early public client shell that will eventually mirror
selected local :class:`hubvault.api.HubVaultApi` read APIs over HTTP.

The module contains:

* :class:`HubVaultRemoteApi` - Remote API entry point
* :data:`HubVaultRemoteAPI` - Compatibility alias for the preferred class name
"""

from os import PathLike
from pathlib import Path
from typing import BinaryIO, Optional, Sequence, Union
from urllib.parse import quote

from ..errors import EntryNotFoundError
from .cache import (
    build_download_target,
    build_snapshot_target,
    get_remote_cache_layout,
    snapshot_is_complete,
)
from .client import build_http_client, request_bytes, request_json
from .serde import (
    decode_git_commit_list,
    decode_git_refs,
    decode_reflog_entries,
    decode_repo_entries,
    decode_repo_info,
    decode_snapshot_plan,
)


class HubVaultRemoteApi:
    """
    Read-only remote API client aligned with :class:`hubvault.api.HubVaultApi`.

    The remote client intentionally mirrors the local API naming for common
    read paths so callers can switch between embedded and HTTP-backed
    repositories with minimal adaptation. Optional HTTP dependencies remain
    lazy; importing this class does not require the remote extra until a real
    transport call is attempted.

    :param base_url: Base URL of the remote server
    :type base_url: str
    :param token: Optional bearer token used for authenticated requests
    :type token: Optional[str]
    :param revision: Default revision used by read APIs
    :type revision: str
    :param timeout: Default request timeout in seconds
    :type timeout: float
    :param cache_dir: Optional client-local cache root override
    :type cache_dir: Optional[Union[str, os.PathLike[str]]]

    Example::

        >>> api = HubVaultRemoteApi("https://example.com/api", token="secret", revision="main")
        >>> api.base_url
        'https://example.com/api'
    """

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        revision: str = "main",
        timeout: float = 30.0,
        cache_dir: Optional[Union[str, PathLike]] = None,
    ) -> None:
        """
        Build one remote API client shell.

        :param base_url: Base URL of the remote server
        :type base_url: str
        :param token: Optional bearer token used for authenticated requests
        :type token: Optional[str]
        :param revision: Default revision used by read APIs
        :type revision: str
        :param timeout: Default request timeout in seconds
        :type timeout: float
        :param cache_dir: Optional client-local cache root override
        :type cache_dir: Optional[Union[str, os.PathLike]]
        :return: ``None``.
        :rtype: None
        """

        self.base_url = base_url.rstrip("/")
        self.endpoint = self.base_url
        self.token = token
        self._default_revision = revision
        self.timeout = timeout
        self._cache_dir = None if cache_dir is None else Path(cache_dir).expanduser()

    def build_client(self):
        """
        Build the underlying HTTP client lazily.

        :return: Configured HTTP transport client
        :rtype: httpx.Client
        :raises hubvault.optional.MissingOptionalDependencyError: Raised when
            the remote extra is not installed.
        """

        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer %s" % (self.token,)
        return build_http_client(base_url=self.base_url, timeout=self.timeout, headers=headers or None)

    def _selected_revision(self, revision: Optional[str]) -> str:
        """
        Resolve one optional revision override.

        :param revision: Optional revision override
        :type revision: Optional[str]
        :return: Selected revision string
        :rtype: str
        """

        return revision or self._default_revision

    def repo_info(self, *, revision: Optional[str] = None):
        """
        Return metadata about the remote repository.

        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: Repository metadata
        :rtype: hubvault.models.RepoInfo
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "GET",
                "/api/v1/repo",
                params={"revision": self._selected_revision(revision)},
            )
        return decode_repo_info(payload)

    def get_paths_info(self, paths: Union[Sequence[str], str], *, revision: Optional[str] = None):
        """
        Return public metadata for selected remote paths.

        :param paths: Repo-relative path or paths to inspect
        :type paths: Union[Sequence[str], str]
        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: Metadata for the existing requested paths
        :rtype: List[Union[hubvault.models.RepoFile, hubvault.models.RepoFolder]]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.errors.UnsupportedPathError: Raised when one of the
            requested paths is invalid.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        body = [paths] if isinstance(paths, str) else list(paths)
        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/content/paths-info",
                params={"revision": self._selected_revision(revision)},
                json=body,
            )
        return decode_repo_entries(payload)

    def list_repo_tree(
        self,
        path_in_repo: Optional[str] = None,
        *,
        recursive: bool = False,
        revision: Optional[str] = None,
    ):
        """
        List direct children under a remote repository directory.

        :param path_in_repo: Repo-relative directory path, defaults to the root
        :type path_in_repo: Optional[str]
        :param recursive: Whether to include descendant entries recursively
        :type recursive: bool
        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: Direct child path metadata
        :rtype: List[Union[hubvault.models.RepoFile, hubvault.models.RepoFolder]]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.errors.UnsupportedPathError: Raised when
            ``path_in_repo`` is invalid.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        params = {
            "recursive": recursive,
            "revision": self._selected_revision(revision),
        }
        if path_in_repo is not None:
            params["path_in_repo"] = path_in_repo
        with self.build_client() as client:
            payload = request_json(client, "GET", "/api/v1/content/tree", params=params)
        return decode_repo_entries(payload)

    def list_repo_files(self, *, revision: Optional[str] = None) -> Sequence[str]:
        """
        List all remote file paths in a revision.

        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: Sorted repo-relative file paths
        :rtype: Sequence[str]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "GET",
                "/api/v1/content/files",
                params={"revision": self._selected_revision(revision)},
            )
        return [str(item) for item in payload]

    def list_repo_commits(self, *, revision: Optional[str] = None, formatted: bool = False):
        """
        List commits reachable from a remote revision in HF-style order.

        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :param formatted: Whether HTML-formatted title/message fields should be populated
        :type formatted: bool
        :return: Commit entries ordered from newest to oldest
        :rtype: Sequence[hubvault.models.GitCommitInfo]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "GET",
                "/api/v1/history/commits",
                params={
                    "revision": self._selected_revision(revision),
                    "formatted": formatted,
                },
            )
        return decode_git_commit_list(payload)

    def list_repo_refs(self, *, include_pull_requests: bool = False):
        """
        List visible remote branch and tag refs in HF-style form.

        :param include_pull_requests: Whether pull-request refs should be included
        :type include_pull_requests: bool
        :return: Visible repository refs
        :rtype: hubvault.models.GitRefs
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "GET",
                "/api/v1/refs",
                params={"include_pull_requests": include_pull_requests},
            )
        return decode_git_refs(payload)

    def list_repo_reflog(self, ref_name: str, *, limit: Optional[int] = None):
        """
        List reflog entries for a remote branch or tag.

        :param ref_name: Full ref name or an unambiguous short ref name
        :type ref_name: str
        :param limit: Optional maximum number of newest entries to return
        :type limit: Optional[int]
        :return: Reflog entries ordered from newest to oldest
        :rtype: Sequence[hubvault.models.ReflogEntry]
        :raises hubvault.errors.HubVaultValidationError: Raised when ``limit``
            is invalid for the server API.
        :raises hubvault.errors.RevisionNotFoundError: Raised when ``ref_name``
            does not resolve to a branch or tag.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        params = {}
        if limit is not None:
            params["limit"] = limit
        with self.build_client() as client:
            payload = request_json(
                client,
                "GET",
                "/api/v1/history/reflog/%s" % (quote(ref_name, safe=""),),
                params=params or None,
            )
        return decode_reflog_entries(payload)

    def read_bytes(self, path_in_repo: str, *, revision: Optional[str] = None) -> bytes:
        """
        Read the full remote content of a file.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: File content bytes
        :rtype: bytes
        :raises hubvault.errors.EntryNotFoundError: Raised when the selected
            file does not exist.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        with self.build_client() as client:
            return request_bytes(
                client,
                "GET",
                "/api/v1/content/blob/%s" % (quote(path_in_repo, safe="/"),),
                params={"revision": self._selected_revision(revision)},
            )

    def read_range(
        self,
        path_in_repo: str,
        *,
        start: int,
        length: int,
        revision: Optional[str] = None,
    ) -> bytes:
        """
        Read a byte range from a remote file.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param start: Starting byte offset in the logical file
        :type start: int
        :param length: Number of bytes to read
        :type length: int
        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: Requested byte range, clamped to the file end
        :rtype: bytes
        :raises hubvault.errors.EntryNotFoundError: Raised when the selected
            file does not exist.
        :raises hubvault.errors.HubVaultValidationError: Raised when ``start``
            or ``length`` is invalid.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        with self.build_client() as client:
            return request_bytes(
                client,
                "GET",
                "/api/v1/content/blob/%s/range" % (quote(path_in_repo, safe="/"),),
                params={
                    "start": start,
                    "length": length,
                    "revision": self._selected_revision(revision),
                },
            )

    def hf_hub_download(
        self,
        filename: str,
        *,
        revision: Optional[str] = None,
        local_dir: Optional[Union[str, PathLike]] = None,
    ) -> str:
        """
        Materialize a detached local path for one remote file.

        :param filename: Repo-relative file path
        :type filename: str
        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :param local_dir: Optional export directory outside the client cache
        :type local_dir: Optional[Union[str, os.PathLike]]
        :return: A filesystem path that can be read safely
        :rtype: str
        :raises hubvault.errors.EntryNotFoundError: Raised when ``filename``
            does not exist in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        selected_revision = self._selected_revision(revision)
        layout = get_remote_cache_layout(self._cache_dir)
        info_items = self.get_paths_info(filename, revision=selected_revision)
        if not info_items:
            raise EntryNotFoundError(filename)
        file_info = info_items[0]
        target_path = build_download_target(
            layout,
            base_url=self.base_url,
            path_in_repo=filename,
            etag=getattr(file_info, "etag", None),
            revision=selected_revision,
            local_dir=local_dir,
        )
        if local_dir is None and target_path.is_file():
            return str(target_path)

        with self.build_client() as client:
            payload = request_bytes(
                client,
                "GET",
                "/api/v1/content/download/%s" % (quote(filename, safe="/"),),
                params={"revision": selected_revision},
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)
        return str(target_path)

    def snapshot_download(
        self,
        *,
        revision: Optional[str] = None,
        local_dir: Optional[Union[str, PathLike]] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> str:
        """
        Materialize a detached local snapshot directory for a remote revision.

        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :param local_dir: Optional export directory outside the client cache
        :type local_dir: Optional[Union[str, os.PathLike]]
        :param allow_patterns: Optional allowlist for repo-relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]]
        :param ignore_patterns: Optional denylist for repo-relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]]
        :return: Filesystem path to the detached snapshot directory
        :rtype: str
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        def _normalize_patterns(values):
            if values is None:
                return []
            if isinstance(values, str):
                return [values]
            return [str(item) for item in values]

        selected_revision = self._selected_revision(revision)
        request_body = {
            "allow_patterns": _normalize_patterns(allow_patterns),
            "ignore_patterns": _normalize_patterns(ignore_patterns),
        }
        with self.build_client() as client:
            manifest = decode_snapshot_plan(
                request_json(
                    client,
                    "POST",
                    "/api/v1/content/snapshot-plan",
                    params={"revision": selected_revision},
                    json=request_body,
                )
            )
            snapshot_id = manifest["head"] or manifest["resolved_revision"]
            layout = get_remote_cache_layout(self._cache_dir)
            target_dir = build_snapshot_target(
                layout,
                base_url=self.base_url,
                snapshot_id=snapshot_id,
                local_dir=local_dir,
            )
            repo_paths = [item["path"] for item in manifest["files"]]
            if local_dir is None and snapshot_is_complete(target_dir, repo_paths):
                return str(target_dir)

            for item in manifest["files"]:
                destination = target_dir / item["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                if local_dir is None and destination.is_file():
                    continue
                destination.write_bytes(request_bytes(client, "GET", item["download_url"]))
        return str(target_dir)

    def open_file(self, path_in_repo: str, *, revision: Optional[str] = None) -> BinaryIO:
        """
        Open a remote file as a read-only binary stream.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the client default revision
        :type revision: Optional[str]
        :return: Read-only binary stream backed by a detached local file
        :rtype: BinaryIO
        :raises hubvault.errors.EntryNotFoundError: Raised when the selected
            file does not exist.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist on the server.
        :raises hubvault.remote.errors.HubVaultRemoteAuthError: Raised when the
            server rejects authentication.
        :raises hubvault.remote.errors.HubVaultRemoteError: Raised when
            transport or payload handling fails.
        """

        return open(self.hf_hub_download(path_in_repo, revision=revision), "rb")


HubVaultRemoteAPI = HubVaultRemoteApi
