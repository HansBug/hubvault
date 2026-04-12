"""
Response-serialization helpers for :mod:`hubvault.server`.

This module converts public ``hubvault`` dataclasses into JSON-compatible
payloads for the HTTP API. The conversion is explicit so the remote client can
reconstruct the same public model classes without relying on FastAPI internals.

The module contains:

* :func:`encode_repo_info` - Serialize repository metadata
* :func:`encode_repo_entry` - Serialize file and folder entries
* :func:`encode_git_refs` - Serialize branch and tag refs
* :func:`encode_git_commit_info` - Serialize commit-list entries
* :func:`encode_commit_file_version_info` - Serialize one commit diff file side
* :func:`encode_commit_change_info` - Serialize one commit diff entry
* :func:`encode_commit_detail_info` - Serialize one commit detail payload
* :func:`encode_reflog_entry` - Serialize reflog entries
* :func:`encode_commit_info` - Serialize write-commit metadata
* :func:`encode_merge_result` - Serialize structured merge results
* :func:`encode_verify_report` - Serialize repository verification reports
* :func:`encode_storage_summary` - Serialize lightweight storage summary
* :func:`encode_storage_overview` - Serialize repository storage analysis
* :func:`encode_gc_report` - Serialize storage reclamation reports
* :func:`encode_squash_report` - Serialize history-squash reports
* :func:`build_snapshot_plan_payload` - Build the remote snapshot manifest
"""

from datetime import datetime
from typing import Iterable, List, Mapping, Optional

from ..models import (
    BlobLfsInfo,
    BlobSecurityInfo,
    CommitChangeInfo,
    CommitDetailInfo,
    CommitInfo,
    CommitFileVersionInfo,
    GcReport,
    GitCommitInfo,
    GitRefInfo,
    GitRefs,
    LastCommitInfo,
    MergeConflict,
    MergeResult,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    RepoInfo,
    StorageOverview,
    StorageSectionInfo,
    SquashReport,
    VerifyReport,
)


def _encode_datetime(value: Optional[datetime]) -> Optional[str]:
    """
    Serialize one optional datetime value.

    :param value: Datetime value to serialize
    :type value: Optional[datetime.datetime]
    :return: ISO-8601 string or ``None``
    :rtype: Optional[str]
    """

    return None if value is None else value.isoformat()


def encode_last_commit_info(value: Optional[LastCommitInfo]) -> Optional[dict]:
    """
    Serialize optional last-commit metadata.

    :param value: Last-commit metadata, if available
    :type value: Optional[LastCommitInfo]
    :return: JSON-compatible last-commit payload or ``None``
    :rtype: Optional[dict]
    """

    if value is None:
        return None
    return {
        "oid": value.oid,
        "title": value.title,
        "date": _encode_datetime(value.date),
    }


def encode_blob_security_info(value: Optional[BlobSecurityInfo]) -> Optional[dict]:
    """
    Serialize optional blob-security metadata.

    :param value: Blob-security metadata, if available
    :type value: Optional[BlobSecurityInfo]
    :return: JSON-compatible security payload or ``None``
    :rtype: Optional[dict]
    """

    if value is None:
        return None
    return {
        "safe": value.safe,
        "status": value.status,
        "av_scan": value.av_scan,
        "pickle_import_scan": value.pickle_import_scan,
    }


def encode_blob_lfs_info(value: Optional[BlobLfsInfo]) -> Optional[dict]:
    """
    Serialize optional large-file metadata.

    :param value: Large-file metadata, if available
    :type value: Optional[BlobLfsInfo]
    :return: JSON-compatible LFS payload or ``None``
    :rtype: Optional[dict]
    """

    if value is None:
        return None
    return {
        "size": value.size,
        "sha256": value.sha256,
        "pointer_size": value.pointer_size,
    }


def encode_repo_info(value: RepoInfo) -> dict:
    """
    Serialize repository metadata.

    :param value: Repository metadata model
    :type value: RepoInfo
    :return: JSON-compatible repository metadata
    :rtype: dict
    """

    return {
        "repo_path": value.repo_path,
        "format_version": value.format_version,
        "default_branch": value.default_branch,
        "head": value.head,
        "refs": list(value.refs),
    }


