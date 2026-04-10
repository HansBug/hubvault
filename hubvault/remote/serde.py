"""
Serialization helpers for :mod:`hubvault.remote`.

This module reconstructs public ``hubvault`` dataclasses and exception types
from server JSON payloads.

The module contains:

* :func:`decode_json_payload` - Normalize one decoded JSON payload
* :func:`decode_error_response` - Map one error payload back to a public exception
"""

from datetime import datetime

from ..errors import (
    ConflictError,
    EntryNotFoundError,
    HubVaultError,
    HubVaultValidationError,
    IntegrityError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
    VerificationError,
)
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
from .errors import HubVaultRemoteAuthError, HubVaultRemoteProtocolError


_PUBLIC_ERROR_TYPES = {
    error_type.__name__: error_type
    for error_type in [
        ConflictError,
        EntryNotFoundError,
        HubVaultValidationError,
        IntegrityError,
        RepositoryAlreadyExistsError,
        RepositoryNotFoundError,
        RevisionNotFoundError,
        UnsupportedPathError,
        VerificationError,
    ]
}


def _require_dict(payload, name: str) -> dict:
    """
    Validate that one payload value is a JSON object.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :param name: Human-readable payload name
    :type name: str
    :return: JSON object payload
    :rtype: dict
    :raises HubVaultRemoteProtocolError: Raised when the payload is not an object.
    """

    if not isinstance(payload, dict):
        raise HubVaultRemoteProtocolError("%s must be a JSON object." % (name,))
    return payload


def _parse_datetime(value, field_name: str) -> datetime:
    """
    Parse one ISO-8601 datetime string.

    :param value: Raw JSON field value
    :type value: object
    :param field_name: Field name used in validation messages
    :type field_name: str
    :return: Parsed datetime value
    :rtype: datetime.datetime
    :raises HubVaultRemoteProtocolError: Raised when the value is missing or invalid.
    """

    if not isinstance(value, str):
        raise HubVaultRemoteProtocolError("%s must be an ISO-8601 string." % (field_name,))
    try:
        return datetime.fromisoformat(value)
    except ValueError as err:
        raise HubVaultRemoteProtocolError("Invalid datetime for %s: %s" % (field_name, err))


def _decode_last_commit_info(payload):
    """
    Decode optional last-commit metadata.

    :param payload: Raw last-commit payload
    :type payload: object
    :return: Decoded last-commit metadata or ``None``
    :rtype: Optional[LastCommitInfo]
    """

    if payload is None:
        return None
    data = _require_dict(payload, "last_commit")
    return LastCommitInfo(
        oid=str(data["oid"]),
        title=str(data["title"]),
        date=_parse_datetime(data["date"], "last_commit.date"),
    )


def _decode_blob_security_info(payload):
    """
    Decode optional blob-security metadata.

    :param payload: Raw blob-security payload
    :type payload: object
    :return: Decoded blob-security metadata or ``None``
    :rtype: Optional[BlobSecurityInfo]
    """

    if payload is None:
        return None
    data = _require_dict(payload, "security")
    return BlobSecurityInfo(
        safe=bool(data["safe"]),
        status=str(data["status"]),
        av_scan=data.get("av_scan"),
        pickle_import_scan=data.get("pickle_import_scan"),
    )


def _decode_blob_lfs_info(payload):
    """
    Decode optional large-file metadata.

    :param payload: Raw large-file payload
    :type payload: object
    :return: Decoded large-file metadata or ``None``
    :rtype: Optional[BlobLfsInfo]
    """

    if payload is None:
        return None
    data = _require_dict(payload, "lfs")
    return BlobLfsInfo(
        size=int(data["size"]),
        sha256=str(data["sha256"]),
        pointer_size=int(data["pointer_size"]),
    )


def decode_json_payload(payload):
    """
    Return the decoded JSON payload unchanged for the skeleton stage.

    :param payload: Decoded JSON-compatible payload
    :type payload: object
    :return: The same payload value
    :rtype: object
    """

    return payload


