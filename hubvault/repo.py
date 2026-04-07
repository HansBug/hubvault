"""
Repository backend for the :mod:`hubvault` MVP.

This module implements the local on-disk repository format used by the MVP.
The backend is intentionally embedded and file-based so the repository remains
self-contained and movable as a normal directory tree.

The module contains:

* :class:`_RepositoryBackend` - Internal repository service used by the public API
"""

import io
import json
import os
import re
import secrets
import shutil
import stat
from datetime import datetime, timezone
from html import escape as html_escape
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Sequence, Tuple

from .errors import (
    ConflictError,
    IntegrityError,
    LockTimeoutError,
    PathNotFoundError,
    RepoAlreadyExistsError,
    RepoNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
)
from .models import CommitInfo, GitCommitInfo, PathInfo, RepoInfo, VerifyReport
from .operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete

FORMAT_MARKER = "hubvault-repo/v1"
FORMAT_VERSION = 1
DEFAULT_BRANCH = "main"
OBJECT_HASH = "sha256"
LARGE_FILE_THRESHOLD = 16 * 1024 * 1024
WRITE_LOCK_DIR = "write.lock"
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
REF_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")


def _utc_now() -> str:
    """
    Return the current UTC timestamp in repository string format.

    The repository persists timestamps in a compact UTC form so metadata stays
    stable across platforms and archive moves.

    :return: Timestamp formatted as ``YYYY-MM-DDTHH:MM:SSZ``
    :rtype: str

    Example::

        >>> timestamp = _utc_now()
        >>> timestamp.endswith("Z")
        True
    """

    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_json_bytes(data: object) -> bytes:
    """
    Encode JSON data with the repository's canonical serialization settings.

    Canonical encoding keeps object IDs stable by ensuring key ordering and
    whitespace rules do not vary between processes or platforms.

    :param data: JSON-serializable object to encode
    :type data: object
    :return: Canonically encoded UTF-8 JSON bytes
    :rtype: bytes

    Example::

        >>> _stable_json_bytes({"b": 1, "a": 2})
        b'{"a":2,"b":1}'
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    """
    Compute the hexadecimal SHA-256 digest for a byte string.

    :param data: Input bytes
    :type data: bytes
    :return: Lowercase hexadecimal SHA-256 digest
    :rtype: str

    Example::

        >>> _sha256_hex(b"abc")
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    """

    return sha256(data).hexdigest()


def _public_sha256_hex(value: str) -> str:
    """
    Normalize a public-facing SHA-256 value to raw hexadecimal form.

    Public API fields should match :mod:`huggingface_hub` semantics, where
    ``sha256`` values are exposed as bare hexadecimal digests without an
    algorithm prefix. The helper also accepts legacy ``sha256:<hex>`` values so
    existing repositories remain readable after the alignment change.

    :param value: Public or legacy SHA-256 string
    :type value: str
    :return: Raw hexadecimal digest without the ``sha256:`` prefix
    :rtype: str

    Example::

        >>> _public_sha256_hex("sha256:abc123")
        'abc123'
        >>> _public_sha256_hex("abc123")
        'abc123'
    """

    text = str(value)
    if text.startswith(OBJECT_HASH + ":"):
        _, digest = _split_object_id(text)
        return digest
    return text


def _integrity_sha256(value: str) -> str:
    """
    Normalize a SHA-256 value to the internal integrity-check form.

    Repository object payloads and checksums continue to use the explicit
    ``sha256:<hex>`` format internally, even though public API fields expose raw
    hexadecimal digests.

    :param value: Public or internal SHA-256 string
    :type value: str
    :return: Internal integrity string with ``sha256:`` prefix
    :rtype: str

    Example::

        >>> _integrity_sha256("abc123")
        'sha256:abc123'
        >>> _integrity_sha256("sha256:abc123")
        'sha256:abc123'
    """

    text = str(value)
    if text.startswith(OBJECT_HASH + ":"):
        return text
    return OBJECT_HASH + ":" + text


def _git_blob_oid(data: bytes) -> str:
    """
    Compute a Git-compatible blob object ID for file content bytes.

    The public file ``oid`` exposed by :mod:`hubvault` is aligned with the
    conventional Git blob hashing scheme used by Hugging Face metadata.

    :param data: Logical file content
    :type data: bytes
    :return: Git blob SHA-1 digest
    :rtype: str

    Example::

        >>> len(_git_blob_oid(b"hello"))
        40
    """

    header = "blob %d\0" % len(data)
    return sha1(header.encode("utf-8") + data).hexdigest()


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """
    Atomically replace a file with the provided bytes.

    The helper writes to a temporary sibling file first and then swaps it into
    place, which avoids partial writes becoming visible to readers.

    :param path: Destination filesystem path
    :type path: pathlib.Path
    :param data: Bytes to write
    :type data: bytes
    :return: ``None``.
    :rtype: None

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     path = Path(tmpdir) / "demo.bin"
        ...     _write_bytes_atomic(path, b"hello")
        ...     path.read_bytes()
        b'hello'
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / (path.name + ".tmp." + secrets.token_hex(4))
    with temp_path.open("wb") as file_:
        file_.write(data)
        file_.flush()
        os.fsync(file_.fileno())
    os.replace(str(temp_path), str(path))


def _write_text_atomic(path: Path, text: str) -> None:
    """
    Atomically replace a UTF-8 text file.

    This helper delegates to :func:`_write_bytes_atomic` after encoding the text
    as UTF-8.

    :param path: Destination filesystem path
    :type path: pathlib.Path
    :param text: Text content to write
    :type text: str
    :return: ``None``.
    :rtype: None

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     path = Path(tmpdir) / "demo.txt"
        ...     _write_text_atomic(path, "hello")
        ...     path.read_text(encoding="utf-8")
        'hello'
    """

    _write_bytes_atomic(path, text.encode("utf-8"))


def _write_json_atomic(path: Path, payload: object) -> None:
    """
    Atomically replace a JSON file using canonical repository encoding.

    Repository metadata files use this helper so their serialized bytes remain
    stable and safe to publish with a final atomic swap.

    :param path: Destination filesystem path
    :type path: pathlib.Path
    :param payload: JSON-serializable payload
    :type payload: object
    :return: ``None``.
    :rtype: None

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     path = Path(tmpdir) / "demo.json"
        ...     _write_json_atomic(path, {"answer": 42})
        ...     _read_json(path)["answer"]
        42
    """

    _write_bytes_atomic(path, _stable_json_bytes(payload))


def _read_text(path: Path) -> str:
    """
    Read a UTF-8 text file.

    :param path: Source filesystem path
    :type path: pathlib.Path
    :return: Decoded text content
    :rtype: str

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     path = Path(tmpdir) / "demo.txt"
        ...     path.write_text("hello", encoding="utf-8")
        ...     _read_text(path)
        'hello'
    """

    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> object:
    """
    Read and decode a JSON file.

    :param path: Source filesystem path
    :type path: pathlib.Path
    :return: Decoded JSON payload
    :rtype: object

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     path = Path(tmpdir) / "demo.json"
        ...     path.write_text('{"answer": 42}', encoding="utf-8")
        ...     _read_json(path)["answer"]
        42
    """

    with path.open("r", encoding="utf-8") as file_:
        return json.load(file_)


def _normalize_repo_path(path_in_repo: str) -> str:
    """
    Normalize and validate a repo-relative logical path.

    Logical repository paths always use POSIX separators and must stay safe on
    all supported platforms, including Windows.

    :param path_in_repo: User-supplied repo-relative path
    :type path_in_repo: str
    :return: Normalized POSIX path
    :rtype: str
    :raises UnsupportedPathError: Raised when the path is empty, absolute, or
        contains platform-unsafe segments.

    Example::

        >>> _normalize_repo_path("models\\\\demo.bin")
        'models/demo.bin'
    """

    raw = str(path_in_repo).replace("\\", "/")
    if not raw:
        raise UnsupportedPathError("path_in_repo must not be empty")
    if raw.startswith("/"):
        raise UnsupportedPathError("path_in_repo must be relative")
    if DRIVE_PATTERN.match(raw):
        raise UnsupportedPathError("path_in_repo must not use an absolute drive path")

    normalized = PurePosixPath(raw)
    parts = normalized.parts
    if not parts or normalized.is_absolute():
        raise UnsupportedPathError("path_in_repo must be a non-empty relative path")

    safe_parts = []
    for part in parts:
        if part in ("", ".", ".."):
            raise UnsupportedPathError("path_in_repo contains an illegal path segment")
        if any(ch in part for ch in '\0<>:"|?*'):
            raise UnsupportedPathError("path_in_repo contains an unsupported character")

        stripped = part.rstrip(" .")
        if not stripped:
            raise UnsupportedPathError("path_in_repo contains an illegal path segment")
        if stripped.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise UnsupportedPathError("path_in_repo uses a reserved platform name")
        safe_parts.append(part)

    return "/".join(safe_parts)