def encode_repo_entry(value) -> dict:
    """
    Serialize one repository file or folder entry.

    :param value: Repository entry model
    :type value: Union[RepoFile, RepoFolder]
    :return: JSON-compatible entry payload with an ``entry_type`` discriminator
    :rtype: dict
    :raises TypeError: Raised when ``value`` is not a supported entry model.
    """

    if isinstance(value, RepoFile):
        return {
            "entry_type": "file",
            "path": value.path,
            "size": value.size,
            "blob_id": value.blob_id,
            "lfs": encode_blob_lfs_info(value.lfs),
            "last_commit": encode_last_commit_info(value.last_commit),
            "security": encode_blob_security_info(value.security),
            "oid": value.oid,
            "sha256": value.sha256,
            "etag": value.etag,
        }
    if isinstance(value, RepoFolder):
        return {
            "entry_type": "folder",
            "path": value.path,
            "tree_id": value.tree_id,
            "last_commit": encode_last_commit_info(value.last_commit),
        }
    raise TypeError("Unsupported repository entry model: %r." % (type(value).__name__,))


def encode_repo_entries(values: Iterable[object]) -> List[dict]:
    """
    Serialize repository file and folder entries.

    :param values: Repository entry models
    :type values: Iterable[object]
    :return: JSON-compatible entry payloads
    :rtype: List[dict]
    """

    return [encode_repo_entry(value) for value in values]


def encode_git_commit_info(value: GitCommitInfo) -> dict:
    """
    Serialize one commit-list entry.

    :param value: Commit-list entry model
    :type value: GitCommitInfo
    :return: JSON-compatible commit payload
    :rtype: dict
    """

    return {
        "commit_id": value.commit_id,
        "authors": list(value.authors),
        "created_at": _encode_datetime(value.created_at),
        "title": value.title,
        "message": value.message,
        "formatted_title": value.formatted_title,
        "formatted_message": value.formatted_message,
    }


def encode_git_commit_list(values: Iterable[GitCommitInfo]) -> List[dict]:
    """
    Serialize commit-list entries.

    :param values: Commit-list entry models
    :type values: Iterable[GitCommitInfo]
    :return: JSON-compatible commit payloads
    :rtype: List[dict]
    """

    return [encode_git_commit_info(value) for value in values]


def encode_commit_file_version_info(value: Optional[CommitFileVersionInfo]) -> Optional[dict]:
    """
    Serialize one optional commit-diff file-side entry.

    :param value: Commit-diff file-side metadata, if available
    :type value: Optional[CommitFileVersionInfo]
    :return: JSON-compatible file-side payload or ``None``
    :rtype: Optional[dict]
    """

    if value is None:
        return None
    return {
        "path": value.path,
        "size": value.size,
        "oid": value.oid,
        "blob_id": value.blob_id,
        "sha256": value.sha256,
    }


def encode_commit_change_info(value: CommitChangeInfo) -> dict:
    """
    Serialize one file-level commit change entry.

    :param value: File-level commit change metadata
    :type value: CommitChangeInfo
    :return: JSON-compatible commit change payload
    :rtype: dict
    """

    return {
        "path": value.path,
        "change_type": value.change_type,
        "old_file": encode_commit_file_version_info(value.old_file),
        "new_file": encode_commit_file_version_info(value.new_file),
        "is_binary": value.is_binary,
        "unified_diff": value.unified_diff,
    }


def encode_commit_detail_info(value: CommitDetailInfo) -> dict:
    """
    Serialize one commit-detail payload.

    :param value: Commit detail metadata
    :type value: CommitDetailInfo
    :return: JSON-compatible commit detail payload
    :rtype: dict
    """

    return {
        "commit": encode_git_commit_info(value.commit),
        "parent_commit_ids": list(value.parent_commit_ids),
        "compare_parent_commit_id": value.compare_parent_commit_id,
        "changes": [encode_commit_change_info(item) for item in value.changes],
    }


def encode_commit_info(value: CommitInfo) -> dict:
    """
    Serialize one write-commit result.

    :param value: Commit metadata returned by a write API
    :type value: CommitInfo
    :return: JSON-compatible commit payload
    :rtype: dict
    """

    return {
        "commit_url": value.commit_url,
        "commit_message": value.commit_message,
        "commit_description": value.commit_description,
        "oid": value.oid,
        "pr_url": value.pr_url,
        "repo_url": value.repo_url,
        "pr_revision": value.pr_revision,
        "pr_num": value.pr_num,
        "_url": str(value),
    }