def decode_error_response(payload, *, status_code: int):
    """
    Map one error payload back to a public exception object.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :param status_code: HTTP status code attached to the response
    :type status_code: int
    :return: Public exception instance matching the server response
    :rtype: Exception
    """

    data = _require_dict(payload, "error response")
    error_data = data.get("error")
    if isinstance(error_data, dict):
        message = str(error_data.get("message", "Remote request failed."))
        error_type_name = str(error_data.get("type", ""))
    else:
        message = str(data.get("detail", "Remote request failed."))
        error_type_name = ""

    if status_code in {401, 403}:
        return HubVaultRemoteAuthError(message)

    error_type = _PUBLIC_ERROR_TYPES.get(error_type_name)
    if error_type is not None:
        return error_type(message)
    return HubVaultRemoteProtocolError(message)


def decode_repo_info(payload) -> RepoInfo:
    """
    Decode repository metadata from JSON.

    :param payload: Raw repository payload
    :type payload: object
    :return: Decoded repository metadata
    :rtype: RepoInfo
    """

    data = _require_dict(payload, "repo_info")
    return RepoInfo(
        repo_path=str(data["repo_path"]),
        format_version=int(data["format_version"]),
        default_branch=str(data["default_branch"]),
        head=None if data.get("head") is None else str(data["head"]),
        refs=[str(item) for item in data.get("refs", [])],
    )


def decode_repo_entry(payload):
    """
    Decode one repository file or folder entry.

    :param payload: Raw repository entry payload
    :type payload: object
    :return: Decoded file or folder entry
    :rtype: Union[RepoFile, RepoFolder]
    :raises HubVaultRemoteProtocolError: Raised when the entry type is unsupported.
    """

    data = _require_dict(payload, "repo entry")
    entry_type = str(data.get("entry_type", ""))
    if entry_type == "file":
        return RepoFile(
            path=str(data["path"]),
            size=int(data["size"]),
            blob_id=str(data["blob_id"]),
            lfs=_decode_blob_lfs_info(data.get("lfs")),
            last_commit=_decode_last_commit_info(data.get("last_commit")),
            security=_decode_blob_security_info(data.get("security")),
            oid=None if data.get("oid") is None else str(data.get("oid")),
            sha256=None if data.get("sha256") is None else str(data.get("sha256")),
            etag=None if data.get("etag") is None else str(data.get("etag")),
        )
    if entry_type == "folder":
        return RepoFolder(
            path=str(data["path"]),
            tree_id=str(data["tree_id"]),
            last_commit=_decode_last_commit_info(data.get("last_commit")),
        )
    raise HubVaultRemoteProtocolError("Unsupported repo entry type: %r." % (entry_type,))


def decode_repo_entries(payload) -> list:
    """
    Decode repository file and folder entries from JSON.

    :param payload: Raw repository entries payload
    :type payload: object
    :return: Decoded repository entries
    :rtype: list
    """

    if not isinstance(payload, list):
        raise HubVaultRemoteProtocolError("Repository entries must be a JSON array.")
    return [decode_repo_entry(item) for item in payload]


def decode_git_commit_info(payload) -> GitCommitInfo:
    """
    Decode one commit-list entry from JSON.

    :param payload: Raw commit-list payload
    :type payload: object
    :return: Decoded commit-list entry
    :rtype: GitCommitInfo
    """

    data = _require_dict(payload, "git commit info")
    return GitCommitInfo(
        commit_id=str(data["commit_id"]),
        authors=[str(item) for item in data.get("authors", [])],
        created_at=_parse_datetime(data["created_at"], "created_at"),
        title=str(data["title"]),
        message=str(data["message"]),
        formatted_title=None if data.get("formatted_title") is None else str(data["formatted_title"]),
        formatted_message=None if data.get("formatted_message") is None else str(data["formatted_message"]),
    )