def _validate_ref_name(name: str) -> str:
    """
    Validate and normalize a branch or tag name.

    Ref names share the same safety rules as repo-relative paths so they can be
    mapped directly into the repository directory structure.

    :param name: User-supplied ref name
    :type name: str
    :return: Normalized ref name
    :rtype: str
    :raises UnsupportedPathError: Raised when the ref name violates repository
        naming rules.

    Example::

        >>> _validate_ref_name("release/v1")
        'release/v1'
    """

    if not REF_NAME_PATTERN.fullmatch(name or ""):
        raise UnsupportedPathError("invalid ref name")
    normalized = _normalize_repo_path(name)
    return normalized


def _split_object_id(object_id: str) -> Tuple[str, str]:
    """
    Split a repository object ID into algorithm and digest parts.

    :param object_id: Object identifier such as ``sha256:<digest>``
    :type object_id: str
    :return: Two-tuple of algorithm and digest
    :rtype: Tuple[str, str]
    :raises IntegrityError: Raised when the object ID is malformed or uses an
        unsupported hash scheme.

    Example::

        >>> _split_object_id("sha256:abc123")
        ('sha256', 'abc123')
    """

    try:
        algorithm, digest = object_id.split(":", 1)
    except ValueError:
        raise IntegrityError("invalid object id format")
    if algorithm != OBJECT_HASH or not digest:
        raise IntegrityError("unsupported object id")
    return algorithm, digest


def _object_id_from_container(container: object) -> Tuple[str, bytes]:
    """
    Compute the repository object ID for a serialized container.

    The object ID is derived from canonical container bytes rather than only the
    logical payload so stored metadata is part of integrity verification.

    :param container: Canonical object container payload
    :type container: object
    :return: Tuple of object ID and serialized bytes
    :rtype: Tuple[str, bytes]

    Example::

        >>> object_id, payload = _object_id_from_container({"payload": 1})
        >>> object_id.startswith("sha256:")
        True
        >>> isinstance(payload, bytes)
        True
    """

    container_bytes = _stable_json_bytes(container)
    return OBJECT_HASH + ":" + _sha256_hex(container_bytes), container_bytes


def _build_object_container(object_type: str, payload: object) -> Tuple[str, bytes]:
    """
    Wrap an object payload in the repository container format.

    The wrapper records both object kind and the payload checksum so later reads
    can verify a stored object belongs to the expected logical collection.

    :param object_type: Logical object type name
    :type object_type: str
    :param payload: Logical payload to embed
    :type payload: object
    :return: Tuple of object ID and serialized container bytes
    :rtype: Tuple[str, bytes]

    Example::

        >>> object_id, container = _build_object_container("tree", {"entries": []})
        >>> object_id.startswith("sha256:")
        True
        >>> isinstance(container, bytes)
        True
    """

    payload_bytes = _stable_json_bytes(payload)
    container = {
        "format_version": FORMAT_VERSION,
        "object_type": object_type,
        "payload_sha256": OBJECT_HASH + ":" + _sha256_hex(payload_bytes),
        "payload": payload,
    }
    return _object_id_from_container(container)


class _WriteLock(object):
    """
    Small lock-handle wrapper for repository write locks.

    Instances are created by :meth:`_RepositoryBackend._acquire_write_lock` and
    encapsulate the filesystem paths that must be removed when the writer is
    done.

    Example::

        >>> lock = _WriteLock(Path("/tmp/lock"), Path("/tmp/lock/owner.json"))
        >>> isinstance(lock, _WriteLock)
        True
    """

    def __init__(self, lock_dir: Path, owner_path: Path):
        """
        Initialize the lock handle.

        :param lock_dir: Lock directory path
        :type lock_dir: pathlib.Path
        :param owner_path: Diagnostic owner metadata path
        :type owner_path: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> lock = _WriteLock(Path("/tmp/lock"), Path("/tmp/lock/owner.json"))
            >>> isinstance(lock, _WriteLock)
            True
        """

        self._lock_dir = lock_dir
        self._owner_path = owner_path

    def release(self) -> None:
        """
        Release the write lock and remove its diagnostic files.

        :return: ``None``.
        :rtype: None

        Example::

            >>> lock = _WriteLock(Path("/tmp/lock"), Path("/tmp/lock/owner.json"))  # doctest: +SKIP
            >>> lock.release()  # doctest: +SKIP
        """

        if self._owner_path.exists():
            self._owner_path.unlink()
        if self._lock_dir.exists():
            self._lock_dir.rmdir()


