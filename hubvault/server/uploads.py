"""
Write-manifest planning helpers for :mod:`hubvault.server`.

This module implements the HTTP-side upload planning and apply logic used by
the Phase 7 write routes. The protocol is intentionally conservative: upload
plans are bound to one immutable branch head so a stale preflight cannot be
applied after an intervening write.

The module contains:

* :func:`plan_commit_manifest` - Build one upload plan for a write manifest
* :func:`apply_commit_manifest` - Materialize public commit operations from a
  planned manifest and uploaded payload parts
"""

from hashlib import sha256
from typing import Dict, Iterable, List, Mapping, Optional

from ..errors import ConflictError, HubVaultValidationError
from ..operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete


def _sha256_hex(data: bytes) -> str:
    """
    Return the hexadecimal SHA-256 digest for one byte payload.

    :param data: Payload bytes to hash
    :type data: bytes
    :return: Bare hexadecimal SHA-256 digest
    :rtype: str
    """

    return sha256(data).hexdigest()


def _chunk_id_for_bytes(data: bytes) -> str:
    """
    Return the internal chunk identifier for one payload.

    :param data: Chunk payload bytes
    :type data: bytes
    :return: Internal chunk identifier with the ``sha256:`` prefix
    :rtype: str
    """

    return "sha256:%s" % (_sha256_hex(data),)


def _build_file_field_name(index: int) -> str:
    """
    Build the multipart field name for one full-file upload.

    :param index: Operation index inside the write manifest
    :type index: int
    :return: Multipart field name
    :rtype: str
    """

    return "upload_file_%d" % (index,)


def _build_chunk_field_name(index: int, chunk_index: int) -> str:
    """
    Build the multipart field name for one missing chunk upload.

    :param index: Operation index inside the write manifest
    :type index: int
    :param chunk_index: Chunk index inside the add operation
    :type chunk_index: int
    :return: Multipart field name
    :rtype: str
    """

    return "upload_chunk_%d_%d" % (index, chunk_index)


def _read_backend(api):
    """
    Return the backend object wrapped by one public API instance.

    :param api: Public repository API instance
    :type api: hubvault.api.HubVaultApi
    :return: Repository backend used by ``api``
    :rtype: hubvault.repo.backend.RepositoryBackend
    """

    return api._backend


def _target_branch_state(api, manifest: dict) -> dict:
    """
    Resolve the immutable target-branch state for one write manifest.

    The returned state is intentionally restricted to the selected branch head.
    This makes the upload plan safe against concurrent writes: if the branch
    head changes, the final apply step will fail its optimistic-concurrency
    check and the caller must re-plan.

    :param api: Public repository API instance
    :type api: hubvault.api.HubVaultApi
    :param manifest: Normalized write manifest
    :type manifest: dict
    :return: Selected branch state and fast-path lookup tables
    :rtype: dict
    :raises hubvault.errors.ConflictError: Raised when an explicit
        ``parent_commit`` does not match the current branch head.
    """

    backend = _read_backend(api)
    with backend._read_locked():
        repo_config = backend._repo_config()
        selected_revision = manifest["revision"] or str(repo_config["default_branch"])
        target_branch = backend._resolve_target_branch_name_unlocked(selected_revision)
        current_head = backend._read_ref(target_branch)

        parent_commit = manifest.get("parent_commit")
        if parent_commit is not None:
            expected_parent = backend._resolve_revision(parent_commit)
            if expected_parent != current_head:
                raise ConflictError("expected head does not match current branch head")

        snapshot = {} if current_head is None else backend._snapshot_for_commit(current_head)
        sha_sources = {}
        visible_chunk_ids = set()
        for path, file_object_id in snapshot.items():
            file_payload = backend._read_object_payload("files", file_object_id)
            file_sha256 = str(file_payload["sha256"])
            if file_sha256.startswith("sha256:"):
                file_sha256 = file_sha256[len("sha256:"):]
            sha_sources.setdefault(file_sha256, path)
            if str(file_payload.get("storage_kind")) == "chunked":
                for chunk_payload in file_payload.get("chunks", []):
                    visible_chunk_ids.add(str(chunk_payload["chunk_id"]))

        return {
            "revision": target_branch,
            "current_head": backend._public_commit_oid_or_none(current_head),
            "sha_sources": sha_sources,
            "visible_chunk_ids": visible_chunk_ids,
        }