def encode_merge_conflict(value: MergeConflict) -> dict:
    """
    Serialize one structured merge conflict.

    :param value: Merge conflict model
    :type value: MergeConflict
    :return: JSON-compatible conflict payload
    :rtype: dict
    """

    return {
        "path": value.path,
        "conflict_type": value.conflict_type,
        "message": value.message,
        "base_oid": value.base_oid,
        "target_oid": value.target_oid,
        "source_oid": value.source_oid,
        "related_path": value.related_path,
    }


def encode_merge_result(value: MergeResult) -> dict:
    """
    Serialize one structured merge result.

    :param value: Merge result model
    :type value: MergeResult
    :return: JSON-compatible merge payload
    :rtype: dict
    """

    return {
        "status": value.status,
        "target_revision": value.target_revision,
        "source_revision": value.source_revision,
        "base_commit": value.base_commit,
        "target_head_before": value.target_head_before,
        "source_head": value.source_head,
        "head_after": value.head_after,
        "commit": None if value.commit is None else encode_commit_info(value.commit),
        "conflicts": [encode_merge_conflict(item) for item in value.conflicts],
        "fast_forward": value.fast_forward,
        "created_commit": value.created_commit,
    }


def encode_git_ref_info(value: GitRefInfo) -> dict:
    """
    Serialize one git reference entry.

    :param value: Git reference entry model
    :type value: GitRefInfo
    :return: JSON-compatible ref payload
    :rtype: dict
    """

    return {
        "name": value.name,
        "ref": value.ref,
        "target_commit": value.target_commit,
    }


def encode_git_refs(value: GitRefs) -> dict:
    """
    Serialize branch and tag reference metadata.

    :param value: Git refs model
    :type value: GitRefs
    :return: JSON-compatible refs payload
    :rtype: dict
    """

    return {
        "branches": [encode_git_ref_info(item) for item in value.branches],
        "converts": [encode_git_ref_info(item) for item in value.converts],
        "tags": [encode_git_ref_info(item) for item in value.tags],
        "pull_requests": None
        if value.pull_requests is None
        else [encode_git_ref_info(item) for item in value.pull_requests],
    }


def encode_reflog_entry(value: ReflogEntry) -> dict:
    """
    Serialize one reflog entry.

    :param value: Reflog entry model
    :type value: ReflogEntry
    :return: JSON-compatible reflog payload
    :rtype: dict
    """

    return {
        "timestamp": _encode_datetime(value.timestamp),
        "ref_name": value.ref_name,
        "old_head": value.old_head,
        "new_head": value.new_head,
        "message": value.message,
        "checksum": value.checksum,
    }


def encode_reflog_entries(values: Iterable[ReflogEntry]) -> List[dict]:
    """
    Serialize reflog entries.

    :param values: Reflog entry models
    :type values: Iterable[ReflogEntry]
    :return: JSON-compatible reflog payloads
    :rtype: List[dict]
    """

    return [encode_reflog_entry(value) for value in values]


def encode_verify_report(value: VerifyReport) -> dict:
    """
    Serialize one repository verification report.

    :param value: Verification report model
    :type value: VerifyReport
    :return: JSON-compatible verification payload
    :rtype: dict
    """

    return {
        "ok": value.ok,
        "checked_refs": list(value.checked_refs),
        "warnings": list(value.warnings),
        "errors": list(value.errors),
    }


def encode_storage_section_info(value: StorageSectionInfo) -> dict:
    """
    Serialize one storage section analysis entry.

    :param value: Storage section analysis model
    :type value: StorageSectionInfo
    :return: JSON-compatible storage section payload
    :rtype: dict
    """

    return {
        "name": value.name,
        "path": value.path,
        "total_size": value.total_size,
        "file_count": value.file_count,
        "reclaimable_size": value.reclaimable_size,
        "reclaim_strategy": value.reclaim_strategy,
        "notes": value.notes,
    }


def encode_storage_summary(value: Mapping[str, object]) -> dict:
    """
    Serialize one lightweight storage-summary payload.

    :param value: Lightweight storage summary mapping
    :type value: Mapping[str, object]
    :return: JSON-compatible storage summary payload
    :rtype: dict
    """

    return {
        "total_size": int(value["total_size"]),
        "total_file_count": int(value["total_file_count"]),
        "metadata_size": int(value["metadata_size"]),
        "metadata_file_count": int(value["metadata_file_count"]),
        "branch_count": int(value["branch_count"]),
        "tag_count": int(value["tag_count"]),
    }


