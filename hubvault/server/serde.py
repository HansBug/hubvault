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
* :func:`encode_reflog_entry` - Serialize reflog entries
* :func:`build_snapshot_plan_payload` - Build the remote snapshot manifest
"""

from datetime import datetime
from typing import Iterable, List, Optional

from ..models import (
    BlobLfsInfo,
    BlobSecurityInfo,
    GitCommitInfo,
    GitRefInfo,
    GitRefs,
    LastCommitInfo,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    RepoInfo,
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