class _RepositoryBackend(object):
    """
    Internal repository backend for the MVP.

    This backend owns the on-disk format, object storage, revision resolution,
    detached read views, and transaction lifecycle used by
    :class:`hubvault.api.HubVaultApi`.

    Example::

        >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
        >>> isinstance(backend, _RepositoryBackend)
        True
    """

    def __init__(self, repo_path: Path):
        """
        Initialize the repository backend for a root directory.

        :param repo_path: Filesystem path to the repository root
        :type repo_path: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._repo_path.as_posix().endswith("demo-repo")
            True
        """

        self._repo_path = Path(repo_path)

    def create_repo(
        self,
        default_branch: str = DEFAULT_BRANCH,
        exist_ok: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> RepoInfo:
        """
        Create a repository at the configured root path.

        This method bootstraps the self-contained on-disk layout, writes the
        format marker and repository configuration, and initializes the default
        branch as an empty ref.

        :param default_branch: Default branch name to create, defaults to
            :data:`DEFAULT_BRANCH`
        :type default_branch: str, optional
        :param exist_ok: Whether an existing repository may be reused,
            defaults to ``False``
        :type exist_ok: bool, optional
        :param metadata: Optional repository metadata persisted in
            ``repo.json``
        :type metadata: Optional[Dict[str, str]], optional
        :return: Public metadata for the created or reused repository
        :rtype: RepoInfo
        :raises RepoAlreadyExistsError: Raised when the target path already
            contains a repository or any non-empty directory.
        :raises UnsupportedPathError: Raised when ``default_branch`` violates
            repository ref naming rules.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     info = backend.create_repo(metadata={"owner": "demo"})
            ...     info.default_branch
            'main'
        """

        default_branch = _validate_ref_name(default_branch)
        metadata = metadata or {}

        if self._is_repo():
            if not exist_ok:
                raise RepoAlreadyExistsError("repository already exists")
            return self.repo_info()

        if self._repo_path.exists():
            entries = list(self._repo_path.iterdir())
            if entries:
                raise RepoAlreadyExistsError("target path is not empty")
        else:
            self._repo_path.mkdir(parents=True)

        self._ensure_layout()
        _write_text_atomic(self._format_path, FORMAT_MARKER + "\n")
        _write_json_atomic(
            self._repo_config_path,
            {
                "format_version": FORMAT_VERSION,
                "default_branch": default_branch,
                "object_hash": OBJECT_HASH,
                "file_mode": "whole-blob-first",
                "large_file_threshold": LARGE_FILE_THRESHOLD,
                "metadata": metadata,
            },
        )
        self._write_ref(default_branch, None)
        return self.repo_info()

    def repo_info(self, revision: Optional[str] = None) -> RepoInfo:
        """
        Return repository metadata for the selected revision.

        The selected revision is only used to resolve the visible ``head`` in
        the returned :class:`RepoInfo`; repository-wide settings still come from
        ``repo.json``.

        :param revision: Revision whose head should be resolved, defaults to the
            configured default branch
        :type revision: Optional[str], optional
        :return: Current repository metadata view
        :rtype: RepoInfo
        :raises RepoNotFoundError: Raised when the configured root is not a
            valid repository.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.repo_info().default_branch
            'main'
        """

        self._ensure_repo()
        self._recover_transactions()

        config = self._repo_config()
        selected_revision = revision or config["default_branch"]
        head = self._resolve_revision(selected_revision, allow_empty_ref=True)
        return RepoInfo(
            repo_path=str(self._repo_path),
            format_version=int(config["format_version"]),
            default_branch=str(config["default_branch"]),
            head=head,
            refs=self._list_refs(),
        )

    def create_commit(
        self,
        revision: str,
        operations: Sequence[object],
        parent_commit: Optional[str] = None,
        expected_head: Optional[str] = None,
        commit_message: str = "",
        metadata: Optional[Dict[str, str]] = None,
    ) -> CommitInfo:
        """
        Create a new commit on a branch revision.

        The backend stages all new objects in a transaction directory, publishes
        them atomically, and only then updates the branch ref and reflog.

        :param revision: Branch name that will receive the new commit
        :type revision: str
        :param operations: Add, delete, or copy operations to apply
        :type operations: Sequence[object]
        :param parent_commit: Optional expected parent commit for optimistic
            concurrency checks
        :type parent_commit: Optional[str], optional
        :param expected_head: Optional explicit expected branch head
        :type expected_head: Optional[str], optional
        :param commit_message: Commit message to store in commit metadata
        :type commit_message: str, optional
        :param metadata: Optional commit metadata persisted in the commit object
        :type metadata: Optional[Dict[str, str]], optional
        :return: Public metadata for the created commit
        :rtype: CommitInfo
        :raises ConflictError: Raised when no operations are supplied, an
            unsupported operation is provided, or optimistic concurrency checks
            fail.
        :raises LockTimeoutError: Raised when another writer currently holds the
            repository write lock.
        :raises PathNotFoundError: Raised when delete or copy operations refer
            to missing paths.
        :raises RevisionNotFoundError: Raised when the target revision cannot be
            resolved.
        :raises UnsupportedPathError: Raised when revision names or repo paths
            are invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     commit = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     commit.revision
            'main'
        """

        self._ensure_repo()
        self._recover_transactions()
        if not operations:
            raise ConflictError("operations must not be empty")

        branch_name = _validate_ref_name(revision)
        metadata = metadata or {}

        lock = self._acquire_write_lock()
        txdir = self._create_txdir(branch_name, expected_head or parent_commit)
        try:
            current_head = self._read_ref(branch_name)
            expected = self._resolve_expected_head(parent_commit, expected_head)
            if expected != current_head:
                raise ConflictError("expected head does not match current branch head")

            snapshot = self._snapshot_for_commit(current_head)
            staged_snapshot = dict(snapshot)
            source_snapshots = {None: dict(snapshot)}

            for operation in operations:
                if isinstance(operation, CommitOperationAdd):
                    normalized_path = _normalize_repo_path(operation.path_in_repo)
                    _, file_object_id, _ = self._stage_add_operation(txdir, operation)
                    staged_snapshot[normalized_path] = file_object_id
                elif isinstance(operation, CommitOperationDelete):
                    self._apply_delete(staged_snapshot, operation.path_in_repo, operation.is_folder)
                elif isinstance(operation, CommitOperationCopy):
                    source_snapshot = source_snapshots.get(operation.src_revision)
                    if source_snapshot is None:
                        source_snapshot = self._snapshot_for_revision(operation.src_revision)
                        source_snapshots[operation.src_revision] = dict(source_snapshot)
                    self._apply_copy(
                        staged_snapshot,
                        source_snapshot,
                        operation.src_path_in_repo,
                        operation.path_in_repo,
                    )
                else:
                    raise ConflictError("unsupported commit operation")

            self._validate_snapshot(staged_snapshot)
            tree_id = self._stage_tree_objects(txdir, staged_snapshot)
            commit_payload = {
                "format_version": FORMAT_VERSION,
                "tree_id": tree_id,
                "parents": [current_head] if current_head else [],
                "author": "",
                "committer": "",
                "created_at": _utc_now(),
                "message": commit_message,
                "metadata": metadata,
            }
            commit_id = self._stage_json_object(txdir, "commits", commit_payload)

            self._write_tx_state(txdir, "STAGED")
            self._publish_staged_objects(txdir)
            self._write_tx_state(txdir, "PUBLISHED_OBJECTS")
            self._write_ref(branch_name, commit_id)
            self._write_tx_state(txdir, "UPDATED_REF")
            self._append_reflog(branch_name, current_head, commit_id, commit_message)
            self._write_tx_state(txdir, "COMMITTED")

            return CommitInfo(
                commit_id=commit_id,
                revision=branch_name,
                tree_id=tree_id,
                parents=[current_head] if current_head else [],
                message=commit_message,
            )
        finally:
            self._cleanup_txdir(txdir)
            lock.release()

    def get_paths_info(
        self,
        paths: Sequence[str],
        revision: str = DEFAULT_BRANCH,
    ) -> List[PathInfo]:
        """
        Return public metadata for the requested paths.

        This method accepts both file paths and logical directory paths. A
        directory is reported when the requested prefix exists transitively in
        the flattened snapshot even if there is no explicit tree entry exposed
        through the public API.

        :param paths: Repo-relative paths to inspect
        :type paths: Sequence[str]
        :param revision: Revision to resolve, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Path metadata in the same order as ``paths``
        :rtype: List[PathInfo]
        :raises PathNotFoundError: Raised when any requested path is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when any supplied path is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.get_paths_info(["nested", "nested/demo.txt"])[0].path_type
            'directory'
        """

        snapshot = self._snapshot_for_revision(revision)
        infos = []
        for raw_path in paths:
            normalized_path = _normalize_repo_path(raw_path)
            if normalized_path in snapshot:
                infos.append(self._path_info_for_file(normalized_path, snapshot[normalized_path]))
                continue

            prefix = normalized_path + "/"
            if any(path.startswith(prefix) for path in snapshot):
                infos.append(
                    PathInfo(
                        path=normalized_path,
                        path_type="directory",
                        size=0,
                        oid=None,
                        blob_id=None,
                        sha256=None,
                        etag=None,
                    )
                )
                continue
            raise PathNotFoundError("path not found: %s" % normalized_path)
        return infos

    def list_repo_tree(self, path_in_repo: str = "", revision: str = DEFAULT_BRANCH) -> List[PathInfo]:
        """
        List direct children under a repository directory.

        The returned list only contains the direct child names for the selected
        directory, not a recursive traversal of the whole tree.

        :param path_in_repo: Repo-relative directory path, or ``""`` for the
            repository root
        :type path_in_repo: str, optional
        :param revision: Revision to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Sorted metadata entries for direct children
        :rtype: List[PathInfo]
        :raises PathNotFoundError: Raised when the requested directory does not
            exist.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``path_in_repo`` points to a
            file or violates path rules.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     [item.path for item in backend.list_repo_tree("nested")]
            ['nested/demo.txt']
        """

        snapshot = self._snapshot_for_revision(revision)
        if not path_in_repo:
            prefix = ""
            base = ""
        else:
            base = _normalize_repo_path(path_in_repo)
            if base in snapshot:
                raise UnsupportedPathError("path_in_repo must refer to a directory")
            prefix = base + "/"
            if not any(path.startswith(prefix) for path in snapshot):
                raise PathNotFoundError("directory not found: %s" % base)

        items = {}
        for repo_path, file_object_id in snapshot.items():
            if base:
                if not repo_path.startswith(prefix):
                    continue
                remainder = repo_path[len(prefix):]
            else:
                remainder = repo_path
            head, _, tail = remainder.partition("/")
            full_path = head if not base else base + "/" + head
            if tail:
                items.setdefault(
                    full_path,
                    PathInfo(
                        path=full_path,
                        path_type="directory",
                        size=0,
                        oid=None,
                        blob_id=None,
                        sha256=None,
                        etag=None,
                    ),
                )
            else:
                items[full_path] = self._path_info_for_file(full_path, file_object_id)
        return [items[key] for key in sorted(items)]

    def list_repo_files(self, revision: str = DEFAULT_BRANCH) -> List[str]:
        """
        List all file paths in a revision.

        The result is a flattened, sorted list of repo-relative file paths and
        intentionally omits directory placeholders.

        :param revision: Revision to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Sorted repo-relative file paths
        :rtype: List[str]
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.list_repo_files()
            ['demo.txt']
        """

        snapshot = self._snapshot_for_revision(revision)
        return sorted(snapshot)

    def list_repo_commits(
        self,
        revision: str = DEFAULT_BRANCH,
        formatted: bool = False,
    ) -> List[GitCommitInfo]:
        """
        List commit entries reachable from a revision head.

        The public method name and the meaningful parameters intentionally match
        :meth:`huggingface_hub.HfApi.list_repo_commits` as closely as the local
        repository design allows. The local API omits remote-only parameters
        such as ``repo_id``, ``repo_type``, and ``token`` because they have no
        real behavior for an embedded on-disk repository.

        The MVP currently produces linear history only, so the returned list is
        ordered from the selected head commit back through its first-parent
        chain until the root commit.

        :param revision: Revision or commit ID to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :param formatted: Whether HTML-formatted title/message fields should be
            populated
        :type formatted: bool, optional
        :return: Commit entries ordered from newest to oldest
        :rtype: List[GitCommitInfo]
        :raises RepoNotFoundError: Raised when the configured root is not a
            valid repository.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     commit = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     history = backend.list_repo_commits()
            ...     history[0].title
            'seed'
        """

        self._ensure_repo()
        self._recover_transactions()

        head_commit_id = self._resolve_revision(revision, allow_empty_ref=True)
        if head_commit_id is None:
            return []

        commits = []
        seen = set()
        current_commit_id = head_commit_id
        while current_commit_id is not None and current_commit_id not in seen:
            seen.add(current_commit_id)
            info = self._git_commit_info(current_commit_id, formatted=formatted)
            commits.append(info)
            commit_payload = self._read_object_payload("commits", current_commit_id)
            parents = list(commit_payload.get("parents", []))
            current_commit_id = str(parents[0]) if parents else None
        return commits

    def open_file(self, path_in_repo: str, revision: str = DEFAULT_BRANCH) -> io.BufferedReader:
        """
        Open a file from a revision as a read-only binary stream.

        The returned stream is detached from repository storage and backed by an
        in-memory buffer, so accidental writes through the stream cannot mutate
        repository truth.

        :param path_in_repo: Repo-relative file path to open
        :type path_in_repo: str
        :param revision: Revision to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Read-only buffered binary stream
        :rtype: io.BufferedReader
        :raises PathNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     with backend.open_file("demo.txt") as fileobj:
            ...         fileobj.read()
            b'hello'
        """

        data = self.read_bytes(path_in_repo, revision=revision)
        return io.BufferedReader(io.BytesIO(data))

    def read_bytes(self, path_in_repo: str, revision: str = DEFAULT_BRANCH) -> bytes:
        """
        Read a file from a revision into memory.

        File bytes are verified against the stored blob checksum before being
        returned so corruption in detached storage is surfaced immediately.

        :param path_in_repo: Repo-relative file path to read
        :type path_in_repo: str
        :param revision: Revision to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Full file content bytes
        :rtype: bytes
        :raises IntegrityError: Raised when persisted blob bytes do not match
            recorded checksums.
        :raises PathNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.read_bytes("demo.txt")
            b'hello'
        """

        snapshot = self._snapshot_for_revision(revision)
        normalized_path = _normalize_repo_path(path_in_repo)
        try:
            file_object_id = snapshot[normalized_path]
        except KeyError:
            raise PathNotFoundError("path not found: %s" % normalized_path)
        file_payload = self._read_object_payload("files", file_object_id)
        blob_object_id = file_payload["content_object_id"]
        blob_meta = self._read_object_payload("blobs", blob_object_id)
        blob_data_path = self._blob_data_path(blob_object_id)
        data = blob_data_path.read_bytes()
        data_sha256 = OBJECT_HASH + ":" + _sha256_hex(data)
        if data_sha256 != blob_meta["payload_sha256"]:
            raise IntegrityError("blob payload checksum mismatch")
        return data

    def hf_hub_download(
        self,
        filename: str,
        revision: Optional[str] = None,
        local_dir: Optional[str] = None,
    ) -> str:
        """
        Materialize a detached user view for a file and return its path.

        The detached path preserves the repo-relative filename suffix, including
        parent directories, so callers can work with a normal-looking filesystem
        path while repository truth remains immutable until explicit commit APIs
        are used.

        :param filename: Repo-relative file path to materialize
        :type filename: str
        :param revision: Revision to inspect, defaults to the default branch
        :type revision: Optional[str], optional
        :param local_dir: Optional external target root for the detached view
        :type local_dir: Optional[str], optional
        :return: Filesystem path to a detached readable file view
        :rtype: str
        :raises PathNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``filename`` is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     path = backend.hf_hub_download("nested/demo.txt")
            ...     path.endswith("nested/demo.txt")
            True
        """

        resolved_revision = revision or DEFAULT_BRANCH
        normalized_path = _normalize_repo_path(filename)
        snapshot = self._snapshot_for_revision(resolved_revision)
        try:
            file_object_id = snapshot[normalized_path]
        except KeyError:
            raise PathNotFoundError("path not found: %s" % normalized_path)

        file_payload = self._read_object_payload("files", file_object_id)
        data = self.read_bytes(normalized_path, revision=resolved_revision)
        self._materialize_content_pool(file_payload, data)

        if local_dir is not None:
            target_root = Path(local_dir)
            target_path = target_root / normalized_path
            self._ensure_detached_view(target_path, data, file_payload)
            return str(target_path)

        resolved_head = self._resolve_revision(resolved_revision)
        view_key = _sha256_hex(((resolved_head or "") + ":" + normalized_path).encode("utf-8"))
        view_root = self._repo_path / "cache" / "files" / view_key
        target_path = view_root / normalized_path
        self._ensure_detached_view(target_path, data, file_payload)
        _write_json_atomic(
            self._repo_path / "cache" / "views" / "files" / (view_key + ".json"),
            {
                "view_key": view_key,
                "revision": resolved_revision,
                "path_in_repo": normalized_path,
                "sha256": _public_sha256_hex(str(file_payload["sha256"])),
                "oid": file_payload["oid"],
                "target_path": str(target_path.relative_to(self._repo_path)),
                "created_at": _utc_now(),
            },
        )
        return str(target_path)

    def reset_ref(self, ref_name: str, to_revision: str) -> CommitInfo:
        """
        Reset a branch ref to a target commit.

        This method performs a branch-head move under the repository write lock
        and records the change in the reflog.

        :param ref_name: Branch name to update
        :type ref_name: str
        :param to_revision: Revision or commit ID to resolve as the new head
        :type to_revision: str
        :return: Public commit metadata for the new branch head
        :rtype: CommitInfo
        :raises LockTimeoutError: Raised when another writer already holds the
            repository lock.
        :raises RevisionNotFoundError: Raised when the target revision cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``ref_name`` violates ref
            naming rules.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     commit = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.reset_ref("main", commit.commit_id).commit_id == commit.commit_id
            True
        """

        self._ensure_repo()
        self._recover_transactions()
        branch_name = _validate_ref_name(ref_name)
        target_commit_id = self._resolve_revision(to_revision)
        lock = self._acquire_write_lock()
        txdir = self._create_txdir(branch_name, target_commit_id)
        try:
            old_head = self._read_ref(branch_name)
            self._write_ref(branch_name, target_commit_id)
            self._append_reflog(branch_name, old_head, target_commit_id, "reset ref")
            self._write_tx_state(txdir, "COMMITTED")
        finally:
            self._cleanup_txdir(txdir)
            lock.release()
        return self._commit_info(target_commit_id, branch_name)

    def quick_verify(self) -> VerifyReport:
        """
        Perform a minimal repository consistency check.

        The verification pass checks repository format compatibility, validates
        commit closure for all visible refs, and reports stale detached views as
        warnings instead of fatal errors.

        :return: Verification summary for the current repository state
        :rtype: VerifyReport
        :raises RepoNotFoundError: Raised when the configured root is not a
            valid repository.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = _RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.quick_verify().ok
            True
        """

        self._ensure_repo()
        self._recover_transactions()

        warnings = []
        errors = []
        checked_refs = []
        config = self._repo_config()

        if config.get("format_version") != FORMAT_VERSION:
            errors.append("unsupported format version")

        for ref_name in self._list_branch_names():
            checked_refs.append("refs/heads/" + ref_name)
            head = self._read_ref(ref_name)
            if head is None:
                continue
            try:
                self._verify_commit_closure(head)
            except IntegrityError as err:
                errors.append("refs/heads/%s: %s" % (ref_name, err))

        for ref_name in self._list_tag_names():
            checked_refs.append("refs/tags/" + ref_name)
            head = self._read_tag_ref(ref_name)
            if head is None:
                continue
            try:
                self._verify_commit_closure(head)
            except IntegrityError as err:
                errors.append("refs/tags/%s: %s" % (ref_name, err))

        for view_meta_path in sorted((self._repo_path / "cache" / "views" / "files").glob("*.json")):
            try:
                view_meta = _read_json(view_meta_path)
                target_path = self._repo_path / str(view_meta["target_path"])
                if target_path.exists():
                    data_sha256 = _sha256_hex(target_path.read_bytes())
                    if data_sha256 != _public_sha256_hex(str(view_meta["sha256"])):
                        warnings.append("stale file view: %s" % view_meta_path.name)
            except Exception as err:  # pragma: no cover - defensive path
                warnings.append("failed to inspect file view %s: %s" % (view_meta_path.name, err))

        return VerifyReport(
            ok=not errors,
            checked_refs=checked_refs,
            warnings=warnings,
            errors=errors,
        )

    @property
    def _format_path(self) -> Path:
        """
        Return the repository ``FORMAT`` marker path.

        :return: Absolute path to ``FORMAT``
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._format_path.name
            'FORMAT'
        """

        return self._repo_path / "FORMAT"

    @property
    def _repo_config_path(self) -> Path:
        """
        Return the repository configuration file path.

        :return: Absolute path to ``repo.json``
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._repo_config_path.name
            'repo.json'
        """

        return self._repo_path / "repo.json"

    def _is_repo(self) -> bool:
        """
        Check whether the configured root already looks like a repository.

        :return: Whether the root contains the minimum repository markers
        :rtype: bool

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._is_repo()
            False
        """

        return self._format_path.is_file() and self._repo_config_path.is_file()

    def _ensure_layout(self) -> None:
        """
        Create the required repository directory layout if missing.

        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._ensure_layout()  # doctest: +SKIP
        """

        for relative in [
            "refs/heads",
            "refs/tags",
            "logs/refs/heads",
            "logs/refs/tags",
            "objects/commits/sha256",
            "objects/trees/sha256",
            "objects/files/sha256",
            "objects/blobs/sha256",
            "txn",
            "locks",
            "cache/materialized/sha256",
            "cache/materialized/meta",
            "cache/views/files",
            "cache/views/snapshots",
            "cache/files",
            "cache/snapshots",
            "quarantine/objects",
            "quarantine/packs",
            "quarantine/manifests",
        ]:
            (self._repo_path / relative).mkdir(parents=True, exist_ok=True)

    def _ensure_repo(self) -> None:
        """
        Validate the repository root and ensure cache/layout directories exist.

        :return: ``None``.
        :rtype: None
        :raises RepoNotFoundError: Raised when the root does not contain a valid
            repository marker set.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._ensure_repo()  # doctest: +SKIP
        """

        if not self._is_repo():
            raise RepoNotFoundError("repository not found")
        self._ensure_layout()

    def _repo_config(self) -> Dict[str, object]:
        """
        Load the repository configuration payload.

        :return: Repository configuration mapping
        :rtype: Dict[str, object]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> sorted(backend._repo_config())  # doctest: +SKIP
            ['default_branch', 'file_mode', 'format_version', 'large_file_threshold', 'metadata', 'object_hash']
        """

        return dict(_read_json(self._repo_config_path))

    def _list_refs(self) -> List[str]:
        """
        List all visible branch and tag refs.

        :return: Sorted list of full ref names
        :rtype: List[str]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._list_refs()  # doctest: +SKIP
            []
        """

        refs = []
        refs.extend("refs/heads/" + name for name in self._list_branch_names())
        refs.extend("refs/tags/" + name for name in self._list_tag_names())
        return sorted(refs)

    def _list_branch_names(self) -> List[str]:
        """
        List branch names beneath ``refs/heads``.

        :return: Sorted branch names
        :rtype: List[str]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._list_branch_names()  # doctest: +SKIP
            []
        """

        heads_dir = self._repo_path / "refs" / "heads"
        if not heads_dir.exists():
            return []
        return self._list_ref_names_under(heads_dir)

    def _list_tag_names(self) -> List[str]:
        """
        List tag names beneath ``refs/tags``.

        :return: Sorted tag names
        :rtype: List[str]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._list_tag_names()  # doctest: +SKIP
            []
        """

        tags_dir = self._repo_path / "refs" / "tags"
        if not tags_dir.exists():
            return []
        return self._list_ref_names_under(tags_dir)

    def _list_ref_names_under(self, root: Path) -> List[str]:
        """
        Recursively list file-backed ref names under a root directory.

        :param root: Ref root directory
        :type root: pathlib.Path
        :return: Sorted relative ref names
        :rtype: List[str]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._list_ref_names_under(Path("/tmp/demo-repo/refs/heads"))  # doctest: +SKIP
            []
        """

        names = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            names.append(path.relative_to(root).as_posix())
        return names

    def _ref_path(self, name: str) -> Path:
        """
        Build the branch ref path for a name.

        :param name: Normalized branch name
        :type name: str
        :return: Absolute branch ref path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._ref_path("main").as_posix().endswith("refs/heads/main")
            True
        """

        return self._repo_path / "refs" / "heads" / name

    def _tag_ref_path(self, name: str) -> Path:
        """
        Build the tag ref path for a name.

        :param name: Normalized tag name
        :type name: str
        :return: Absolute tag ref path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._tag_ref_path("v1").as_posix().endswith("refs/tags/v1")
            True
        """

        return self._repo_path / "refs" / "tags" / name

    def _reflog_path(self, name: str) -> Path:
        """
        Build the reflog path for a branch name.

        :param name: Normalized branch name
        :type name: str
        :return: Absolute reflog path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._reflog_path("main").name
            'main.log'
        """

        return self._repo_path / "logs" / "refs" / "heads" / (name + ".log")

    def _write_ref(self, name: str, commit_id: Optional[str]) -> None:
        """
        Persist a branch ref value.

        :param name: Normalized branch name
        :type name: str
        :param commit_id: Commit object ID or ``None`` for an empty ref
        :type commit_id: Optional[str]
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._write_ref("main", None)  # doctest: +SKIP
        """

        path = self._ref_path(name)
        content = "" if commit_id is None else commit_id + "\n"
        _write_text_atomic(path, content)

    def _read_ref(self, name: str) -> Optional[str]:
        """
        Read a branch ref value.

        :param name: Normalized branch name
        :type name: str
        :return: Commit object ID or ``None`` for an empty ref
        :rtype: Optional[str]
        :raises RevisionNotFoundError: Raised when the branch ref does not
            exist.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._read_ref("main")  # doctest: +SKIP
        """

        path = self._ref_path(name)
        if not path.exists():
            raise RevisionNotFoundError("branch not found: %s" % name)
        content = _read_text(path).strip()
        return content or None

    def _read_tag_ref(self, name: str) -> Optional[str]:
        """
        Read a tag ref value.

        :param name: Normalized tag name
        :type name: str
        :return: Commit object ID or ``None`` for an empty ref
        :rtype: Optional[str]
        :raises RevisionNotFoundError: Raised when the tag ref does not exist.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._read_tag_ref("v1")  # doctest: +SKIP
        """

        path = self._tag_ref_path(name)
        if not path.exists():
            raise RevisionNotFoundError("tag not found: %s" % name)
        content = _read_text(path).strip()
        return content or None

    def _resolve_revision(self, revision: str, allow_empty_ref: bool = False) -> Optional[str]:
        """
        Resolve a revision string to a commit object ID.

        :param revision: Branch, tag, full ref, or commit object ID
        :type revision: str
        :param allow_empty_ref: Whether empty refs may resolve to ``None``
        :type allow_empty_ref: bool
        :return: Resolved commit ID or ``None`` for an allowed empty ref
        :rtype: Optional[str]
        :raises RevisionNotFoundError: Raised when the revision cannot be
            resolved.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._resolve_revision("main", allow_empty_ref=True)  # doctest: +SKIP
        """

        if revision.startswith(OBJECT_HASH + ":"):
            self._read_object_payload("commits", revision)
            return revision

        if revision.startswith("refs/heads/"):
            head = self._read_ref(revision.split("/", 2)[-1])
        elif revision.startswith("refs/tags/"):
            head = self._read_tag_ref(revision.split("/", 2)[-1])
        else:
            branch_path = self._ref_path(revision)
            tag_path = self._tag_ref_path(revision)
            if branch_path.exists():
                head = self._read_ref(revision)
            elif tag_path.exists():
                head = self._read_tag_ref(revision)
            else:
                raise RevisionNotFoundError("revision not found: %s" % revision)

        if head is None and not allow_empty_ref:
            raise RevisionNotFoundError("revision has no commits yet: %s" % revision)
        return head

    def _resolve_expected_head(self, parent_commit: Optional[str], expected_head: Optional[str]) -> Optional[str]:
        """
        Merge optimistic-concurrency head expectations.

        :param parent_commit: Expected parent commit
        :type parent_commit: Optional[str]
        :param expected_head: Explicit expected head override
        :type expected_head: Optional[str]
        :return: Effective expected head
        :rtype: Optional[str]
        :raises ConflictError: Raised when both expectations are provided but
            disagree.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._resolve_expected_head("a", None)
            'a'
        """

        if parent_commit is not None and expected_head is not None and parent_commit != expected_head:
            raise ConflictError("parent_commit and expected_head disagree")
        return expected_head if expected_head is not None else parent_commit

    def _object_json_path(self, object_type: str, object_id: str) -> Path:
        """
        Build the JSON object path for a stored object.

        :param object_type: Stored object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Absolute object JSON path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._object_json_path("trees", "sha256:" + "a" * 64).suffix
            '.json'
        """

        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".json"
        return self._repo_path / "objects" / object_type / OBJECT_HASH / prefix / filename

    def _blob_meta_path(self, object_id: str) -> Path:
        """
        Build the metadata path for a blob object.

        :param object_id: Blob object identifier
        :type object_id: str
        :return: Absolute blob metadata path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._blob_meta_path("sha256:" + "a" * 64).name.endswith(".meta.json")
            True
        """

        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".meta.json"
        return self._repo_path / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _blob_data_path(self, object_id: str) -> Path:
        """
        Build the payload data path for a blob object.

        :param object_id: Blob object identifier
        :type object_id: str
        :return: Absolute blob payload path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._blob_data_path("sha256:" + "a" * 64).name.endswith(".data")
            True
        """

        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".data"
        return self._repo_path / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _object_exists(self, object_type: str, object_id: str) -> bool:
        """
        Check whether a published object exists on disk.

        :param object_type: Stored object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Whether the object exists
        :rtype: bool

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._object_exists("trees", "sha256:" + "a" * 64)
            False
        """

        if object_type == "blobs":
            return self._blob_meta_path(object_id).exists() and self._blob_data_path(object_id).exists()
        return self._object_json_path(object_type, object_id).exists()

    def _stage_json_object(self, txdir: Path, object_type: str, payload: object) -> str:
        """
        Stage a JSON-backed object into a transaction directory.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param object_type: Stored object collection name
        :type object_type: str
        :param payload: Logical object payload
        :type payload: object
        :return: Staged object identifier
        :rtype: str

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._stage_json_object(Path("/tmp/demo-repo/txn/demo"), "trees", {"entries": []})  # doctest: +SKIP
        """

        object_id, container_bytes = _build_object_container(object_type[:-1], payload)
        path = self._stage_object_json_path(txdir, object_type, object_id)
        if not path.exists():
            _write_bytes_atomic(path, container_bytes)
        return object_id

    def _stage_blob_object(self, txdir: Path, payload: object, data: bytes) -> str:
        """
        Stage a blob metadata/data pair into a transaction directory.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param payload: Blob metadata payload
        :type payload: object
        :param data: Blob content bytes
        :type data: bytes
        :return: Staged blob object identifier
        :rtype: str

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._stage_blob_object(Path("/tmp/demo-repo/txn/demo"), {"payload_sha256": "sha256:" + "a" * 64}, b"demo")  # doctest: +SKIP
        """

        object_id, container_bytes = _build_object_container("blob", payload)
        meta_path = self._stage_blob_meta_path(txdir, object_id)
        data_path = self._stage_blob_data_path(txdir, object_id)
        if not meta_path.exists():
            _write_bytes_atomic(meta_path, container_bytes)
        if not data_path.exists():
            _write_bytes_atomic(data_path, data)
        return object_id

    def _stage_object_json_path(self, txdir: Path, object_type: str, object_id: str) -> Path:
        """
        Build the staged JSON object path for a transaction.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param object_type: Stored object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Absolute staged JSON object path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._stage_object_json_path(Path("/tmp/demo-repo/txn/demo"), "trees", "sha256:" + "a" * 64).suffix
            '.json'
        """

        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".json"
        return txdir / "objects" / object_type / OBJECT_HASH / prefix / filename

    def _stage_blob_meta_path(self, txdir: Path, object_id: str) -> Path:
        """
        Build the staged blob metadata path for a transaction.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param object_id: Blob object identifier
        :type object_id: str
        :return: Absolute staged blob metadata path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._stage_blob_meta_path(Path("/tmp/demo-repo/txn/demo"), "sha256:" + "a" * 64).name.endswith(".meta.json")
            True
        """

        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".meta.json"
        return txdir / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _stage_blob_data_path(self, txdir: Path, object_id: str) -> Path:
        """
        Build the staged blob data path for a transaction.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param object_id: Blob object identifier
        :type object_id: str
        :return: Absolute staged blob payload path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._stage_blob_data_path(Path("/tmp/demo-repo/txn/demo"), "sha256:" + "a" * 64).name.endswith(".data")
            True
        """

        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".data"
        return txdir / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _read_object_payload(self, object_type: str, object_id: str) -> Dict[str, object]:
        """
        Load the logical payload of a published object.

        :param object_type: Stored object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Decoded logical payload
        :rtype: Dict[str, object]
        :raises RevisionNotFoundError: Raised when the object file is missing.
        :raises IntegrityError: Raised when the stored container is malformed.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._read_object_payload("trees", "sha256:" + "a" * 64)  # doctest: +SKIP
        """

        if object_type == "blobs":
            path = self._blob_meta_path(object_id)
        else:
            path = self._object_json_path(object_type, object_id)
        if not path.exists():
            raise RevisionNotFoundError("object not found: %s" % object_id)
        container = _read_json(path)
        if not isinstance(container, dict) or "payload" not in container:
            raise IntegrityError("invalid object container")
        return dict(container["payload"])

    def _snapshot_for_revision(self, revision: str) -> Dict[str, str]:
        """
        Materialize a flat file snapshot for a revision.

        :param revision: Revision to resolve
        :type revision: str
        :return: Mapping of repo-relative path to file object ID
        :rtype: Dict[str, str]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._snapshot_for_revision("main")  # doctest: +SKIP
        """

        head = self._resolve_revision(revision)
        return self._snapshot_for_commit(head)

    def _snapshot_for_commit(self, commit_id: Optional[str]) -> Dict[str, str]:
        """
        Materialize a flat file snapshot for a commit.

        :param commit_id: Commit object ID or ``None`` for an empty snapshot
        :type commit_id: Optional[str]
        :return: Mapping of repo-relative path to file object ID
        :rtype: Dict[str, str]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._snapshot_for_commit(None)
            {}
        """

        if commit_id is None:
            return {}
        commit_payload = self._read_object_payload("commits", commit_id)
        return self._snapshot_for_tree(str(commit_payload["tree_id"]), prefix="")

    def _snapshot_for_tree(self, tree_id: str, prefix: str) -> Dict[str, str]:
        """
        Recursively flatten a tree object into a path map.

        :param tree_id: Tree object identifier
        :type tree_id: str
        :param prefix: Current path prefix
        :type prefix: str
        :return: Mapping of repo-relative path to file object ID
        :rtype: Dict[str, str]
        :raises IntegrityError: Raised when the tree contains unknown entry
            kinds.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._snapshot_for_tree("sha256:" + "a" * 64, prefix="")  # doctest: +SKIP
        """

        snapshot = {}
        tree_payload = self._read_object_payload("trees", tree_id)
        for entry in tree_payload.get("entries", []):
            name = entry["name"]
            path = name if not prefix else prefix + "/" + name
            if entry["entry_type"] == "file":
                snapshot[path] = entry["object_id"]
            elif entry["entry_type"] == "tree":
                snapshot.update(self._snapshot_for_tree(entry["object_id"], path))
            else:
                raise IntegrityError("unknown tree entry type")
        return snapshot

    def _path_info_for_file(self, path: str, file_object_id: str) -> PathInfo:
        """
        Build public path metadata for a file object.

        :param path: Repo-relative file path
        :type path: str
        :param file_object_id: File object identifier
        :type file_object_id: str
        :return: Public file metadata
        :rtype: PathInfo

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._path_info_for_file("demo.txt", "sha256:" + "a" * 64)  # doctest: +SKIP
        """

        payload = self._read_object_payload("files", file_object_id)
        return PathInfo(
            path=path,
            path_type="file",
            size=int(payload["logical_size"]),
            oid=str(payload["oid"]),
            blob_id=str(payload["oid"]),
            sha256=_public_sha256_hex(str(payload["sha256"])),
            etag=str(payload["etag"]),
        )

    def _stage_add_operation(
        self,
        txdir: Path,
        operation: CommitOperationAdd,
    ) -> Tuple[str, str, Dict[str, object]]:
        """
        Stage the storage objects needed for an add operation.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param operation: Public add operation
        :type operation: CommitOperationAdd
        :return: Tuple of blob ID, file ID, and file payload
        :rtype: Tuple[str, str, Dict[str, object]]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> operation = CommitOperationAdd("demo.txt", b"hello")
            >>> backend._stage_add_operation(Path("/tmp/demo-repo/txn/demo"), operation)  # doctest: +SKIP
        """

        normalized_path = _normalize_repo_path(operation.path_in_repo)
        del normalized_path
        with operation.as_file() as fileobj:
            data = fileobj.read()
        file_sha256_hex = _sha256_hex(data)
        file_sha256 = OBJECT_HASH + ":" + file_sha256_hex
        oid = _git_blob_oid(data)
        blob_payload = {
            "format_version": FORMAT_VERSION,
            "compression": "none",
            "logical_size": len(data),
            "logical_hash": file_sha256,
            "stored_size": len(data),
            "payload_sha256": file_sha256,
        }
        blob_object_id = self._stage_blob_object(txdir, blob_payload, data)
        file_payload = {
            "format_version": FORMAT_VERSION,
            "storage_kind": "blob",
            "logical_size": len(data),
            "sha256": file_sha256_hex,
            "oid": oid,
            "etag": oid,
            "content_type_hint": None,
            "content_object_id": blob_object_id,
            "chunks": [],
        }
        file_object_id = self._stage_json_object(txdir, "files", file_payload)
        return blob_object_id, file_object_id, file_payload

    def _apply_delete(self, snapshot: Dict[str, str], path_in_repo: str, is_folder: bool) -> None:
        """
        Apply a delete operation to a staged snapshot.

        :param snapshot: Mutable snapshot map
        :type snapshot: Dict[str, str]
        :param path_in_repo: Repo-relative file or directory path
        :type path_in_repo: str
        :param is_folder: Whether the delete targets a directory subtree
        :type is_folder: bool
        :return: ``None``.
        :rtype: None
        :raises PathNotFoundError: Raised when the target path is absent.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> snapshot = {"demo.txt": "sha256:" + "a" * 64}
            >>> backend._apply_delete(snapshot, "demo.txt", False)
            >>> snapshot
            {}
        """

        if is_folder and path_in_repo.endswith("/"):
            path_in_repo = path_in_repo[:-1]
        normalized_path = _normalize_repo_path(path_in_repo)
        if is_folder:
            removed = False
            prefix = normalized_path + "/"
            for path in list(snapshot):
                if path.startswith(prefix):
                    del snapshot[path]
                    removed = True
            if not removed:
                raise PathNotFoundError("path not found: %s" % normalized_path)
            return

        try:
            del snapshot[normalized_path]
        except KeyError:
            raise PathNotFoundError("path not found: %s" % normalized_path)

    def _apply_copy(
        self,
        snapshot: Dict[str, str],
        source_snapshot: Dict[str, str],
        src_path_in_repo: str,
        dst_path_in_repo: str,
    ) -> None:
        """
        Apply a copy operation to a staged snapshot.

        :param snapshot: Mutable snapshot map
        :type snapshot: Dict[str, str]
        :param source_snapshot: Source snapshot used for the copy lookup
        :type source_snapshot: Dict[str, str]
        :param src_path_in_repo: Source file or directory path
        :type src_path_in_repo: str
        :param dst_path_in_repo: Destination file or directory path
        :type dst_path_in_repo: str
        :return: ``None``.
        :rtype: None
        :raises PathNotFoundError: Raised when the source path is absent.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> snapshot = {"demo.txt": "sha256:" + "a" * 64}
            >>> backend._apply_copy(snapshot, snapshot, "demo.txt", "copy.txt")
            >>> sorted(snapshot)
            ['copy.txt', 'demo.txt']
        """

        src_path = _normalize_repo_path(src_path_in_repo)
        dst_path = _normalize_repo_path(dst_path_in_repo)

        if src_path in source_snapshot:
            snapshot[dst_path] = source_snapshot[src_path]
            return

        prefix = src_path + "/"
        matches = [(path, object_id) for path, object_id in source_snapshot.items() if path.startswith(prefix)]
        if not matches:
            raise PathNotFoundError("path not found: %s" % src_path)
        for path, object_id in matches:
            suffix = path[len(prefix):]
            snapshot[dst_path + "/" + suffix] = object_id

    def _validate_snapshot(self, snapshot: Dict[str, str]) -> None:
        """
        Validate staged snapshot path invariants.

        :param snapshot: Mutable snapshot map
        :type snapshot: Dict[str, str]
        :return: ``None``.
        :rtype: None
        :raises ConflictError: Raised when file/directory conflicts or
            case-folding collisions are detected.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._validate_snapshot({"demo.txt": "sha256:" + "a" * 64})
        """

        seen_per_dir = {}
        sorted_paths = sorted(snapshot)
        for path in sorted_paths:
            parts = path.split("/")
            for index in range(1, len(parts)):
                prefix = "/".join(parts[:index])
                if prefix in snapshot:
                    raise ConflictError("file and directory paths conflict")

            parent = "/".join(parts[:-1])
            key = parent
            seen_per_dir.setdefault(key, {})
            folded = parts[-1].casefold()
            if folded in seen_per_dir[key] and seen_per_dir[key][folded] != parts[-1]:
                raise ConflictError("case-insensitive path conflict")
            seen_per_dir[key][folded] = parts[-1]

    def _stage_tree_objects(self, txdir: Path, snapshot: Dict[str, str]) -> str:
        """
        Stage tree objects for a flat snapshot.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param snapshot: Flat snapshot map
        :type snapshot: Dict[str, str]
        :return: Root tree object identifier
        :rtype: str

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._stage_tree_objects(Path("/tmp/demo-repo/txn/demo"), {"demo.txt": "sha256:" + "a" * 64})  # doctest: +SKIP
        """

        nested = {}
        for path, file_object_id in snapshot.items():
            current = nested
            parts = path.split("/")
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = file_object_id

        return self._stage_tree_node(txdir, nested)

    def _stage_tree_node(self, txdir: Path, node: Dict[str, object]) -> str:
        """
        Recursively stage a nested tree node structure.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param node: Nested directory structure
        :type node: Dict[str, object]
        :return: Tree object identifier
        :rtype: str

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._stage_tree_node(Path("/tmp/demo-repo/txn/demo"), {"nested": {}, "demo.txt": "sha256:" + "a" * 64})  # doctest: +SKIP
        """

        entries = []
        for name in sorted(node):
            value = node[name]
            if isinstance(value, dict):
                tree_object_id = self._stage_tree_node(txdir, value)
                entries.append(
                    {
                        "name": name,
                        "entry_type": "tree",
                        "object_id": tree_object_id,
                        "mode": "040000",
                        "size_hint": 0,
                    }
                )
            else:
                file_payload = self._read_staged_or_published_file_payload(txdir, value)
                entries.append(
                    {
                        "name": name,
                        "entry_type": "file",
                        "object_id": value,
                        "mode": "100644",
                        "size_hint": int(file_payload["logical_size"]),
                    }
                )
        tree_payload = {
            "format_version": FORMAT_VERSION,
            "entries": entries,
        }
        return self._stage_json_object(txdir, "trees", tree_payload)

    def _read_staged_or_published_file_payload(self, txdir: Path, object_id: str) -> Dict[str, object]:
        """
        Read a file payload from staged or already-published storage.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param object_id: File object identifier
        :type object_id: str
        :return: File payload mapping
        :rtype: Dict[str, object]

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._read_staged_or_published_file_payload(Path("/tmp/demo-repo/txn/demo"), "sha256:" + "a" * 64)  # doctest: +SKIP
        """

        staged_path = self._stage_object_json_path(txdir, "files", object_id)
        if staged_path.exists():
            return dict(_read_json(staged_path)["payload"])
        return self._read_object_payload("files", object_id)

    def _publish_staged_objects(self, txdir: Path) -> None:
        """
        Publish staged transaction objects into the repository object store.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when a staged object conflicts with an
            existing published object.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._publish_staged_objects(Path("/tmp/demo-repo/txn/demo"))  # doctest: +SKIP
        """

        staged_root = txdir / "objects"
        if not staged_root.exists():
            return
        for path in sorted(staged_root.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(staged_root)
            target = self._repo_path / "objects" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if path.read_bytes() != target.read_bytes():
                    raise IntegrityError("staged object does not match existing object")
                path.unlink()
                continue
            os.replace(str(path), str(target))

    def _commit_info(self, commit_id: str, revision: str) -> CommitInfo:
        """
        Build public commit metadata for an existing commit.

        :param commit_id: Commit object identifier
        :type commit_id: str
        :param revision: Revision name associated with the commit
        :type revision: str
        :return: Public commit metadata
        :rtype: CommitInfo

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._commit_info("sha256:" + "a" * 64, "main")  # doctest: +SKIP
        """

        commit_payload = self._read_object_payload("commits", commit_id)
        return CommitInfo(
            commit_id=commit_id,
            revision=revision,
            tree_id=str(commit_payload["tree_id"]),
            parents=list(commit_payload.get("parents", [])),
            message=str(commit_payload.get("message", "")),
        )

    def _git_commit_info(self, commit_id: str, formatted: bool = False) -> GitCommitInfo:
        """
        Build HF-style commit listing metadata for an existing commit.

        :param commit_id: Commit object identifier
        :type commit_id: str
        :param formatted: Whether HTML-formatted title/message fields should be
            populated
        :type formatted: bool, optional
        :return: HF-style commit metadata
        :rtype: GitCommitInfo

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._git_commit_info("sha256:" + "a" * 64)  # doctest: +SKIP
        """

        commit_payload = self._read_object_payload("commits", commit_id)
        raw_message = str(commit_payload.get("message", ""))
        title, message = self._split_commit_message(raw_message)
        created_at = datetime.strptime(str(commit_payload["created_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )

        formatted_title = None
        formatted_message = None
        if formatted:
            formatted_title = html_escape(title).replace("\n", "<br />\n")
            formatted_message = html_escape(message).replace("\n", "<br />\n")

        return GitCommitInfo(
            commit_id=commit_id,
            authors=[],
            created_at=created_at,
            title=title,
            message=message,
            formatted_title=formatted_title,
            formatted_message=formatted_message,
        )

    @staticmethod
    def _split_commit_message(message: str) -> Tuple[str, str]:
        """
        Split a stored commit message into title and body segments.

        :param message: Raw stored commit message
        :type message: str
        :return: Two-tuple of title and body message
        :rtype: Tuple[str, str]

        Example::

            >>> _RepositoryBackend._split_commit_message("title\\n\\nbody")
            ('title', 'body')
        """

        lines = str(message).splitlines()
        if not lines:
            return "", ""
        title = lines[0]
        body = "\n".join(lines[1:]).lstrip("\n")
        return title, body

    def _verify_commit_closure(self, commit_id: str) -> None:
        """
        Verify commit reachability and the transitive closure of parent links.

        :param commit_id: Commit object identifier
        :type commit_id: str
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when the commit closure cannot be read or
            validated.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._verify_commit_closure("sha256:" + "a" * 64)  # doctest: +SKIP
        """

        visited = set()
        pending = [commit_id]

        while pending:
            current_commit_id = pending.pop()
            if current_commit_id in visited:
                continue
            visited.add(current_commit_id)
            try:
                commit_payload = self._read_object_payload("commits", current_commit_id)
                tree_id = str(commit_payload["tree_id"])
                self._verify_tree(tree_id)
                pending.extend(str(parent_id) for parent_id in commit_payload.get("parents", []))
            except (FileNotFoundError, KeyError, TypeError, ValueError, RevisionNotFoundError) as err:
                raise IntegrityError("invalid commit closure at %s: %s" % (current_commit_id, err))

    def _verify_tree(self, tree_id: str) -> None:
        """
        Verify a tree object and all referenced descendants.

        :param tree_id: Tree object identifier
        :type tree_id: str
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when the tree or any descendant entry is
            invalid.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._verify_tree("sha256:" + "a" * 64)  # doctest: +SKIP
        """

        try:
            tree_payload = self._read_object_payload("trees", tree_id)
            for entry in tree_payload.get("entries", []):
                entry_type = entry["entry_type"]
                object_id = entry["object_id"]
                if entry_type == "file":
                    self._verify_file_object(object_id)
                elif entry_type == "tree":
                    self._verify_tree(object_id)
                else:
                    raise IntegrityError("unknown tree entry type")
        except (FileNotFoundError, KeyError, TypeError, ValueError, RevisionNotFoundError) as err:
            raise IntegrityError("invalid tree %s: %s" % (tree_id, err))

    def _verify_file_object(self, file_object_id: str) -> None:
        """
        Verify a file object and its referenced blob content.

        :param file_object_id: File object identifier
        :type file_object_id: str
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when file metadata, blob metadata, or
            blob content is inconsistent.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._verify_file_object("sha256:" + "a" * 64)  # doctest: +SKIP
        """

        try:
            payload = self._read_object_payload("files", file_object_id)
            blob_object_id = str(payload["content_object_id"])
            blob_payload = self._read_object_payload("blobs", blob_object_id)
            data_path = self._blob_data_path(blob_object_id)
            if not data_path.exists():
                raise IntegrityError("blob data missing")
            data = data_path.read_bytes()
            data_sha256 = OBJECT_HASH + ":" + _sha256_hex(data)
            if data_sha256 != _integrity_sha256(str(payload["sha256"])):
                raise IntegrityError("file sha256 mismatch")
            if data_sha256 != blob_payload["payload_sha256"]:
                raise IntegrityError("blob payload sha256 mismatch")
            if _git_blob_oid(data) != payload["oid"]:
                raise IntegrityError("file oid mismatch")
        except (FileNotFoundError, KeyError, TypeError, ValueError, RevisionNotFoundError) as err:
            raise IntegrityError("invalid file object %s: %s" % (file_object_id, err))

    def _acquire_write_lock(self) -> _WriteLock:
        """
        Acquire the repository's single-writer lock.

        :return: Lock handle that must be released by the caller
        :rtype: _WriteLock
        :raises LockTimeoutError: Raised when another writer already holds the
            lock.

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> lock = backend._acquire_write_lock()  # doctest: +SKIP
            >>> lock.release()  # doctest: +SKIP
        """

        lock_dir = self._repo_path / "locks" / WRITE_LOCK_DIR
        owner_path = lock_dir / "owner.json"
        try:
            lock_dir.mkdir()
        except FileExistsError:
            raise LockTimeoutError("write lock is already held")
        _write_json_atomic(
            owner_path,
            {
                "pid": os.getpid(),
                "hostname": os.environ.get("HOSTNAME") or os.environ.get("COMPUTERNAME") or "",
                "started_at": _utc_now(),
                "heartbeat_at": _utc_now(),
            },
        )
        return _WriteLock(lock_dir=lock_dir, owner_path=owner_path)

    def _create_txdir(self, revision: str, expected_head: Optional[str]) -> Path:
        """
        Create a new transaction working directory.

        :param revision: Target revision for the transaction
        :type revision: str
        :param expected_head: Expected branch head for optimistic concurrency
        :type expected_head: Optional[str]
        :return: Absolute transaction directory path
        :rtype: pathlib.Path

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._create_txdir("main", None)  # doctest: +SKIP
        """

        txid = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        txdir = self._repo_path / "txn" / txid
        txdir.mkdir(parents=True, exist_ok=False)
        _write_json_atomic(
            txdir / "meta.json",
            {
                "txid": txid,
                "revision": revision,
                "expected_head": expected_head,
                "created_at": _utc_now(),
            },
        )
        self._write_tx_state(txdir, "PREPARING")
        return txdir

    def _write_tx_state(self, txdir: Path, state: str) -> None:
        """
        Persist the current transaction state marker.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param state: Transaction state label
        :type state: str
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._write_tx_state(Path("/tmp/demo-repo/txn/demo"), "PREPARING")  # doctest: +SKIP
        """

        _write_json_atomic(txdir / "STATE.json", {"state": state, "updated_at": _utc_now()})

    def _cleanup_txdir(self, txdir: Path) -> None:
        """
        Remove a transaction directory if it still exists.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._cleanup_txdir(Path("/tmp/demo-repo/txn/demo"))  # doctest: +SKIP
        """

        if txdir.exists():
            shutil.rmtree(str(txdir))

    def _recover_transactions(self) -> None:
        """
        Remove abandoned transaction directories from previous interrupted work.

        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._recover_transactions()  # doctest: +SKIP
        """

        txn_root = self._repo_path / "txn"
        if not txn_root.exists():
            return
        for txdir in txn_root.iterdir():
            if not txdir.is_dir():
                continue
            shutil.rmtree(str(txdir))

    def _append_reflog(
        self,
        revision: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
    ) -> None:
        """
        Append a reflog record for a branch update.

        :param revision: Branch name
        :type revision: str
        :param old_head: Previous head commit
        :type old_head: Optional[str]
        :param new_head: New head commit
        :type new_head: Optional[str]
        :param message: Short reflog message
        :type message: str
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._append_reflog("main", None, "sha256:" + "a" * 64, "seed")  # doctest: +SKIP
        """

        path = self._reflog_path(revision)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": _utc_now(),
            "ref_name": "refs/heads/" + revision,
            "old_head": old_head,
            "new_head": new_head,
            "message": message,
            "checksum": OBJECT_HASH + ":" + _sha256_hex(_stable_json_bytes([old_head, new_head, message])),
        }
        with path.open("a", encoding="utf-8") as file_:
            file_.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            file_.write("\n")

    def _materialize_content_pool(self, file_payload: Dict[str, object], data: bytes) -> None:
        """
        Materialize content into the repository's deduplicated cache pool.

        :param file_payload: Public file payload metadata
        :type file_payload: Dict[str, object]
        :param data: Logical file content
        :type data: bytes
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._materialize_content_pool({"sha256": "a" * 64, "oid": "b" * 40, "logical_size": 4}, b"demo")  # doctest: +SKIP
        """

        content_key = _public_sha256_hex(str(file_payload["sha256"]))
        pool_path = self._repo_path / "cache" / "materialized" / OBJECT_HASH / content_key[:2] / (content_key[2:] + ".data")
        meta_path = self._repo_path / "cache" / "materialized" / "meta" / (content_key + ".json")
        if not pool_path.exists():
            _write_bytes_atomic(pool_path, data)
            try:
                pool_path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            except OSError:  # pragma: no cover - permission semantics vary
                pass
        _write_json_atomic(
            meta_path,
            {
                "content_key": content_key,
                "oid": file_payload["oid"],
                "sha256": content_key,
                "size": file_payload["logical_size"],
                "created_at": _utc_now(),
            },
        )

    def _ensure_detached_view(self, target_path: Path, data: bytes, file_payload: Dict[str, object]) -> None:
        """
        Ensure a detached user-view path matches the requested file content.

        :param target_path: User-visible target path
        :type target_path: pathlib.Path
        :param data: Logical file content
        :type data: bytes
        :param file_payload: Public file payload metadata
        :type file_payload: Dict[str, object]
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = _RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._ensure_detached_view(Path("/tmp/demo-repo/cache/files/demo.txt"), b"demo", {"sha256": "a" * 64})  # doctest: +SKIP
        """

        expected_sha256 = _public_sha256_hex(str(file_payload["sha256"]))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            if target_path.is_symlink():
                target_path.unlink()
            elif target_path.is_dir():
                shutil.rmtree(str(target_path))
            elif target_path.is_file():
                current_sha256 = _sha256_hex(target_path.read_bytes())
                if current_sha256 == expected_sha256:
                    return
                target_path.unlink()
            else:  # pragma: no cover - defensive path for unusual filesystem nodes
                target_path.unlink()
        _write_bytes_atomic(target_path, data)
