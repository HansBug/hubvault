"""
Public remote API surface for :mod:`hubvault.remote`.

This module defines the public HTTP-backed client that mirrors the supported
local :class:`hubvault.api.HubVaultApi` read, write, and maintenance APIs.

The module contains:

* :class:`HubVaultRemoteApi` - Remote API entry point
* :data:`HubVaultRemoteAPI` - Compatibility alias for the preferred class name
"""

import io
import json
from fnmatch import fnmatch
import os
from os import PathLike
from pathlib import Path
from typing import BinaryIO, Callable, Optional, Sequence, Union
from urllib.parse import quote

from ..errors import EntryNotFoundError
from ..optional import MissingOptionalDependencyError, import_optional_dependency
from ..operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete
from ..storage import ChunkStore
from .cache import (
    build_download_target,
    build_snapshot_target,
    get_remote_cache_layout,
    snapshot_is_complete,
)
from .client import build_http_client, request_bytes, request_json
from .serde import (
    decode_commit_detail_info,
    decode_commit_info,
    decode_gc_report,
    decode_git_commit_list,
    decode_git_refs,
    decode_merge_result,
    decode_reflog_entries,
    decode_repo_entries,
    decode_repo_info,
    decode_snapshot_plan,
    decode_squash_report,
    decode_storage_overview,
    decode_verify_report,
)


def _sha256_hex(data: bytes) -> str:
    """
    Return the hexadecimal SHA-256 digest for one byte payload.

    :param data: Payload bytes to hash
    :type data: bytes
    :return: Bare hexadecimal SHA-256 digest
    :rtype: str
    """

    from hashlib import sha256

    return sha256(data).hexdigest()


def _normalize_glob_patterns(values) -> list:
    """
    Normalize string-or-list glob inputs.

    :param values: Raw glob input
    :type values: object
    :return: Normalized glob patterns
    :rtype: list
    """

    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    normalized = []
    for item in values:
        text = str(item)
        if text.endswith("/"):
            normalized.append(text + "*")
        else:
            normalized.append(text)
    return normalized


def _filter_local_paths(paths, *, allow_patterns=None, ignore_patterns=None) -> list:
    """
    Filter local relative paths using HF-style glob semantics.

    :param paths: Candidate relative paths
    :type paths: Sequence[str]
    :param allow_patterns: Optional allowlist patterns
    :type allow_patterns: Optional[Union[Sequence[str], str]]
    :param ignore_patterns: Optional denylist patterns
    :type ignore_patterns: Optional[Union[Sequence[str], str]]
    :return: Filtered relative paths
    :rtype: list
    """

    normalized_allow = _normalize_glob_patterns(allow_patterns)
    normalized_ignore = _normalize_glob_patterns(ignore_patterns)

    filtered = []
    for item in paths:
        if normalized_allow and not any(fnmatch(item, rule) for rule in normalized_allow):
            continue
        if normalized_ignore and any(fnmatch(item, rule) for rule in normalized_ignore):
            continue
        filtered.append(item)
    return filtered


FAST_UPLOAD_CHUNK_THRESHOLD = 1024 * 1024