def decode_git_commit_list(payload) -> list:
    """
    Decode commit-list entries from JSON.

    :param payload: Raw commit-list payload
    :type payload: object
    :return: Decoded commit-list entries
    :rtype: list
    """

    if not isinstance(payload, list):
        raise HubVaultRemoteProtocolError("Commit list must be a JSON array.")
    return [decode_git_commit_info(item) for item in payload]


def decode_git_ref_info(payload) -> GitRefInfo:
    """
    Decode one git reference entry from JSON.

    :param payload: Raw ref payload
    :type payload: object
    :return: Decoded git ref entry
    :rtype: GitRefInfo
    """

    data = _require_dict(payload, "git ref info")
    return GitRefInfo(
        name=str(data["name"]),
        ref=str(data["ref"]),
        target_commit=None if data.get("target_commit") is None else str(data.get("target_commit")),
    )


def decode_git_refs(payload) -> GitRefs:
    """
    Decode branch and tag refs from JSON.

    :param payload: Raw refs payload
    :type payload: object
    :return: Decoded refs collection
    :rtype: GitRefs
    """

    data = _require_dict(payload, "git refs")
    pull_requests = data.get("pull_requests")
    return GitRefs(
        branches=[decode_git_ref_info(item) for item in data.get("branches", [])],
        converts=[decode_git_ref_info(item) for item in data.get("converts", [])],
        tags=[decode_git_ref_info(item) for item in data.get("tags", [])],
        pull_requests=None if pull_requests is None else [decode_git_ref_info(item) for item in pull_requests],
    )


def decode_reflog_entry(payload) -> ReflogEntry:
    """
    Decode one reflog entry from JSON.

    :param payload: Raw reflog payload
    :type payload: object
    :return: Decoded reflog entry
    :rtype: ReflogEntry
    """

    data = _require_dict(payload, "reflog entry")
    return ReflogEntry(
        timestamp=_parse_datetime(data["timestamp"], "timestamp"),
        ref_name=str(data["ref_name"]),
        old_head=None if data.get("old_head") is None else str(data.get("old_head")),
        new_head=None if data.get("new_head") is None else str(data.get("new_head")),
        message=str(data["message"]),
        checksum=str(data["checksum"]),
    )


def decode_reflog_entries(payload) -> list:
    """
    Decode reflog entries from JSON.

    :param payload: Raw reflog payload
    :type payload: object
    :return: Decoded reflog entries
    :rtype: list
    """

    if not isinstance(payload, list):
        raise HubVaultRemoteProtocolError("Reflog entries must be a JSON array.")
    return [decode_reflog_entry(item) for item in payload]


def decode_snapshot_plan(payload) -> dict:
    """
    Decode a snapshot-plan manifest from JSON.

    :param payload: Raw snapshot-plan payload
    :type payload: object
    :return: Normalized snapshot-plan manifest
    :rtype: dict
    """

    data = _require_dict(payload, "snapshot plan")
    files = data.get("files", [])
    if not isinstance(files, list):
        raise HubVaultRemoteProtocolError("Snapshot plan files must be a JSON array.")
    normalized_files = []
    for item in files:
        file_data = _require_dict(item, "snapshot plan file")
        normalized_files.append(
            {
                "path": str(file_data["path"]),
                "size": int(file_data["size"]),
                "blob_id": str(file_data["blob_id"]),
                "oid": None if file_data.get("oid") is None else str(file_data.get("oid")),
                "sha256": None if file_data.get("sha256") is None else str(file_data.get("sha256")),
                "etag": None if file_data.get("etag") is None else str(file_data.get("etag")),
                "download_url": str(file_data["download_url"]),
            }
        )

    return {
        "revision": str(data["revision"]),
        "resolved_revision": str(data["resolved_revision"]),
        "head": None if data.get("head") is None else str(data.get("head")),
        "allow_patterns": [str(item) for item in data.get("allow_patterns", [])],
        "ignore_patterns": [str(item) for item in data.get("ignore_patterns", [])],
        "files": normalized_files,
    }