def encode_storage_overview(value: StorageOverview) -> dict:
    """
    Serialize repository-wide storage analysis.

    :param value: Storage analysis model
    :type value: StorageOverview
    :return: JSON-compatible storage overview payload
    :rtype: dict
    """

    return {
        "total_size": value.total_size,
        "reachable_size": value.reachable_size,
        "historical_retained_size": value.historical_retained_size,
        "reclaimable_gc_size": value.reclaimable_gc_size,
        "reclaimable_cache_size": value.reclaimable_cache_size,
        "reclaimable_temporary_size": value.reclaimable_temporary_size,
        "sections": [encode_storage_section_info(item) for item in value.sections],
        "recommendations": list(value.recommendations),
    }


def encode_gc_report(value: GcReport) -> dict:
    """
    Serialize one garbage-collection report.

    :param value: GC report model
    :type value: GcReport
    :return: JSON-compatible GC payload
    :rtype: dict
    """

    return {
        "dry_run": value.dry_run,
        "checked_refs": list(value.checked_refs),
        "reclaimed_size": value.reclaimed_size,
        "reclaimed_object_size": value.reclaimed_object_size,
        "reclaimed_chunk_size": value.reclaimed_chunk_size,
        "reclaimed_cache_size": value.reclaimed_cache_size,
        "reclaimed_temporary_size": value.reclaimed_temporary_size,
        "removed_file_count": value.removed_file_count,
        "notes": list(value.notes),
    }


def encode_squash_report(value: SquashReport) -> dict:
    """
    Serialize one history-squash report.

    :param value: Squash report model
    :type value: SquashReport
    :return: JSON-compatible squash payload
    :rtype: dict
    """

    return {
        "ref_name": value.ref_name,
        "old_head": value.old_head,
        "new_head": value.new_head,
        "root_commit_before": value.root_commit_before,
        "rewritten_commit_count": value.rewritten_commit_count,
        "dropped_ancestor_count": value.dropped_ancestor_count,
        "blocking_refs": list(value.blocking_refs),
        "gc_report": None if value.gc_report is None else encode_gc_report(value.gc_report),
    }


def build_snapshot_plan_payload(
    *,
    revision: str,
    resolved_revision: str,
    head: Optional[str],
    files: Iterable[dict],
    allow_patterns: Iterable[str],
    ignore_patterns: Iterable[str],
) -> dict:
    """
    Build the remote-consumable snapshot manifest.

    :param revision: Requested revision string
    :type revision: str
    :param resolved_revision: Immutable revision used for file downloads
    :type resolved_revision: str
    :param head: Resolved commit OID, if available
    :type head: Optional[str]
    :param files: File manifest entries
    :type files: Iterable[dict]
    :param allow_patterns: Normalized allowlist patterns
    :type allow_patterns: Iterable[str]
    :param ignore_patterns: Normalized ignore patterns
    :type ignore_patterns: Iterable[str]
    :return: JSON-compatible snapshot manifest
    :rtype: dict
    """

    return {
        "revision": revision,
        "resolved_revision": resolved_revision,
        "head": head,
        "allow_patterns": list(allow_patterns),
        "ignore_patterns": list(ignore_patterns),
        "files": list(files),
    }


def build_meta_service_payload(*, service, version, mode, repo_path, ui_enabled, default_branch, head, auth) -> dict:
    """
    Build the ``/api/v1/meta/service`` response body.

    :param service: Service title
    :type service: str
    :param version: Service version string
    :type version: str
    :param mode: Active server mode
    :type mode: str
    :param repo_path: Repository root path
    :type repo_path: str
    :param ui_enabled: Whether the frontend UI is enabled
    :type ui_enabled: bool
    :param default_branch: Repository default branch
    :type default_branch: str
    :param head: Current repository head OID
    :type head: Optional[str]
    :param auth: Authentication summary payload
    :type auth: dict
    :return: JSON-compatible service payload
    :rtype: dict
    """

    return {
        "service": service,
        "version": version,
        "mode": mode,
        "ui_enabled": ui_enabled,
        "repo": {
            "path": repo_path,
            "default_branch": default_branch,
            "head": head,
        },
        "auth": auth,
    }


def build_whoami_payload(*, access, can_write) -> dict:
    """
    Build the ``/api/v1/meta/whoami`` response body.

    :param access: Resolved access level
    :type access: str
    :param can_write: Whether the caller may mutate repository state
    :type can_write: bool
    :return: JSON-compatible caller summary
    :rtype: dict
    """

    return {
        "access": access,
        "can_write": can_write,
    }