def plan_commit_manifest(api, manifest: dict) -> dict:
    """
    Build one upload plan for a normalized write manifest.

    :param api: Public repository API instance
    :type api: hubvault.api.HubVaultApi
    :param manifest: Normalized write manifest
    :type manifest: dict
    :return: JSON-compatible upload plan
    :rtype: dict
    :raises hubvault.errors.ConflictError: Raised when ``parent_commit`` is
        stale relative to the current branch head.
    """

    state = _target_branch_state(api, manifest)
    copy_file_count = 0
    full_upload_file_count = 0
    chunk_fast_upload_file_count = 0
    reused_chunk_count = 0
    missing_chunk_count = 0
    planned_upload_bytes = 0
    planned_operations = []

    for index, operation in enumerate(manifest["operations"]):
        if operation["type"] != "add":
            planned_operations.append(
                {
                    "index": index,
                    "type": operation["type"],
                    "path_in_repo": operation.get("path_in_repo"),
                    "strategy": "passthrough",
                    "field_name": None,
                    "source_path_in_repo": None,
                    "source_revision": None,
                    "missing_chunks": [],
                    "reused_chunk_count": 0,
                    "missing_chunk_count": 0,
                }
            )
            continue

        source_path = state["sha_sources"].get(operation["sha256"])
        if source_path is not None and state["current_head"] is not None:
            copy_file_count += 1
            planned_operations.append(
                {
                    "index": index,
                    "type": "add",
                    "path_in_repo": operation["path_in_repo"],
                    "strategy": "copy",
                    "field_name": None,
                    "source_path_in_repo": source_path,
                    "source_revision": state["current_head"],
                    "missing_chunks": [],
                    "reused_chunk_count": 0,
                    "missing_chunk_count": 0,
                }
            )
            continue

        chunks = operation.get("chunks") or []
        reusable_chunks = [chunk for chunk in chunks if chunk["chunk_id"] in state["visible_chunk_ids"]]
        if chunks and reusable_chunks:
            missing_chunks = []
            for chunk_index, chunk in enumerate(chunks):
                if chunk["chunk_id"] in state["visible_chunk_ids"]:
                    continue
                missing_chunks.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "chunk_index": chunk_index,
                        "field_name": _build_chunk_field_name(index, chunk_index),
                        "logical_size": chunk["logical_size"],
                    }
                )
            chunk_fast_upload_file_count += 1
            reused_chunk_count += len(reusable_chunks)
            missing_chunk_count += len(missing_chunks)
            planned_upload_bytes += sum(item["logical_size"] for item in missing_chunks)
            planned_operations.append(
                {
                    "index": index,
                    "type": "add",
                    "path_in_repo": operation["path_in_repo"],
                    "strategy": "chunk-upload",
                    "field_name": None,
                    "source_path_in_repo": None,
                    "source_revision": None,
                    "missing_chunks": missing_chunks,
                    "reused_chunk_count": len(reusable_chunks),
                    "missing_chunk_count": len(missing_chunks),
                }
            )
            continue

        full_upload_file_count += 1
        planned_upload_bytes += int(operation["size"])
        planned_operations.append(
            {
                "index": index,
                "type": "add",
                "path_in_repo": operation["path_in_repo"],
                "strategy": "upload-full",
                "field_name": _build_file_field_name(index),
                "source_path_in_repo": None,
                "source_revision": None,
                "missing_chunks": [],
                "reused_chunk_count": 0,
                "missing_chunk_count": 0,
            }
        )

    return {
        "revision": state["revision"],
        "base_head": state["current_head"],
        "operations": planned_operations,
        "statistics": {
            "copy_file_count": copy_file_count,
            "full_upload_file_count": full_upload_file_count,
            "chunk_fast_upload_file_count": chunk_fast_upload_file_count,
            "reused_chunk_count": reused_chunk_count,
            "missing_chunk_count": missing_chunk_count,
            "planned_upload_bytes": planned_upload_bytes,
        },
    }