class _UploadProgressState:
    """
    Track aggregate multipart upload progress for one commit request.

    :param total_bytes: Total request payload bytes attributed to upload parts
    :type total_bytes: int
    :param progress_callback: Optional callback receiving ``(sent, total)``
    :type progress_callback: Optional[Callable[[int, int], None]]
    """

    def __init__(self, total_bytes: int, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
        """
        Initialize one upload-progress tracker.

        :param total_bytes: Total request payload bytes attributed to upload parts
        :type total_bytes: int
        :param progress_callback: Optional callback receiving ``(sent, total)``
        :type progress_callback: Optional[Callable[[int, int], None]]
        :return: ``None``.
        :rtype: None
        """

        self.total_bytes = max(int(total_bytes), 0)
        self.sent_bytes = 0
        self._progress_callback = progress_callback
        if self._progress_callback is not None:
            self._progress_callback(self.sent_bytes, self.total_bytes)

    def advance(self, delta: int) -> None:
        """
        Advance the tracked upload byte counter.

        :param delta: Number of newly streamed bytes
        :type delta: int
        :return: ``None``.
        :rtype: None
        """

        if delta <= 0:
            return
        self.sent_bytes = min(self.total_bytes, self.sent_bytes + int(delta))
        if self._progress_callback is not None:
            self._progress_callback(self.sent_bytes, self.total_bytes)

    def finish(self) -> None:
        """
        Mark the upload as fully streamed.

        :return: ``None``.
        :rtype: None
        """

        self.sent_bytes = self.total_bytes
        if self._progress_callback is not None:
            self._progress_callback(self.sent_bytes, self.total_bytes)


class _UploadProgressReader(io.BytesIO):
    """
    Wrap one in-memory upload part and report streamed bytes.

    :param data: Upload payload bytes
    :type data: bytes
    :param state: Shared aggregate upload-progress tracker
    :type state: _UploadProgressState
    """

    def __init__(self, data: bytes, state: _UploadProgressState) -> None:
        """
        Build one progress-reporting upload reader.

        :param data: Upload payload bytes
        :type data: bytes
        :param state: Shared aggregate upload-progress tracker
        :type state: _UploadProgressState
        :return: ``None``.
        :rtype: None
        """

        super(_UploadProgressReader, self).__init__(data)
        self._state = state

    def read(self, size: int = -1) -> bytes:
        """
        Read upload bytes while updating shared progress.

        :param size: Requested byte count
        :type size: int
        :return: Read payload bytes
        :rtype: bytes
        """

        chunk = super(_UploadProgressReader, self).read(size)
        self._state.advance(len(chunk))
        return chunk


def _build_progress_callback(
    total_bytes: int,
    *,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    show_progress: bool = False,
) -> tuple:
    """
    Build one upload-progress callback and optional tqdm cleanup hook.

    :param total_bytes: Total request payload bytes attributed to upload parts
    :type total_bytes: int
    :param progress_callback: Optional explicit progress callback
    :type progress_callback: Optional[Callable[[int, int], None]]
    :param show_progress: Whether a local tqdm progress bar should be shown
    :type show_progress: bool
    :return: Tuple of ``(callback, close_callback)``
    :rtype: tuple
    """

    if progress_callback is not None:
        return progress_callback, None
    if not show_progress or total_bytes <= 0:
        return None, None

    try:
        tqdm_auto = import_optional_dependency(
            "tqdm.auto",
            extra="remote",
            feature="remote upload progress reporting",
            missing_names={"tqdm"},
        )
    except MissingOptionalDependencyError:
        return None, None

    progress_bar = tqdm_auto.tqdm(total=total_bytes, unit="B", unit_scale=True, desc="hubvault upload")

    def _progress_callback(sent_bytes: int, total: int) -> None:
        progress_bar.total = total
        progress_bar.n = sent_bytes
        progress_bar.refresh()

    return _progress_callback, progress_bar.close


class HubVaultRemoteApi:
    """
    Remote API client aligned with :class:`hubvault.api.HubVaultApi`.

    The remote client intentionally mirrors the local API naming for common
    read and write paths so callers can switch between embedded and HTTP-backed
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

    def _build_add_manifest(self, operation: CommitOperationAdd) -> tuple:
        """
        Build one upload-manifest entry for a public add operation.

        :param operation: Public add operation
        :type operation: CommitOperationAdd
        :return: Tuple of normalized manifest payload and local upload source
        :rtype: tuple
        """

        with operation.as_file() as fileobj:
            data = fileobj.read()

        manifest_operation = {
            "type": "add",
            "path_in_repo": operation.path_in_repo,
            "size": len(data),
            "sha256": _sha256_hex(data),
            "chunks": [],
        }
        upload_source = {
            "data": data,
            "chunks": [],
        }
        if len(data) >= FAST_UPLOAD_CHUNK_THRESHOLD:
            chunk_plan = ChunkStore().plan_bytes(data)
            manifest_operation["chunks"] = [
                {
                    "chunk_id": descriptor.chunk_id,
                    "checksum": descriptor.checksum,
                    "logical_offset": descriptor.logical_offset,
                    "logical_size": descriptor.logical_size,
                    "stored_size": descriptor.stored_size,
                    "compression": descriptor.compression,
                }
                for descriptor in chunk_plan.chunks
            ]
            upload_source["chunks"] = [part.data for part in chunk_plan.parts]
        return manifest_operation, upload_source

    def _build_commit_manifest(
        self,
        *,
        operations: Sequence[object],
        commit_message: str,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> tuple:
        """
        Build the upload manifest and local upload sources for one commit call.

        :param operations: Public commit operations
        :type operations: Sequence[object]
        :param commit_message: Commit summary/title
        :type commit_message: str
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param revision: Optional target revision override
        :type revision: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :return: Tuple of normalized manifest payload and upload sources
        :rtype: tuple
        """

        manifest_operations = []
        upload_sources = {}
        for index, operation in enumerate(operations):
            if isinstance(operation, CommitOperationAdd):
                manifest_operation, upload_source = self._build_add_manifest(operation)
                manifest_operations.append(manifest_operation)
                upload_sources[index] = upload_source
            elif isinstance(operation, CommitOperationDelete):
                manifest_operations.append(
                    {
                        "type": "delete",
                        "path_in_repo": operation.path_in_repo,
                        "is_folder": bool(operation.is_folder),
                    }
                )
            elif isinstance(operation, CommitOperationCopy):
                manifest_operations.append(
                    {
                        "type": "copy",
                        "src_path_in_repo": operation.src_path_in_repo,
                        "path_in_repo": operation.path_in_repo,
                        "src_revision": operation.src_revision,
                    }
                )
            else:
                raise TypeError("Unsupported commit operation: %r." % (type(operation).__name__,))
        return (
            {
                "revision": self._selected_revision(revision),
                "parent_commit": parent_commit,
                "commit_message": commit_message,
                "commit_description": commit_description,
                "operations": manifest_operations,
            },
            upload_sources,
        )

    def _planned_commit_request(
        self,
        manifest: dict,
        upload_sources: dict,
        *,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: bool = False,
    ):
        """
        Execute the ``commit-plan`` / ``commit`` upload flow.

        :param manifest: Normalized write manifest
        :type manifest: dict
        :param upload_sources: Local upload sources indexed by operation number
        :type upload_sources: dict
        :param progress_callback: Optional callback receiving ``(sent, total)``
            upload-byte updates for streamed file/chunk parts
        :type progress_callback: Optional[Callable[[int, int], None]]
        :param show_progress: Whether to show a tqdm progress bar when no
            explicit callback is provided
        :type show_progress: bool
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        """

        with self.build_client() as client:
            plan = request_json(
                client,
                "POST",
                "/api/v1/write/commit-plan",
                json=manifest,
            )
            progress_callback, close_progress = _build_progress_callback(
                int(plan.get("statistics", {}).get("planned_upload_bytes", 0)),
                progress_callback=progress_callback,
                show_progress=show_progress,
            )
            progress_state = (
                _UploadProgressState(
                    int(plan.get("statistics", {}).get("planned_upload_bytes", 0)),
                    progress_callback,
                )
                if progress_callback is not None
                else None
            )
            apply_manifest = dict(manifest)
            if apply_manifest.get("parent_commit") is None:
                apply_manifest["parent_commit"] = plan.get("base_head")
            apply_manifest["upload_plan"] = plan

            files = []
            for planned_operation in plan.get("operations", []):
                if planned_operation.get("type") != "add":
                    continue
                source = upload_sources.get(int(planned_operation["index"]))
                if source is None:
                    continue
                if planned_operation.get("strategy") == "upload-full":
                    field_name = str(planned_operation["field_name"])
                    payload_data = bytes(source["data"])
                    files.append(
                        (
                            field_name,
                            (
                                field_name,
                                _UploadProgressReader(payload_data, progress_state)
                                if progress_state is not None
                                else payload_data,
                                "application/octet-stream",
                            ),
                        )
                    )
                elif planned_operation.get("strategy") == "chunk-upload":
                    for chunk_payload in planned_operation.get("missing_chunks", []):
                        chunk_index = int(chunk_payload["chunk_index"])
                        payload_data = bytes(source["chunks"][chunk_index])
                        files.append(
                            (
                                str(chunk_payload["field_name"]),
                                (
                                    str(chunk_payload["chunk_id"]) + ".bin",
                                    _UploadProgressReader(payload_data, progress_state)
                                    if progress_state is not None
                                    else payload_data,
                                    "application/octet-stream",
                                ),
                            )
                        )

            try:
                if files:
                    payload = request_json(
                        client,
                        "POST",
                        "/api/v1/write/commit",
                        data={"manifest": json.dumps(apply_manifest)},
                        files=files,
                    )
                else:
                    payload = request_json(
                        client,
                        "POST",
                        "/api/v1/write/commit",
                        json=apply_manifest,
                    )
                if progress_state is not None:
                    progress_state.finish()
            finally:
                if close_progress is not None:
                    close_progress()
        return decode_commit_info(payload)

    def create_commit(
        self,
        operations: Sequence[object] = (),
        *,
        commit_message: str,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: bool = False,
    ):
        """
        Create one remote commit through the planned upload protocol.

        :param operations: Public commit operations to apply
        :type operations: Sequence[object]
        :param commit_message: Commit summary/title
        :type commit_message: str
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param revision: Optional target branch override
        :type revision: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :param progress_callback: Optional callback receiving ``(sent, total)``
            upload-byte updates for streamed file/chunk parts
        :type progress_callback: Optional[Callable[[int, int], None]]
        :param show_progress: Whether to show a tqdm progress bar when no
            explicit callback is provided
        :type show_progress: bool
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        """

        manifest, upload_sources = self._build_commit_manifest(
            operations=operations,
            commit_message=commit_message,
            commit_description=commit_description,
            revision=revision,
            parent_commit=parent_commit,
        )
        return self._planned_commit_request(
            manifest,
            upload_sources,
            progress_callback=progress_callback,
            show_progress=show_progress,
        )

    def merge(
        self,
        source_revision: str,
        *,
        target_revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
    ):
        """
        Merge one remote source revision into a target branch.

        :param source_revision: Source revision to merge
        :type source_revision: str
        :param target_revision: Optional target branch override
        :type target_revision: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :param commit_message: Optional merge-commit title
        :type commit_message: Optional[str]
        :param commit_description: Optional merge-commit body
        :type commit_description: Optional[str]
        :return: Structured merge result
        :rtype: hubvault.models.MergeResult
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/write/merge",
                json={
                    "source_revision": source_revision,
                    "target_revision": self._selected_revision(target_revision),
                    "parent_commit": parent_commit,
                    "commit_message": commit_message,
                    "commit_description": commit_description,
                },
            )
        return decode_merge_result(payload)

    def create_branch(
        self,
        *,
        branch: str,
        revision: Optional[str] = None,
        exist_ok: bool = False,
    ) -> None:
        """
        Create one remote branch.

        :param branch: Branch name to create
        :type branch: str
        :param revision: Optional start-point revision
        :type revision: Optional[str]
        :param exist_ok: Whether an existing branch may be reused
        :type exist_ok: bool
        :return: ``None``.
        :rtype: None
        """

        with self.build_client() as client:
            request_json(
                client,
                "POST",
                "/api/v1/write/branches",
                json={
                    "branch": branch,
                    "revision": self._selected_revision(revision),
                    "exist_ok": bool(exist_ok),
                },
            )

    def delete_branch(self, *, branch: str) -> None:
        """
        Delete one remote branch.

        :param branch: Branch name to delete
        :type branch: str
        :return: ``None``.
        :rtype: None
        """

        with self.build_client() as client:
            request_json(
                client,
                "DELETE",
                "/api/v1/write/branches/%s" % (quote(branch, safe=""),),
            )

    def create_tag(
        self,
        *,
        tag: str,
        tag_message: Optional[str] = None,
        revision: Optional[str] = None,
        exist_ok: bool = False,
    ) -> None:
        """
        Create one remote lightweight tag.

        :param tag: Tag name to create
        :type tag: str
        :param tag_message: Optional reflog message for the new tag
        :type tag_message: Optional[str]
        :param revision: Optional start-point revision
        :type revision: Optional[str]
        :param exist_ok: Whether an existing tag may be reused
        :type exist_ok: bool
        :return: ``None``.
        :rtype: None
        """

        with self.build_client() as client:
            request_json(
                client,
                "POST",
                "/api/v1/write/tags",
                json={
                    "tag": tag,
                    "tag_message": tag_message,
                    "revision": self._selected_revision(revision),
                    "exist_ok": bool(exist_ok),
                },
            )

    def delete_tag(self, *, tag: str) -> None:
        """
        Delete one remote lightweight tag.

        :param tag: Tag name to delete
        :type tag: str
        :return: ``None``.
        :rtype: None
        """

        with self.build_client() as client:
            request_json(
                client,
                "DELETE",
                "/api/v1/write/tags/%s" % (quote(tag, safe=""),),
            )

    def reset_ref(self, ref_name: str, *, to_revision: str):
        """
        Reset one remote branch ref to a target revision.

        :param ref_name: Branch name to update
        :type ref_name: str
        :param to_revision: Revision to resolve as the new head
        :type to_revision: str
        :return: Commit metadata for the new head
        :rtype: hubvault.models.CommitInfo
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/write/reset-ref",
                json={
                    "ref_name": ref_name,
                    "to_revision": to_revision,
                },
            )
        return decode_commit_info(payload)

    def quick_verify(self):
        """
        Run the remote quick verification pass.

        :return: Verification report
        :rtype: hubvault.models.VerifyReport
        """

        with self.build_client() as client:
            payload = request_json(client, "POST", "/api/v1/maintenance/quick-verify")
        return decode_verify_report(payload)

    def full_verify(self):
        """
        Run the remote full verification pass.

        :return: Verification report
        :rtype: hubvault.models.VerifyReport
        """

        with self.build_client() as client:
            payload = request_json(client, "POST", "/api/v1/maintenance/full-verify")
        return decode_verify_report(payload)

    def get_storage_overview(self):
        """
        Fetch the remote storage-overview report.

        :return: Storage overview
        :rtype: hubvault.models.StorageOverview
        """

        with self.build_client() as client:
            payload = request_json(client, "GET", "/api/v1/maintenance/storage-overview")
        return decode_storage_overview(payload)

    def gc(
        self,
        *,
        dry_run: bool = False,
        prune_cache: bool = True,
    ):
        """
        Run one remote GC pass.

        :param dry_run: Whether to compute the result without mutating storage
        :type dry_run: bool
        :param prune_cache: Whether rebuildable cache areas should be pruned
        :type prune_cache: bool
        :return: GC report
        :rtype: hubvault.models.GcReport
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/maintenance/gc",
                json={
                    "dry_run": bool(dry_run),
                    "prune_cache": bool(prune_cache),
                },
            )
        return decode_gc_report(payload)

    def squash_history(
        self,
        ref_name: str,
        *,
        root_revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        run_gc: bool = True,
        prune_cache: bool = False,
    ):
        """
        Rewrite one remote branch history chain.

        :param ref_name: Branch name or full branch ref to rewrite
        :type ref_name: str
        :param root_revision: Optional oldest commit to preserve
        :type root_revision: Optional[str]
        :param commit_message: Optional replacement root title
        :type commit_message: Optional[str]
        :param commit_description: Optional replacement root body
        :type commit_description: Optional[str]
        :param run_gc: Whether a GC pass should run immediately after rewriting
        :type run_gc: bool
        :param prune_cache: Whether the follow-up GC should also prune caches
        :type prune_cache: bool
        :return: History-squash report
        :rtype: hubvault.models.SquashReport
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/maintenance/squash-history",
                json={
                    "ref_name": ref_name,
                    "root_revision": root_revision,
                    "commit_message": commit_message,
                    "commit_description": commit_description,
                    "run_gc": bool(run_gc),
                    "prune_cache": bool(prune_cache),
                },
            )
        return decode_squash_report(payload)

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

    def get_commit_detail(self, commit_id: str, *, formatted: bool = False):
        """
        Return one remote commit together with its first-parent file changes.

        :param commit_id: Public commit ID or revision resolving to a commit
        :type commit_id: str
        :param formatted: Whether HTML-formatted title/message fields should be populated
        :type formatted: bool
        :return: Commit metadata with file-level changes
        :rtype: hubvault.models.CommitDetailInfo
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "GET",
                "/api/v1/history/commits/%s" % (quote(commit_id, safe=""),),
                params={
                    "formatted": formatted,
                },
            )
        return decode_commit_detail_info(payload)

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

    def upload_file(
        self,
        *,
        path_or_fileobj: Union[str, PathLike, bytes, BinaryIO],
        path_in_repo: str,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: bool = False,
    ):
        """
        Upload one file through the remote planned-commit protocol.

        :param path_or_fileobj: File content source
        :type path_or_fileobj: Union[str, os.PathLike[str], bytes, BinaryIO]
        :param path_in_repo: Target repo-relative path
        :type path_in_repo: str
        :param revision: Optional target branch override
        :type revision: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :param progress_callback: Optional callback receiving ``(sent, total)``
            upload-byte updates for streamed file/chunk parts
        :type progress_callback: Optional[Callable[[int, int], None]]
        :param show_progress: Whether to show a tqdm progress bar when no
            explicit callback is provided
        :type show_progress: bool
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        """

        return self.create_commit(
            operations=[CommitOperationAdd(path_in_repo=path_in_repo, path_or_fileobj=path_or_fileobj)],
            commit_message=commit_message or "Upload %s with hubvault" % (path_in_repo,),
            commit_description=commit_description,
            revision=revision,
            parent_commit=parent_commit,
            progress_callback=progress_callback,
            show_progress=show_progress,
        )

    def upload_folder(
        self,
        *,
        folder_path: Union[str, PathLike],
        path_in_repo: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
        delete_patterns: Optional[Union[Sequence[str], str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: bool = False,
    ):
        """
        Upload one local folder through the remote planned-commit protocol.

        :param folder_path: Local folder to upload
        :type folder_path: Union[str, os.PathLike[str]]
        :param path_in_repo: Optional target directory in the repo
        :type path_in_repo: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param revision: Optional target branch override
        :type revision: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :param allow_patterns: Optional allowlist for local relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]]
        :param ignore_patterns: Optional denylist for local relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]]
        :param delete_patterns: Optional denylist applied to already uploaded
            repo files below ``path_in_repo``
        :type delete_patterns: Optional[Union[Sequence[str], str]]
        :param progress_callback: Optional callback receiving ``(sent, total)``
            upload-byte updates for streamed file/chunk parts
        :type progress_callback: Optional[Callable[[int, int], None]]
        :param show_progress: Whether to show a tqdm progress bar when no
            explicit callback is provided
        :type show_progress: bool
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        :raises ValueError: Raised when ``folder_path`` is not a local
            directory.
        """

        root = Path(folder_path)
        if not root.is_dir():
            raise ValueError("folder_path must point to an existing local directory")

        base_path = "" if path_in_repo in (None, "") else str(path_in_repo).strip("/")
        local_paths = []
        for current_root, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = sorted(name for name in dirnames if name != ".git")
            current_root_path = Path(current_root)
            for filename in sorted(filenames):
                local_paths.append((current_root_path / filename).relative_to(root).as_posix())

        filtered_local_paths = _filter_local_paths(
            local_paths,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
        )

        add_operations = []
        for relative_path in filtered_local_paths:
            repo_path = relative_path if not base_path else base_path + "/" + relative_path
            add_operations.append(
                CommitOperationAdd(
                    path_in_repo=repo_path,
                    path_or_fileobj=str(root / relative_path),
                )
            )

        delete_operations = []
        if delete_patterns is not None:
            delete_rules = _normalize_glob_patterns(delete_patterns)
            selected_revision = self._selected_revision(revision)
            existing_paths = self.list_repo_files(revision=selected_revision)
            for existing_path in sorted(existing_paths):
                relative_existing_path = existing_path
                if base_path:
                    prefix = base_path + "/"
                    if not existing_path.startswith(prefix):
                        continue
                    relative_existing_path = existing_path[len(prefix):]
                if relative_existing_path == ".gitattributes":
                    continue
                if any(fnmatch(relative_existing_path, rule) for rule in delete_rules):
                    delete_operations.append(CommitOperationDelete(path_in_repo=existing_path, is_folder=False))

            added_paths = {operation.path_in_repo for operation in add_operations}
            delete_operations = [
                operation
                for operation in delete_operations
                if operation.path_in_repo not in added_paths
            ]

        return self.create_commit(
            operations=delete_operations + add_operations,
            commit_message=commit_message or "Upload folder using hubvault",
            commit_description=commit_description,
            revision=revision,
            parent_commit=parent_commit,
            progress_callback=progress_callback,
            show_progress=show_progress,
        )

    def upload_large_folder(
        self,
        *,
        folder_path: Union[str, PathLike],
        revision: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: bool = False,
    ):
        """
        Upload one local folder through the remote large-folder flow.

        :param folder_path: Local folder to upload
        :type folder_path: Union[str, os.PathLike[str]]
        :param revision: Optional target branch override
        :type revision: Optional[str]
        :param allow_patterns: Optional allowlist for local relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]]
        :param ignore_patterns: Optional denylist for local relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]]
        :param progress_callback: Optional callback receiving ``(sent, total)``
            upload-byte updates for streamed file/chunk parts
        :type progress_callback: Optional[Callable[[int, int], None]]
        :param show_progress: Whether to show a tqdm progress bar when no
            explicit callback is provided
        :type show_progress: bool
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        """

        return self.upload_folder(
            folder_path=folder_path,
            path_in_repo=None,
            commit_message="Upload large folder using hubvault",
            commit_description=None,
            revision=revision,
            parent_commit=None,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
            delete_patterns=None,
            progress_callback=progress_callback,
            show_progress=show_progress,
        )

    def delete_file(
        self,
        path_in_repo: str,
        *,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ):
        """
        Delete one remote file through the public write API.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Optional target branch override
        :type revision: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/write/delete-file",
                json={
                    "path_in_repo": path_in_repo,
                    "revision": self._selected_revision(revision),
                    "commit_message": commit_message,
                    "commit_description": commit_description,
                    "parent_commit": parent_commit,
                },
            )
        return decode_commit_info(payload)

    def delete_folder(
        self,
        path_in_repo: str,
        *,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ):
        """
        Delete one remote folder subtree through the public write API.

        :param path_in_repo: Repo-relative folder path
        :type path_in_repo: str
        :param revision: Optional target branch override
        :type revision: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param parent_commit: Optional optimistic-concurrency base head
        :type parent_commit: Optional[str]
        :return: Commit metadata for the created commit
        :rtype: hubvault.models.CommitInfo
        """

        with self.build_client() as client:
            payload = request_json(
                client,
                "POST",
                "/api/v1/write/delete-folder",
                json={
                    "path_in_repo": path_in_repo,
                    "revision": self._selected_revision(revision),
                    "commit_message": commit_message,
                    "commit_description": commit_description,
                    "parent_commit": parent_commit,
                },
            )
        return decode_commit_info(payload)

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