def _validate_upload_plan(manifest: dict, plan: dict) -> None:
    """
    Validate that one apply-time upload plan still matches its manifest.

    :param manifest: Normalized write manifest
    :type manifest: dict
    :param plan: Normalized upload plan
    :type plan: dict
    :return: ``None``.
    :rtype: None
    :raises HubVaultValidationError: Raised when the plan and manifest diverge.
    """

    if len(manifest["operations"]) != len(plan["operations"]):
        raise HubVaultValidationError("upload_plan.operations must align with operations.")

    for index, (operation, planned_operation) in enumerate(zip(manifest["operations"], plan["operations"])):
        if int(planned_operation["index"]) != index:
            raise HubVaultValidationError("upload_plan.operations[%d].index is out of sync." % (index,))
        if planned_operation["type"] != operation["type"]:
            raise HubVaultValidationError("upload_plan.operations[%d].type is out of sync." % (index,))
        if operation["type"] == "add" and planned_operation["path_in_repo"] != operation["path_in_repo"]:
            raise HubVaultValidationError("upload_plan.operations[%d].path_in_repo is out of sync." % (index,))


def _read_existing_chunk_bytes(backend, chunk_descriptors: Iterable[dict]) -> Dict[str, bytes]:
    """
    Read reusable chunk payloads from the current repository state.

    :param backend: Repository backend used by the server API
    :type backend: hubvault.repo.backend.RepositoryBackend
    :param chunk_descriptors: Chunk descriptors that should already exist in the
        selected base snapshot
    :type chunk_descriptors: Iterable[dict]
    :return: Mapping from chunk ID to verified chunk bytes
    :rtype: Dict[str, bytes]
    :raises hubvault.errors.ConflictError: Raised when the selected chunk is no
        longer visible under the current base snapshot.
    """

    payloads = {}
    with backend._read_locked():
        chunk_context = backend._new_chunk_read_context(track_verified_chunks=False)
        try:
            visible_entries = chunk_context["visible_entries"]
            for descriptor in chunk_descriptors:
                chunk_id = descriptor["chunk_id"]
                if chunk_id in payloads:
                    continue
                entry = visible_entries.get(chunk_id)
                if entry is None:
                    raise ConflictError("planned chunk is no longer available; please re-plan the upload")
                chunk_view = backend._read_verified_chunk_view(entry, descriptor["checksum"], chunk_context)
                try:
                    payloads[chunk_id] = bytes(chunk_view)
                finally:
                    backend._release_chunk_view(chunk_view)
        finally:
            backend._close_chunk_read_context(chunk_context)
    return payloads


def _materialize_add_operation(backend, operation: dict, planned_operation: dict, uploads: Mapping[str, bytes]):
    """
    Materialize one planned add operation into a public commit operation.

    :param backend: Repository backend used by the server API
    :type backend: hubvault.repo.backend.RepositoryBackend
    :param operation: Normalized add-manifest operation
    :type operation: dict
    :param planned_operation: Normalized planned add operation
    :type planned_operation: dict
    :param uploads: Uploaded multipart payloads indexed by field name
    :type uploads: Mapping[str, bytes]
    :return: Public add/copy operation
    :rtype: object
    :raises HubVaultValidationError: Raised when uploaded payloads are missing
        or fail checksum validation.
    """

    strategy = planned_operation["strategy"]
    if strategy == "copy":
        return CommitOperationCopy(
            src_path_in_repo=planned_operation["source_path_in_repo"],
            path_in_repo=operation["path_in_repo"],
            src_revision=planned_operation["source_revision"],
        )

    if strategy == "upload-full":
        field_name = planned_operation["field_name"]
        if field_name not in uploads:
            raise HubVaultValidationError("Missing uploaded file payload: %s." % (field_name,))
        data = bytes(uploads[field_name])
        if len(data) != int(operation["size"]):
            raise HubVaultValidationError("Uploaded file payload size does not match the manifest.")
        if _sha256_hex(data) != operation["sha256"]:
            raise HubVaultValidationError("Uploaded file payload checksum does not match the manifest.")
        return CommitOperationAdd(path_in_repo=operation["path_in_repo"], path_or_fileobj=data)

    if strategy == "chunk-upload":
        missing_by_index = dict(
            (int(item["chunk_index"]), item)
            for item in planned_operation.get("missing_chunks", [])
        )
        reusable_descriptors = [
            chunk
            for chunk_index, chunk in enumerate(operation.get("chunks") or [])
            if chunk_index not in missing_by_index
        ]
        reusable_payloads = _read_existing_chunk_bytes(backend, reusable_descriptors) if reusable_descriptors else {}
        parts = []
        for chunk_index, chunk in enumerate(operation.get("chunks") or []):
            missing_chunk = missing_by_index.get(chunk_index)
            if missing_chunk is not None:
                field_name = missing_chunk["field_name"]
                if field_name not in uploads:
                    raise HubVaultValidationError("Missing uploaded chunk payload: %s." % (field_name,))
                payload = bytes(uploads[field_name])
            else:
                payload = reusable_payloads.get(chunk["chunk_id"])
                if payload is None:
                    raise ConflictError("planned chunk is no longer available; please re-plan the upload")

            if len(payload) != int(chunk["logical_size"]):
                raise HubVaultValidationError("Chunk payload size does not match the manifest.")
            if _chunk_id_for_bytes(payload) != chunk["chunk_id"]:
                raise HubVaultValidationError("Chunk payload checksum does not match the manifest.")
            parts.append(payload)

        data = b"".join(parts)
        if len(data) != int(operation["size"]):
            raise HubVaultValidationError("Reconstructed file size does not match the manifest.")
        if _sha256_hex(data) != operation["sha256"]:
            raise HubVaultValidationError("Reconstructed file checksum does not match the manifest.")
        return CommitOperationAdd(path_in_repo=operation["path_in_repo"], path_or_fileobj=data)

    raise HubVaultValidationError("Unsupported upload strategy: %s." % (strategy,))


def apply_commit_manifest(api, manifest: dict, uploads: Mapping[str, bytes]):
    """
    Apply one previously planned write manifest.

    :param api: Public repository API instance
    :type api: hubvault.api.HubVaultApi
    :param manifest: Normalized write manifest including ``upload_plan``
    :type manifest: dict
    :param uploads: Uploaded multipart payloads indexed by field name
    :type uploads: Mapping[str, bytes]
    :return: Commit metadata for the created commit
    :rtype: hubvault.models.CommitInfo
    :raises HubVaultValidationError: Raised when the apply payload is invalid.
    :raises hubvault.errors.ConflictError: Raised when the planned branch head
        is stale and the caller must re-plan.
    """

    upload_plan = manifest.get("upload_plan")
    if upload_plan is None:
        raise HubVaultValidationError("upload_plan is required when applying a write manifest.")

    effective_manifest = dict(manifest)
    if effective_manifest.get("parent_commit") is None:
        effective_manifest["parent_commit"] = upload_plan.get("base_head")

    state = _target_branch_state(api, effective_manifest)
    if upload_plan["revision"] != state["revision"]:
        raise HubVaultValidationError("upload_plan.revision does not match the selected target branch.")
    if upload_plan.get("base_head") != state["current_head"]:
        raise ConflictError("branch head changed after upload planning; please re-plan the upload")
    _validate_upload_plan(manifest, upload_plan)

    backend = _read_backend(api)
    commit_operations = []
    for operation, planned_operation in zip(manifest["operations"], upload_plan["operations"]):
        if operation["type"] == "add":
            commit_operations.append(_materialize_add_operation(backend, operation, planned_operation, uploads))
        elif operation["type"] == "delete":
            commit_operations.append(
                CommitOperationDelete(
                    path_in_repo=operation["path_in_repo"],
                    is_folder=bool(operation["is_folder"]),
                )
            )
        elif operation["type"] == "copy":
            commit_operations.append(
                CommitOperationCopy(
                    src_path_in_repo=operation["src_path_in_repo"],
                    path_in_repo=operation["path_in_repo"],
                    src_revision=operation.get("src_revision"),
                )
            )
        else:  # pragma: no cover
            raise HubVaultValidationError("Unsupported write operation type: %s." % (operation["type"],))

    return api.create_commit(
        operations=commit_operations,
        commit_message=manifest["commit_message"],
        commit_description=manifest.get("commit_description"),
        revision=state["revision"],
        parent_commit=effective_manifest.get("parent_commit"),
    )
