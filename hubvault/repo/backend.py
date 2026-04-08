"""
Repository backend for the :mod:`hubvault` MVP.

This module implements the local on-disk repository format used by the MVP.
The backend is intentionally embedded and file-based so the repository remains
self-contained and movable as a normal directory tree.

The module contains:

* :class:`RepositoryBackend` - Internal repository service used by the public API
"""

import io
import json
import os
import re
import secrets
import shutil
import stat
import warnings
from contextlib import contextmanager
from fnmatch import fnmatch
from datetime import datetime, timezone
from html import escape as html_escape
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from fasteners import InterProcessReaderWriterLock

from ..errors import (
    ConflictError,
    EntryNotFoundError,
    IntegrityError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
    VerificationError,
)
from ..models import (
    BlobLfsInfo,
    CommitInfo,
    GcReport,
    GitCommitInfo,
    GitRefInfo,
    GitRefs,
    MergeConflict,
    MergeResult,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    RepoInfo,
    SquashReport,
    StorageOverview,
    StorageSectionInfo,
    VerifyReport,
)
from ..operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete
from ..storage import (
    ChunkStore,
    IndexEntry,
    IndexManifest,
    IndexStore,
    PackChunkLocation,
    PackStore,
    canonical_lfs_pointer,
    git_blob_oid as chunk_git_blob_oid,
)
from .constants import DEFAULT_BRANCH, FORMAT_MARKER, FORMAT_VERSION, LARGE_FILE_THRESHOLD, OBJECT_HASH, REPO_LOCK_FILENAME
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
GC_ANALYSIS_PACK_ID = "gc-0000000000000000-00000000"
GIT_OID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PUBLIC_GIT_AUTHOR_NAME = "HubVault"
PUBLIC_GIT_AUTHOR_EMAIL = "hubvault@local"
FAILPOINT_ENV = "HUBVAULT_FAILPOINT"
FAIL_ACTION_ENV = "HUBVAULT_FAIL_ACTION"
FAILPOINT_EXIT_CODE = 86


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


def _parse_utc_timestamp(value: str) -> datetime:
    """
    Parse a repository UTC timestamp string.

    :param value: Timestamp formatted as ``YYYY-MM-DDTHH:MM:SSZ``
    :type value: str
    :return: Timezone-aware UTC datetime
    :rtype: datetime.datetime

    Example::

        >>> _parse_utc_timestamp("2024-01-01T00:00:00Z").tzinfo == timezone.utc
        True
    """

    return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _fsync_directory(path: Path) -> None:
    """
    Best-effort fsync of a directory entry boundary.

    :param path: Directory path to fsync
    :type path: pathlib.Path
    :return: ``None``.
    :rtype: None

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     _fsync_directory(Path(tmpdir))
    """

    if not path.exists():
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(str(path), flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


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


def _git_tree_sort_key(name: str, is_tree: bool) -> bytes:
    """
    Build the Git tree sort key for one entry name.

    Git compares tree entries by raw path bytes, with directory names sorted as
    if they had a trailing slash.

    :param name: Entry name relative to the current tree
    :type name: str
    :param is_tree: Whether the entry is a tree/directory
    :type is_tree: bool
    :return: Raw Git sort key bytes
    :rtype: bytes
    """

    key = str(name).encode("utf-8")
    if is_tree:
        return key + b"/"
    return key


def _git_tree_oid(entries: Sequence[Dict[str, object]]) -> str:
    """
    Compute a Git-compatible tree object ID from public entry metadata.

    Each entry must provide ``name``, ``entry_type``, ``mode``, and
    Git-compatible ``git_oid`` fields.

    :param entries: Tree entry payloads
    :type entries: Sequence[Dict[str, object]]
    :return: Git tree SHA-1 digest
    :rtype: str
    :raises IntegrityError: Raised when any entry has an invalid public Git OID.
    """

    ordered_entries = []
    for entry in entries:
        entry_type = str(entry["entry_type"])
        name = str(entry["name"])
        git_oid = str(entry["git_oid"])
        if not GIT_OID_PATTERN.fullmatch(git_oid):
            raise IntegrityError("invalid git tree entry oid")
        mode = str(entry["mode"])
        if entry_type == "tree" and mode.startswith("0"):
            mode = mode[1:]
        ordered_entries.append((name, entry_type == "tree", mode, git_oid))

    ordered_entries.sort(key=lambda item: _git_tree_sort_key(item[0], item[1]))
    body = b"".join(
        mode.encode("ascii") + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(git_oid)
        for name, is_tree, mode, git_oid in ordered_entries
    )
    header = "tree %d\0" % len(body)
    return sha1(header.encode("utf-8") + body).hexdigest()


def _git_commit_oid(tree_oid: str, parent_oids: Sequence[str], message: str, created_at: str) -> str:
    """
    Compute a Git-compatible commit object ID from public commit metadata.

    :param tree_oid: Git-compatible tree OID for the commit snapshot
    :type tree_oid: str
    :param parent_oids: Parent commit OIDs in stored order
    :type parent_oids: Sequence[str]
    :param message: Stored commit message text
    :type message: str
    :param created_at: Stored UTC timestamp string
    :type created_at: str
    :return: Git commit SHA-1 digest
    :rtype: str
    :raises IntegrityError: Raised when the tree or parent OIDs are invalid.
    """

    if not GIT_OID_PATTERN.fullmatch(str(tree_oid)):
        raise IntegrityError("invalid git tree oid")
    normalized_parents = []
    for parent_oid in parent_oids:
        parent_text = str(parent_oid)
        if not GIT_OID_PATTERN.fullmatch(parent_text):
            raise IntegrityError("invalid git parent oid")
        normalized_parents.append(parent_text)

    timestamp = int(_parse_utc_timestamp(created_at).timestamp())
    signature = "%s <%s> %d +0000" % (
        PUBLIC_GIT_AUTHOR_NAME,
        PUBLIC_GIT_AUTHOR_EMAIL,
        timestamp,
    )
    raw_message = str(message)
    if not raw_message.endswith("\n"):
        raw_message += "\n"
    body_lines = ["tree " + str(tree_oid)]
    body_lines.extend("parent " + parent_oid for parent_oid in normalized_parents)
    body_lines.extend(["author " + signature, "committer " + signature, "", raw_message])
    body = "\n".join(body_lines).encode("utf-8")
    header = "commit %d\0" % len(body)
    return sha1(header.encode("utf-8") + body).hexdigest()


def _add_wildcard_to_directories(pattern: str) -> str:
    """
    Normalize a glob pattern so directory paths include their descendants.

    This mirrors the small compatibility helper used by
    ``huggingface_hub.utils.filter_repo_objects``.

    :param pattern: Input glob pattern
    :type pattern: str
    :return: Normalized glob pattern
    :rtype: str

    Example::

        >>> _add_wildcard_to_directories("nested/")
        'nested/*'
    """

    text = str(pattern)
    if text.endswith("/"):
        return text + "*"
    return text


def _normalize_glob_patterns(patterns: Optional[Union[Sequence[str], str]]) -> Optional[List[str]]:
    """
    Normalize optional glob patterns to a list of strings.

    :param patterns: Raw pattern or patterns
    :type patterns: Optional[Union[Sequence[str], str]]
    :return: Normalized pattern list, or ``None`` when omitted
    :rtype: Optional[List[str]]

    Example::

        >>> _normalize_glob_patterns("*.bin")
        ['*.bin']
    """

    if patterns is None:
        return None
    if isinstance(patterns, str):
        values = [patterns]
    else:
        values = [str(item) for item in patterns]
    return [_add_wildcard_to_directories(item) for item in values]


def _filter_repo_paths(
    items: Sequence[str],
    *,
    allow_patterns: Optional[Union[Sequence[str], str]] = None,
    ignore_patterns: Optional[Union[Sequence[str], str]] = None,
) -> List[str]:
    """
    Filter repo-relative paths using HF-style glob semantics.

    :param items: Candidate repo-relative paths
    :type items: Sequence[str]
    :param allow_patterns: Optional allowlist patterns
    :type allow_patterns: Optional[Union[Sequence[str], str]]
    :param ignore_patterns: Optional denylist patterns
    :type ignore_patterns: Optional[Union[Sequence[str], str]]
    :return: Filtered repo-relative paths
    :rtype: List[str]

    Example::

        >>> _filter_repo_paths(["a.bin", "nested/b.txt"], allow_patterns="*.bin")
        ['a.bin']
    """

    normalized_allow = _normalize_glob_patterns(allow_patterns)
    normalized_ignore = _normalize_glob_patterns(ignore_patterns)

    filtered = []
    for item in items:
        if normalized_allow is not None and not any(fnmatch(item, rule) for rule in normalized_allow):
            continue
        if normalized_ignore is not None and any(fnmatch(item, rule) for rule in normalized_ignore):
            continue
        filtered.append(item)
    return filtered


def _is_relative_to(path: Path, root: Path) -> bool:
    """
    Check whether a path is inside another path.

    :param path: Candidate absolute path
    :type path: pathlib.Path
    :param root: Candidate ancestor directory
    :type root: pathlib.Path
    :return: Whether ``path`` is contained by ``root``
    :rtype: bool

    Example::

        >>> _is_relative_to(Path("/tmp/a/b"), Path("/tmp"))
        True
    """

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


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
    _fsync_directory(path.parent)


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


def _path_metrics(path: Path) -> Tuple[int, int]:
    """
    Sum file bytes and file count beneath a path.

    :param path: File or directory path to inspect
    :type path: pathlib.Path
    :return: Two-tuple of total bytes and file count
    :rtype: Tuple[int, int]

    Example::

        >>> import tempfile
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     root = Path(tmpdir)
        ...     (root / "demo.txt").write_text("hello", encoding="utf-8")
        ...     _path_metrics(root)
        (5, 1)
    """

    if not path.exists():
        return 0, 0
    if path.is_symlink() or path.is_file():
        return path.stat().st_size, 1

    total_size = 0
    file_count = 0
    for current in path.rglob("*"):
        if current.is_symlink() or current.is_file():
            total_size += current.stat().st_size
            file_count += 1
    return total_size, file_count


def _format_bytes(value: int) -> str:
    """
    Render a byte count using a short human-readable unit.

    :param value: Byte count
    :type value: int
    :return: Human-readable size string
    :rtype: str

    Example::

        >>> _format_bytes(1536)
        '1.5 KiB'
    """

    size = float(int(value))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            if unit == "B":
                return "%d %s" % (int(size), unit)
            return "%.1f %s" % (size, unit)
        size /= 1024.0


class RepositoryBackend(object):
    """
    Internal repository backend for the MVP.

    This backend owns the on-disk format, object storage, revision resolution,
    detached read views, and transaction lifecycle used by
    :class:`hubvault.api.HubVaultApi`.

    Example::

        >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
        >>> isinstance(backend, RepositoryBackend)
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._repo_path.as_posix().endswith("demo-repo")
            True
        """

        self._repo_path = Path(repo_path)

    @property
    def _repo_lock_path(self) -> Path:
        """
        Return the filesystem path used for the repository RW lock file.

        :return: Absolute lock file path
        :rtype: pathlib.Path

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._repo_lock_path.name
            'repo.lock'
        """

        return self._repo_path / "locks" / REPO_LOCK_FILENAME

    @contextmanager
    def _read_locked(self):
        """
        Hold the repository shared read lock for the duration of a block.

        :return: Iterator yielding ``None`` while the shared lock is held
        :rtype: Iterator[None]
        """

        lock = InterProcessReaderWriterLock(str(self._repo_lock_path))
        with lock.read_lock():
            yield

    @contextmanager
    def _write_locked(self):
        """
        Hold the repository exclusive write lock for the duration of a block.

        :return: Iterator yielding ``None`` while the exclusive lock is held
        :rtype: Iterator[None]
        """

        lock = InterProcessReaderWriterLock(str(self._repo_lock_path))
        with lock.write_lock():
            yield

    def _read_staged_or_published_object_payload(self, txdir: Optional[Path], object_type: str, object_id: str) -> Dict[str, object]:
        """
        Read a JSON-backed object payload from staged or published storage.

        :param txdir: Optional transaction directory to consult first
        :type txdir: Optional[pathlib.Path]
        :param object_type: Stored object collection name
        :type object_type: str
        :param object_id: Object identifier
        :type object_id: str
        :return: Decoded logical payload
        :rtype: Dict[str, object]
        :raises IntegrityError: Raised when a staged object container is malformed.
        """

        if txdir is not None:
            staged_path = self._stage_object_json_path(txdir, object_type, object_id)
            if staged_path.exists():
                container = _read_json(staged_path)
                if not isinstance(container, dict) or "payload" not in container:
                    raise IntegrityError("invalid object container")
                return dict(container["payload"])
        return self._read_object_payload(object_type, object_id)

    def _public_tree_oid(
        self,
        tree_id: str,
        txdir: Optional[Path] = None,
        cache: Optional[Dict[str, str]] = None,
        active: Optional[set] = None,
    ) -> str:
        """
        Resolve the public Git-compatible tree OID for an internal tree object.

        :param tree_id: Internal tree object identifier
        :type tree_id: str
        :param txdir: Optional transaction directory to consult first
        :type txdir: Optional[pathlib.Path], optional
        :param cache: Optional memoization cache keyed by internal tree ID
        :type cache: Optional[Dict[str, str]], optional
        :param active: Optional recursion guard set
        :type active: Optional[set], optional
        :return: Git-compatible public tree OID
        :rtype: str
        :raises IntegrityError: Raised when the tree payload is malformed.
        """

        if cache is None:
            cache = {}
        if active is None:
            active = set()
        cached = cache.get(tree_id)
        if cached is not None:
            return cached
        if tree_id in active:
            raise IntegrityError("tree cycle detected while computing public tree oid")

        active.add(tree_id)
        try:
            tree_payload = self._read_staged_or_published_object_payload(txdir, "trees", tree_id)
            stored_git_oid = tree_payload.get("git_oid")
            if stored_git_oid is not None:
                stored_git_oid = str(stored_git_oid)
                if not GIT_OID_PATTERN.fullmatch(stored_git_oid):
                    raise IntegrityError("invalid stored git tree oid")
                cache[tree_id] = stored_git_oid
                return stored_git_oid

            public_entries = []
            for entry in tree_payload.get("entries", []):
                entry_type = str(entry["entry_type"])
                object_id = str(entry["object_id"])
                if entry_type == "file":
                    file_payload = self._read_staged_or_published_object_payload(txdir, "files", object_id)
                    entry_git_oid = str(file_payload["oid"])
                elif entry_type == "tree":
                    entry_git_oid = self._public_tree_oid(object_id, txdir=txdir, cache=cache, active=active)
                else:
                    raise IntegrityError("unknown tree entry type")
                public_entries.append(
                    {
                        "name": str(entry["name"]),
                        "entry_type": entry_type,
                        "mode": str(entry["mode"]),
                        "git_oid": entry_git_oid,
                    }
                )

            public_tree_oid = _git_tree_oid(public_entries)
            cache[tree_id] = public_tree_oid
            return public_tree_oid
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, RevisionNotFoundError) as err:
            raise IntegrityError("invalid tree %s: %s" % (tree_id, err))
        finally:
            active.discard(tree_id)

    def _public_commit_oid(
        self,
        commit_id: str,
        txdir: Optional[Path] = None,
        commit_cache: Optional[Dict[str, str]] = None,
        tree_cache: Optional[Dict[str, str]] = None,
        active: Optional[set] = None,
    ) -> str:
        """
        Resolve the public Git-compatible commit OID for an internal commit object.

        :param commit_id: Internal commit object identifier
        :type commit_id: str
        :param txdir: Optional transaction directory to consult first
        :type txdir: Optional[pathlib.Path], optional
        :param commit_cache: Optional memoization cache keyed by internal commit ID
        :type commit_cache: Optional[Dict[str, str]], optional
        :param tree_cache: Optional memoization cache keyed by internal tree ID
        :type tree_cache: Optional[Dict[str, str]], optional
        :param active: Optional recursion guard set
        :type active: Optional[set], optional
        :return: Git-compatible public commit OID
        :rtype: str
        :raises IntegrityError: Raised when the commit payload is malformed.
        """

        if commit_cache is None:
            commit_cache = {}
        if tree_cache is None:
            tree_cache = {}
        if active is None:
            active = set()
        cached = commit_cache.get(commit_id)
        if cached is not None:
            return cached
        if commit_id in active:
            raise IntegrityError("commit cycle detected while computing public commit oid")

        active.add(commit_id)
        try:
            commit_payload = self._read_staged_or_published_object_payload(txdir, "commits", commit_id)
            stored_git_oid = commit_payload.get("git_oid")
            if stored_git_oid is not None:
                stored_git_oid = str(stored_git_oid)
                if not GIT_OID_PATTERN.fullmatch(stored_git_oid):
                    raise IntegrityError("invalid stored git commit oid")
                commit_cache[commit_id] = stored_git_oid
                return stored_git_oid

            tree_oid = self._public_tree_oid(str(commit_payload["tree_id"]), txdir=txdir, cache=tree_cache)
            parent_oids = [
                self._public_commit_oid(
                    str(parent_id),
                    txdir=txdir,
                    commit_cache=commit_cache,
                    tree_cache=tree_cache,
                    active=active,
                )
                for parent_id in commit_payload.get("parents", [])
            ]
            public_commit_oid = _git_commit_oid(
                tree_oid=tree_oid,
                parent_oids=parent_oids,
                message=str(commit_payload.get("message", "")),
                created_at=str(commit_payload["created_at"]),
            )
            commit_cache[commit_id] = public_commit_oid
            return public_commit_oid
        except IntegrityError:
            raise
        except (KeyError, TypeError, ValueError, RevisionNotFoundError) as err:
            raise IntegrityError("invalid commit %s: %s" % (commit_id, err))
        finally:
            active.discard(commit_id)

    def _public_commit_oid_or_none(self, commit_id: Optional[str], txdir: Optional[Path] = None) -> Optional[str]:
        """
        Resolve an optional internal commit ID to its public Git OID.

        :param commit_id: Internal commit object identifier, or ``None``
        :type commit_id: Optional[str]
        :param txdir: Optional transaction directory to consult first
        :type txdir: Optional[pathlib.Path], optional
        :return: Public Git OID, or ``None``
        :rtype: Optional[str]
        """

        if commit_id is None:
            return None
        return self._public_commit_oid(commit_id, txdir=txdir)

    def create_repo(
        self,
        default_branch: str = DEFAULT_BRANCH,
        exist_ok: bool = False,
        large_file_threshold: int = LARGE_FILE_THRESHOLD,
    ) -> RepoInfo:
        """
        Create a repository at the configured root path.

        This method bootstraps the self-contained on-disk layout, writes the
        format marker and repository configuration, initializes the default
        branch, and immediately writes an empty initial commit so the repo has a
        valid first history entry from the start.

        :param default_branch: Default branch name to create, defaults to
            :data:`DEFAULT_BRANCH`
        :type default_branch: str, optional
        :param exist_ok: Whether an existing repository may be reused,
            defaults to ``False``
        :type exist_ok: bool, optional
        :param large_file_threshold: File size threshold in bytes at or above
            which newly added files switch to chunked storage, defaults to
            :data:`LARGE_FILE_THRESHOLD`
        :type large_file_threshold: int, optional
        :return: Public metadata for the created or reused repository
        :rtype: RepoInfo
        :raises RepositoryAlreadyExistsError: Raised when the target path already
            contains a repository or any non-empty directory.
        :raises UnsupportedPathError: Raised when ``default_branch`` violates
            repository ref naming rules.
        :raises ValueError: Raised when ``large_file_threshold`` is not
            positive.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     info = backend.create_repo()
            ...     (info.default_branch, info.head is not None)
            ('main', True)
        """

        default_branch = _validate_ref_name(default_branch)
        large_file_threshold = int(large_file_threshold)
        if large_file_threshold <= 0:
            raise ValueError("large_file_threshold must be > 0")
        if not self._repo_path.exists():
            self._repo_path.mkdir(parents=True)
            _fsync_directory(self._repo_path.parent)

        (self._repo_path / "locks").mkdir(parents=True, exist_ok=True)
        _fsync_directory(self._repo_path / "locks")

        with self._write_locked():
            if self._is_repo():
                if not exist_ok:
                    raise RepositoryAlreadyExistsError("repository already exists")
                return self._repo_info_unlocked(revision=None)

            visible_entries = [entry.name for entry in self._repo_path.iterdir() if entry.name != "locks"]
            if visible_entries:
                raise RepositoryAlreadyExistsError("target path is not empty")

            extra_lock_entries = [
                entry.name for entry in (self._repo_path / "locks").iterdir() if entry.name != REPO_LOCK_FILENAME
            ]
            if extra_lock_entries:
                raise RepositoryAlreadyExistsError("target path is not empty")

            self._ensure_layout()
            _write_text_atomic(self._format_path, FORMAT_MARKER + "\n")
            _write_json_atomic(
                self._repo_config_path,
                {
                    "format_version": FORMAT_VERSION,
                    "default_branch": default_branch,
                    "object_hash": OBJECT_HASH,
                    "file_mode": "whole-blob-first",
                    "large_file_threshold": large_file_threshold,
                    "metadata": {},
                },
            )
            IndexStore(self._repo_path / "chunks" / "index").write_manifest(IndexManifest.empty())
            self._write_ref(default_branch, None)
            self._create_initial_commit_unlocked(default_branch)
            return self._repo_info_unlocked(revision=None)

    def _create_initial_commit_unlocked(self, branch_name: str) -> str:
        """
        Create the bootstrap empty commit while the repo write lock is held.

        :param branch_name: Default branch name receiving the initial commit
        :type branch_name: str
        :return: Initial commit object ID
        :rtype: str
        """

        current_head = self._read_ref(branch_name)
        txdir = self._create_txdir(branch_name, current_head)
        try:
            tree_id = self._stage_tree_objects(txdir, {})
            created_at = _utc_now()
            commit_payload = {
                "format_version": FORMAT_VERSION,
                "tree_id": tree_id,
                "parents": [],
                "author": "",
                "committer": "",
                "created_at": created_at,
                "message": "Initial commit",
                "title": "Initial commit",
                "description": "",
                "metadata": {},
            }
            commit_payload["git_oid"] = _git_commit_oid(
                tree_oid=self._public_tree_oid(tree_id, txdir=txdir),
                parent_oids=[],
                message=str(commit_payload["message"]),
                created_at=created_at,
            )
            commit_id = self._stage_json_object(txdir, "commits", commit_payload)
            self._stage_chunk_manifest(txdir)
            self._write_tx_state(txdir, "STAGED")
            self._publish_staged_objects(txdir)
            self._write_tx_state(txdir, "PUBLISHED_OBJECTS")
            self._commit_branch_ref_update_unlocked(
                txdir=txdir,
                branch_name=branch_name,
                old_head=current_head,
                new_head=commit_id,
                message="Initial commit",
                failpoint_prefix="create_repo.initial_commit",
            )
        except BaseException:
            # Roll back even on interrupts so create_repo() never exposes a
            # half-visible initial history root.
            self._rollback_transaction_unlocked(txdir)
            raise
        self._safe_cleanup_txdir(txdir)
        return commit_id

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
        :raises RepositoryNotFoundError: Raised when the configured root is not a
            valid repository.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.repo_info().default_branch
            'main'
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            return self._repo_info_unlocked(revision=revision)

    def _repo_info_unlocked(self, revision: Optional[str]) -> RepoInfo:
        """
        Build repository metadata while the caller already holds a repo lock.

        :param revision: Revision whose visible head should be resolved
        :type revision: Optional[str]
        :return: Current repository metadata view
        :rtype: RepoInfo
        """

        config = self._repo_config()
        selected_revision = revision or str(config["default_branch"])
        head = self._resolve_revision(selected_revision, allow_empty_ref=True)
        return RepoInfo(
            repo_path=str(self._repo_path),
            format_version=int(config["format_version"]),
            default_branch=str(config["default_branch"]),
            head=self._public_commit_oid_or_none(head),
            refs=self._list_refs(),
        )

    def create_commit(
        self,
        operations: Sequence[object],
        commit_message: str,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Create a new commit on a branch revision.

        The backend stages all new objects in a transaction directory, publishes
        them atomically, and only then updates the branch ref and reflog.

        :param operations: Add, delete, or copy operations to apply
        :type operations: Sequence[object]
        :param commit_message: Commit summary/title to store. When
            ``commit_description`` is omitted, embedded body text after a blank
            line is preserved and split the same way Git and HF commit listings
            interpret commit text.
        :type commit_message: str
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str], optional
        :param revision: Branch name that will receive the new commit,
            defaults to the repository default branch
        :type revision: Optional[str], optional
        :param parent_commit: Optional expected parent commit for optimistic
            concurrency checks. When omitted, the current branch head becomes
            the implicit base revision.
        :type parent_commit: Optional[str], optional
        :return: Public metadata for the created commit
        :rtype: CommitInfo
        :raises ConflictError: Raised when no operations are supplied, an
            unsupported operation is provided, or optimistic concurrency checks
            fail.
        :raises EntryNotFoundError: Raised when delete or copy operations refer
            to missing paths.
        :raises RevisionNotFoundError: Raised when the target revision cannot be
            resolved.
        :raises UnsupportedPathError: Raised when revision names or repo paths
            are invalid.
        :raises ValueError: Raised when ``commit_message`` is empty.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     commit = backend.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     commit.commit_message
            'seed'
        """

        self._ensure_repo()
        if not operations:
            raise ConflictError("operations must not be empty")
        if commit_message is None or len(commit_message) == 0:
            raise ValueError("`commit_message` can't be empty, please pass a value.")

        raw_commit_message = str(commit_message)
        if commit_description is None:
            stored_title, stored_description = self._split_commit_message(raw_commit_message)
            full_commit_message = raw_commit_message
        else:
            stored_title = raw_commit_message
            stored_description = str(commit_description)
            full_commit_message = self._compose_commit_text(stored_title, stored_description)

        with self._write_locked():
            self._recover_transactions()
            repo_config = self._repo_config()
            branch_name = _validate_ref_name(revision or str(repo_config["default_branch"]))
            current_head = self._read_ref(branch_name)
            txdir = self._create_txdir(branch_name, current_head)
            try:
                if parent_commit is not None:
                    expected_parent_commit = self._resolve_revision(parent_commit)
                    if expected_parent_commit != current_head:
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
                created_at = _utc_now()
                commit_payload = {
                    "format_version": FORMAT_VERSION,
                    "tree_id": tree_id,
                    "parents": [current_head] if current_head else [],
                    "author": "",
                    "committer": "",
                    "created_at": created_at,
                    "message": full_commit_message,
                    "title": stored_title,
                    "description": stored_description,
                    "metadata": {},
                }
                commit_payload["git_oid"] = _git_commit_oid(
                    tree_oid=self._public_tree_oid(tree_id, txdir=txdir),
                    parent_oids=[
                        self._public_commit_oid(current_head),
                    ] if current_head else [],
                    message=full_commit_message,
                    created_at=created_at,
                )
                commit_id = self._stage_json_object(txdir, "commits", commit_payload)
                self._stage_chunk_manifest(txdir)
                result = CommitInfo(
                    commit_url=self._commit_url(commit_id, txdir=txdir),
                    commit_message=stored_title,
                    commit_description=stored_description,
                    oid=self._public_commit_oid(commit_id, txdir=txdir),
                )

                self._write_tx_state(txdir, "STAGED")
                self._publish_staged_objects(txdir)
                self._write_tx_state(txdir, "PUBLISHED_OBJECTS")
                self._maybe_failpoint("create_commit.after_publish")
                self._commit_branch_ref_update_unlocked(
                    txdir=txdir,
                    branch_name=branch_name,
                    old_head=current_head,
                    new_head=commit_id,
                    message=commit_message,
                    failpoint_prefix="create_commit",
                )
            except BaseException:
                # Roll back even on interrupts so an interrupted create_commit()
                # is indistinguishable from never having happened.
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)
            return result

    def merge(
        self,
        source_revision: str,
        target_revision: str = DEFAULT_BRANCH,
        parent_commit: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
    ) -> MergeResult:
        """
        Merge a source revision into a target branch.

        The local repository exposes merge as a first-class public write API.
        Successful merges return a structured result describing whether the
        operation created a merge commit, fast-forwarded the target branch, or
        found the branches already up to date. Conflicts are reported in the
        result instead of mutating repository state.

        :param source_revision: Source branch, tag, or commit ID to merge from
        :type source_revision: str
        :param target_revision: Target branch name or full branch ref, defaults
            to :data:`DEFAULT_BRANCH`
        :type target_revision: str, optional
        :param parent_commit: Optional expected current head for optimistic
            concurrency on the target branch
        :type parent_commit: Optional[str], optional
        :param commit_message: Optional merge-commit title
        :type commit_message: Optional[str], optional
        :param commit_description: Optional merge-commit description/body
        :type commit_description: Optional[str], optional
        :return: Structured merge result
        :rtype: MergeResult
        :raises ConflictError: Raised when ``parent_commit`` does not match the
            current target head.
        :raises RevisionNotFoundError: Raised when the source revision or
            target branch does not exist.
        :raises UnsupportedPathError: Raised when ``target_revision`` is not a
            branch ref.
        :raises ValueError: Raised when ``commit_message`` is explicitly empty.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"base")],
            ...         commit_message="seed",
            ...     )
            ...     backend.create_branch(branch="feature")
            ...     _ = backend.create_commit(
            ...         revision="feature",
            ...         operations=[CommitOperationAdd("feature.txt", b"hello")],
            ...         commit_message="feature work",
            ...     )
            ...     backend.merge("feature").status
            'fast-forward'
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()
            repo_config = self._repo_config()
            target_branch_name = self._resolve_target_branch_name_unlocked(
                target_revision or str(repo_config["default_branch"])
            )
            target_head = self._read_ref(target_branch_name)
            if parent_commit is not None:
                expected_parent_commit = self._resolve_revision(parent_commit)
                if expected_parent_commit != target_head:
                    raise ConflictError("expected head does not match current branch head")

            source_head = self._resolve_revision(source_revision, allow_empty_ref=True)

            if source_head is None:
                return MergeResult(
                    status="already-up-to-date",
                    target_revision=target_branch_name,
                    source_revision=source_revision,
                    base_commit=None,
                    target_head_before=self._public_commit_oid_or_none(target_head),
                    source_head=None,
                    head_after=self._public_commit_oid_or_none(target_head),
                    commit=self._commit_info(target_head, target_branch_name) if target_head is not None else None,
                    conflicts=[],
                    fast_forward=False,
                    created_commit=False,
                )

            if target_head is None:
                txdir = self._create_txdir(target_branch_name, target_head)
                try:
                    result = MergeResult(
                        status="fast-forward",
                        target_revision=target_branch_name,
                        source_revision=source_revision,
                        base_commit=None,
                        target_head_before=None,
                        source_head=self._public_commit_oid_or_none(source_head),
                        head_after=self._public_commit_oid_or_none(source_head),
                        commit=self._commit_info(source_head, target_branch_name),
                        conflicts=[],
                        fast_forward=True,
                        created_commit=False,
                    )
                    self._commit_branch_ref_update_unlocked(
                        txdir=txdir,
                        branch_name=target_branch_name,
                        old_head=target_head,
                        new_head=source_head,
                        message=self._default_merge_title(source_revision, target_branch_name),
                        failpoint_prefix="merge",
                    )
                except BaseException:
                    self._rollback_transaction_unlocked(txdir)
                    raise
                self._safe_cleanup_txdir(txdir)
                return result

            if target_head == source_head:
                return MergeResult(
                    status="already-up-to-date",
                    target_revision=target_branch_name,
                    source_revision=source_revision,
                    base_commit=self._public_commit_oid_or_none(target_head),
                    target_head_before=self._public_commit_oid_or_none(target_head),
                    source_head=self._public_commit_oid_or_none(source_head),
                    head_after=self._public_commit_oid_or_none(target_head),
                    commit=self._commit_info(target_head, target_branch_name),
                    conflicts=[],
                    fast_forward=False,
                    created_commit=False,
                )

            if self._is_ancestor_unlocked(source_head, target_head):
                return MergeResult(
                    status="already-up-to-date",
                    target_revision=target_branch_name,
                    source_revision=source_revision,
                    base_commit=self._public_commit_oid_or_none(source_head),
                    target_head_before=self._public_commit_oid_or_none(target_head),
                    source_head=self._public_commit_oid_or_none(source_head),
                    head_after=self._public_commit_oid_or_none(target_head),
                    commit=self._commit_info(target_head, target_branch_name),
                    conflicts=[],
                    fast_forward=False,
                    created_commit=False,
                )

            if self._is_ancestor_unlocked(target_head, source_head):
                txdir = self._create_txdir(target_branch_name, target_head)
                try:
                    result = MergeResult(
                        status="fast-forward",
                        target_revision=target_branch_name,
                        source_revision=source_revision,
                        base_commit=self._public_commit_oid_or_none(target_head),
                        target_head_before=self._public_commit_oid_or_none(target_head),
                        source_head=self._public_commit_oid_or_none(source_head),
                        head_after=self._public_commit_oid_or_none(source_head),
                        commit=self._commit_info(source_head, target_branch_name),
                        conflicts=[],
                        fast_forward=True,
                        created_commit=False,
                    )
                    self._commit_branch_ref_update_unlocked(
                        txdir=txdir,
                        branch_name=target_branch_name,
                        old_head=target_head,
                        new_head=source_head,
                        message=self._default_merge_title(source_revision, target_branch_name),
                        failpoint_prefix="merge",
                    )
                except BaseException:
                    self._rollback_transaction_unlocked(txdir)
                    raise
                self._safe_cleanup_txdir(txdir)
                return result

            base_commit = self._find_merge_base_unlocked(target_head, source_head)
            target_snapshot = self._snapshot_for_commit(target_head)
            source_snapshot = self._snapshot_for_commit(source_head)
            base_snapshot = self._snapshot_for_commit(base_commit)
            merged_snapshot, conflicts = self._merge_snapshots_unlocked(
                base_snapshot=base_snapshot,
                target_snapshot=target_snapshot,
                source_snapshot=source_snapshot,
            )
            if conflicts:
                return MergeResult(
                    status="conflict",
                    target_revision=target_branch_name,
                    source_revision=source_revision,
                    base_commit=self._public_commit_oid_or_none(base_commit),
                    target_head_before=self._public_commit_oid_or_none(target_head),
                    source_head=self._public_commit_oid_or_none(source_head),
                    head_after=self._public_commit_oid_or_none(target_head),
                    commit=None,
                    conflicts=conflicts,
                    fast_forward=False,
                    created_commit=False,
                )

            merge_title = commit_message
            if merge_title is None:
                merge_title = self._default_merge_title(source_revision, target_branch_name)
            if len(merge_title) == 0:
                raise ValueError("`commit_message` can't be empty, please pass a value.")

            if commit_description is None:
                stored_title, stored_description = self._split_commit_message(merge_title)
                full_commit_message = merge_title
            else:
                stored_title = str(merge_title)
                stored_description = str(commit_description)
                full_commit_message = self._compose_commit_text(stored_title, stored_description)

            txdir = self._create_txdir(target_branch_name, target_head)
            try:
                self._validate_snapshot(merged_snapshot)
                tree_id = self._stage_tree_objects(txdir, merged_snapshot)
                created_at = _utc_now()
                commit_payload = {
                    "format_version": FORMAT_VERSION,
                    "tree_id": tree_id,
                    "parents": [target_head, source_head],
                    "author": "",
                    "committer": "",
                    "created_at": created_at,
                    "message": full_commit_message,
                    "title": stored_title,
                    "description": stored_description,
                    "metadata": {
                        "merge": {
                            "base_commit": base_commit,
                            "source_revision": source_revision,
                            "target_revision": target_branch_name,
                        }
                    },
                }
                commit_payload["git_oid"] = _git_commit_oid(
                    tree_oid=self._public_tree_oid(tree_id, txdir=txdir),
                    parent_oids=[
                        self._public_commit_oid(target_head),
                        self._public_commit_oid(source_head),
                    ],
                    message=full_commit_message,
                    created_at=created_at,
                )
                commit_id = self._stage_json_object(txdir, "commits", commit_payload)
                self._stage_chunk_manifest(txdir)
                result = MergeResult(
                    status="merged",
                    target_revision=target_branch_name,
                    source_revision=source_revision,
                    base_commit=self._public_commit_oid_or_none(base_commit),
                    target_head_before=self._public_commit_oid_or_none(target_head),
                    source_head=self._public_commit_oid_or_none(source_head),
                    head_after=self._public_commit_oid(commit_id, txdir=txdir),
                    commit=CommitInfo(
                        commit_url=self._commit_url(commit_id, txdir=txdir),
                        commit_message=stored_title,
                        commit_description=stored_description,
                        oid=self._public_commit_oid(commit_id, txdir=txdir),
                    ),
                    conflicts=[],
                    fast_forward=False,
                    created_commit=True,
                )
                self._write_tx_state(txdir, "STAGED")
                self._publish_staged_objects(txdir)
                self._write_tx_state(txdir, "PUBLISHED_OBJECTS")
                self._maybe_failpoint("merge.after_publish")
                self._commit_branch_ref_update_unlocked(
                    txdir=txdir,
                    branch_name=target_branch_name,
                    old_head=target_head,
                    new_head=commit_id,
                    message=stored_title,
                    failpoint_prefix="merge",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)
            return result

    def get_paths_info(
        self,
        paths: Union[Sequence[str], str],
        revision: str = DEFAULT_BRANCH,
    ) -> List[Union[RepoFile, RepoFolder]]:
        """
        Return public metadata for the requested paths.

        This method intentionally follows the main behavior of
        :meth:`huggingface_hub.HfApi.get_paths_info`: existing file and folder
        paths are returned in input order, while missing paths are ignored
        instead of raising an exception.

        :param paths: Repo-relative path or paths to inspect
        :type paths: Union[Sequence[str], str]
        :param revision: Revision to resolve, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Path metadata in the same order as existing requested paths
        :rtype: List[Union[RepoFile, RepoFolder]]
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when any supplied path is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     type(backend.get_paths_info(["nested", "nested/demo.txt"])[0]).__name__
            'RepoFolder'
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            snapshot = self._snapshot_for_revision(revision)
            requested_paths = [paths] if isinstance(paths, str) else list(paths)
            infos = []
            for raw_path in requested_paths:
                normalized_path = _normalize_repo_path(raw_path)
                if normalized_path in snapshot:
                    infos.append(self._repo_file_info(normalized_path, snapshot[normalized_path]))
                    continue

                prefix = normalized_path + "/"
                if any(path.startswith(prefix) for path in snapshot):
                    infos.append(self._repo_folder_info(revision, normalized_path))
            return infos

    def list_repo_tree(
        self,
        path_in_repo: Optional[str] = None,
        recursive: bool = False,
        revision: str = DEFAULT_BRANCH,
    ) -> List[Union[RepoFile, RepoFolder]]:
        """
        List file and folder entries under a repository directory.

        This method intentionally follows the main behavior of
        :meth:`huggingface_hub.HfApi.list_repo_tree`, including the
        ``recursive`` flag and the use of HF-style ``RepoFile`` /
        ``RepoFolder`` return objects.

        :param path_in_repo: Repo-relative directory path, or ``None`` for the
            repository root
        :type path_in_repo: Optional[str], optional
        :param recursive: Whether to include descendants recursively
        :type recursive: bool, optional
        :param revision: Revision to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Sorted metadata entries for direct children
        :rtype: List[Union[RepoFile, RepoFolder]]
        :raises EntryNotFoundError: Raised when the requested directory does not
            exist.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``path_in_repo`` violates
            path rules.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     [item.path for item in backend.list_repo_tree("nested")]
            ['nested/demo.txt']
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            head_commit_id = self._resolve_revision(revision, allow_empty_ref=True)
            if head_commit_id is None:
                return []

            commit_payload = self._read_object_payload("commits", head_commit_id)
            root_tree_id = str(commit_payload["tree_id"])

            if not path_in_repo:
                tree_id = root_tree_id
                prefix = ""
            else:
                prefix = _normalize_repo_path(path_in_repo)
                tree_id = self._tree_id_for_directory(root_tree_id, prefix)

            return self._list_tree_entries(tree_id, prefix=prefix, recursive=recursive)

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
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.list_repo_files()
            ['demo.txt']
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
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

        The returned list walks the reachable commit DAG from the selected head
        in a stable parent-first order. This keeps merge commits visible while
        remaining deterministic for local regression tests.

        :param revision: Revision or commit ID to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :param formatted: Whether HTML-formatted title/message fields should be
            populated
        :type formatted: bool, optional
        :return: Commit entries ordered from newest to oldest
        :rtype: List[GitCommitInfo]
        :raises RepositoryNotFoundError: Raised when the configured root is not a
            valid repository.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
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
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            head_commit_id = self._resolve_revision(revision, allow_empty_ref=True)
            if head_commit_id is None:
                return []

            return [
                self._git_commit_info(commit_id, formatted=formatted)
                for commit_id in self._reachable_commit_order_unlocked(head_commit_id)
            ]

    def list_repo_refs(self, include_pull_requests: bool = False) -> GitRefs:
        """
        List visible branch and tag refs in HF-style form.

        The local repository does not support convert refs or pull requests, but
        keeps the same top-level return shape as
        :meth:`huggingface_hub.HfApi.list_repo_refs`.

        :param include_pull_requests: Whether pull-request refs should be
            included. The local repository returns ``[]`` when requested and
            ``None`` otherwise.
        :type include_pull_requests: bool, optional
        :return: Visible repository refs
        :rtype: GitRefs
        :raises RepositoryNotFoundError: Raised when the configured root is not
            a valid repository.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.list_repo_refs().branches[0].ref
            'refs/heads/main'
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            branches = [
                GitRefInfo(
                    name=name,
                    ref="refs/heads/" + name,
                    target_commit=self._public_commit_oid_or_none(self._read_ref(name)),
                )
                for name in self._list_branch_names()
            ]
            tags = [
                GitRefInfo(
                    name=name,
                    ref="refs/tags/" + name,
                    target_commit=self._public_commit_oid_or_none(self._read_tag_ref(name)),
                )
                for name in self._list_tag_names()
            ]
            return GitRefs(
                branches=branches,
                converts=[],
                tags=tags,
                pull_requests=[] if include_pull_requests else None,
            )

    def create_branch(
        self,
        *,
        branch: str,
        revision: Optional[str] = None,
        exist_ok: bool = False,
    ) -> None:
        """
        Create a new branch from an existing revision.

        The public method name and main parameters intentionally mirror
        :meth:`huggingface_hub.HfApi.create_branch`, while omitting remote-only
        parameters such as ``repo_id``, ``repo_type``, and ``token``.

        :param branch: Branch name to create
        :type branch: str
        :param revision: Starting revision, defaults to the repository default
            branch
        :type revision: Optional[str], optional
        :param exist_ok: Whether an existing branch should be accepted
        :type exist_ok: bool, optional
        :return: ``None``.
        :rtype: None
        :raises ConflictError: Raised when the branch already exists and
            ``exist_ok`` is ``False``.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``branch`` is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.create_branch(branch="dev")
            ...     sorted(ref.name for ref in backend.list_repo_refs().branches)
            ['dev', 'main']
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()

            branch_name = _validate_ref_name(branch)
            branch_path = self._ref_path(branch_name)
            if branch_path.exists():
                if exist_ok:
                    return
                raise ConflictError("branch already exists: %s" % branch_name)

            repo_config = self._repo_config()
            base_revision = revision or str(repo_config["default_branch"])
            target_commit = self._resolve_revision(base_revision, allow_empty_ref=True)

            txdir = self._create_txdir(branch_name, target_commit)
            try:
                self._finalize_ref_update_unlocked(
                    txdir=txdir,
                    ref_kind="branch",
                    ref_name=branch_name,
                    old_head=None,
                    new_head=target_commit,
                    message="create branch",
                    ref_existed_before=False,
                    apply_ref_change=lambda: self._write_ref(branch_name, target_commit),
                    failpoint_prefix="create_branch",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)

    def delete_branch(self, *, branch: str) -> None:
        """
        Delete a branch ref from the repository.

        The current default branch is protected from deletion, mirroring the
        practical behavior users expect from the HF Hub.

        :param branch: Branch name to delete
        :type branch: str
        :return: ``None``.
        :rtype: None
        :raises ConflictError: Raised when attempting to delete the default
            branch.
        :raises RevisionNotFoundError: Raised when the branch does not exist.
        :raises UnsupportedPathError: Raised when ``branch`` is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.create_branch(branch="dev")
            ...     backend.delete_branch(branch="dev")
            ...     [ref.name for ref in backend.list_repo_refs().branches]
            ['main']
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()

            repo_config = self._repo_config()
            branch_name = _validate_ref_name(branch)
            if branch_name == str(repo_config["default_branch"]):
                raise ConflictError("default branch cannot be deleted")

            old_head = self._read_ref(branch_name)
            txdir = self._create_txdir(branch_name, old_head)
            try:
                self._finalize_ref_update_unlocked(
                    txdir=txdir,
                    ref_kind="branch",
                    ref_name=branch_name,
                    old_head=old_head,
                    new_head=None,
                    message="delete branch",
                    ref_existed_before=True,
                    apply_ref_change=lambda: self._delete_ref_file(
                        self._ref_path(branch_name),
                        self._repo_path / "refs" / "heads",
                    ),
                    failpoint_prefix="delete_branch",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)

    def create_tag(
        self,
        *,
        tag: str,
        tag_message: Optional[str] = None,
        revision: Optional[str] = None,
        exist_ok: bool = False,
    ) -> None:
        """
        Create a lightweight tag pointing at a revision.

        :param tag: Tag name to create
        :type tag: str
        :param tag_message: Optional tag message stored in the reflog
        :type tag_message: Optional[str], optional
        :param revision: Target revision, defaults to the repository default
            branch
        :type revision: Optional[str], optional
        :param exist_ok: Whether an existing tag should be accepted
        :type exist_ok: bool, optional
        :return: ``None``.
        :rtype: None
        :raises ConflictError: Raised when the tag already exists and
            ``exist_ok`` is ``False``.
        :raises RevisionNotFoundError: Raised when the target revision does not
            resolve to a commit.
        :raises UnsupportedPathError: Raised when ``tag`` is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.create_tag(tag="v1")
            ...     [ref.name for ref in backend.list_repo_refs().tags]
            ['v1']
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()

            tag_name = _validate_ref_name(tag)
            tag_path = self._tag_ref_path(tag_name)
            if tag_path.exists():
                if exist_ok:
                    return
                raise ConflictError("tag already exists: %s" % tag_name)

            repo_config = self._repo_config()
            target_revision = revision or str(repo_config["default_branch"])
            target_commit = self._resolve_revision(target_revision)

            txdir = self._create_txdir(tag_name, target_commit)
            try:
                self._finalize_ref_update_unlocked(
                    txdir=txdir,
                    ref_kind="tag",
                    ref_name=tag_name,
                    old_head=None,
                    new_head=target_commit,
                    message=tag_message or "create tag",
                    ref_existed_before=False,
                    apply_ref_change=lambda: self._write_tag_ref(tag_name, target_commit),
                    failpoint_prefix="create_tag",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)

    def delete_tag(self, *, tag: str) -> None:
        """
        Delete a tag ref from the repository.

        :param tag: Tag name to delete
        :type tag: str
        :return: ``None``.
        :rtype: None
        :raises RevisionNotFoundError: Raised when the tag does not exist.
        :raises UnsupportedPathError: Raised when ``tag`` is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.create_tag(tag="v1")
            ...     backend.delete_tag(tag="v1")
            ...     backend.list_repo_refs().tags
            []
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()

            tag_name = _validate_ref_name(tag)
            old_head = self._read_tag_ref(tag_name)
            txdir = self._create_txdir(tag_name, old_head)
            try:
                self._finalize_ref_update_unlocked(
                    txdir=txdir,
                    ref_kind="tag",
                    ref_name=tag_name,
                    old_head=old_head,
                    new_head=None,
                    message="delete tag",
                    ref_existed_before=True,
                    apply_ref_change=lambda: self._delete_ref_file(
                        self._tag_ref_path(tag_name),
                        self._repo_path / "refs" / "tags",
                    ),
                    failpoint_prefix="delete_tag",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)

    def list_repo_reflog(
        self,
        ref_name: str,
        limit: Optional[int] = None,
    ) -> List[ReflogEntry]:
        """
        List reflog entries for a branch or tag.

        This is a local repository extension with no direct HF public
        counterpart. It exists to support audit and recovery workflows for the
        embedded on-disk repository.

        :param ref_name: Full ref name such as ``refs/heads/main`` or a short
            branch/tag name when unambiguous
        :type ref_name: str
        :param limit: Optional maximum number of newest entries to return
        :type limit: Optional[int], optional
        :return: Reflog entries ordered from newest to oldest
        :rtype: List[ReflogEntry]
        :raises ConflictError: Raised when a short ref name is ambiguous across
            branches and tags.
        :raises RevisionNotFoundError: Raised when the ref or reflog does not
            exist.
        :raises ValueError: Raised when ``limit`` is negative.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.list_repo_reflog("main")[0].ref_name
            'refs/heads/main'
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            if limit is not None and limit < 0:
                raise ValueError("limit must be >= 0")

            reflog_path, _ = self._resolve_reflog_query(ref_name)
            if not reflog_path.exists():
                return []

            entries = []
            for line in reflog_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                entries.append(
                    ReflogEntry(
                        timestamp=_parse_utc_timestamp(str(payload["timestamp"])),
                        ref_name=str(payload["ref_name"]),
                        old_head=self._public_commit_oid_or_none(payload.get("old_head")),
                        new_head=self._public_commit_oid_or_none(payload.get("new_head")),
                        message=str(payload.get("message", "")),
                        checksum=str(payload["checksum"]),
                    )
                )

            entries.reverse()
            if limit is not None:
                return entries[:limit]
            return entries

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
        :raises EntryNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
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
        :raises EntryNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.read_bytes("demo.txt")
            b'hello'
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            snapshot = self._snapshot_for_revision(revision)
            normalized_path = _normalize_repo_path(path_in_repo)
            try:
                file_object_id = snapshot[normalized_path]
            except KeyError:
                raise EntryNotFoundError("path not found: %s" % normalized_path)
            return self._read_file_bytes_by_object_id(file_object_id)

    def read_range(
        self,
        path_in_repo: str,
        start: int,
        length: int,
        revision: str = DEFAULT_BRANCH,
    ) -> bytes:
        """
        Read a byte range from a file in a revision.

        For chunked files the backend resolves only the overlapping chunks and
        avoids reconstructing unrelated file regions.

        :param path_in_repo: Repo-relative file path to read
        :type path_in_repo: str
        :param start: Starting byte offset in the logical file
        :type start: int
        :param length: Number of bytes to read
        :type length: int
        :param revision: Revision to inspect, defaults to
            :data:`DEFAULT_BRANCH`
        :type revision: str, optional
        :return: Requested byte range, clamped to the file end
        :rtype: bytes
        :raises IntegrityError: Raised when persisted blob or pack content does
            not match recorded checksums.
        :raises EntryNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises ValueError: Raised when ``start`` or ``length`` is negative.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.read_range("demo.txt", start=1, length=3)
            b'ell'
        """

        start = int(start)
        length = int(length)
        if start < 0 or length < 0:
            raise ValueError("start and length must be >= 0")

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            snapshot = self._snapshot_for_revision(revision)
            normalized_path = _normalize_repo_path(path_in_repo)
            try:
                file_object_id = snapshot[normalized_path]
            except KeyError:
                raise EntryNotFoundError("path not found: %s" % normalized_path)
            file_payload = self._read_object_payload("files", file_object_id)
            logical_size = int(file_payload["logical_size"])
            if start >= logical_size or length == 0:
                return b""
            if str(file_payload.get("storage_kind")) == "chunked":
                return self._read_chunked_file_range(file_payload, start=start, length=length)
            return self._read_file_bytes_by_object_id(file_object_id)[start:start + length]

    def _read_file_bytes_by_object_id(self, file_object_id: str) -> bytes:
        """
        Read verified file bytes while the caller already holds a repo lock.

        :param file_object_id: File object identifier
        :type file_object_id: str
        :return: Verified logical file bytes
        :rtype: bytes
        """

        file_payload = self._read_object_payload("files", file_object_id)
        if str(file_payload.get("storage_kind")) == "chunked":
            return self._read_chunked_file_bytes(file_payload)

        blob_object_id = str(file_payload["content_object_id"])
        blob_meta = self._read_object_payload("blobs", blob_object_id)
        blob_data_path = self._blob_data_path(blob_object_id)
        data = blob_data_path.read_bytes()
        data_sha256 = OBJECT_HASH + ":" + _sha256_hex(data)
        if data_sha256 != blob_meta["payload_sha256"]:
            raise IntegrityError("blob payload checksum mismatch")
        return data

    def _read_chunked_file_bytes(self, file_payload: Dict[str, object]) -> bytes:
        """
        Reconstruct a chunked file from pack storage.

        :param file_payload: File object payload with ``storage_kind="chunked"``
        :type file_payload: Dict[str, object]
        :return: Verified logical file bytes
        :rtype: bytes
        :raises IntegrityError: Raised when chunk metadata, pack content, or
            file-level checksums do not match.
        """

        data = self._read_chunked_file_range(
            file_payload,
            start=0,
            length=int(file_payload["logical_size"]),
        )
        data_sha256 = _sha256_hex(data)
        if data_sha256 != _public_sha256_hex(str(file_payload["sha256"])):
            raise IntegrityError("file sha256 mismatch")
        expected_oid = chunk_git_blob_oid(canonical_lfs_pointer(data_sha256, len(data)))
        if expected_oid != str(file_payload["oid"]):
            raise IntegrityError("file oid mismatch")
        if str(file_payload["etag"]) != data_sha256:
            raise IntegrityError("file etag mismatch")
        return data

    def _read_chunked_file_range(
        self,
        file_payload: Dict[str, object],
        start: int,
        length: int,
    ) -> bytes:
        """
        Read and verify only the overlapping chunks for a requested byte range.

        :param file_payload: File object payload with ``storage_kind="chunked"``
        :type file_payload: Dict[str, object]
        :param start: Starting byte offset in the logical file
        :type start: int
        :param length: Number of bytes to read
        :type length: int
        :return: Requested byte range, clamped to the file end
        :rtype: bytes
        :raises IntegrityError: Raised when chunk metadata or pack content is
            inconsistent.
        """

        logical_size = int(file_payload["logical_size"])
        if start >= logical_size or length == 0:
            return b""

        end = min(logical_size, start + length)
        manifest = IndexStore(self._repo_path / "chunks" / "index").read_manifest()
        index_store = IndexStore(self._repo_path / "chunks" / "index")
        pack_store = PackStore(self._repo_path / "chunks" / "packs")

        parts = []
        for raw_chunk in file_payload.get("chunks", []):
            chunk_offset = int(raw_chunk["logical_offset"])
            chunk_size = int(raw_chunk["logical_size"])
            chunk_end = chunk_offset + chunk_size
            if chunk_end <= start or chunk_offset >= end:
                continue

            chunk_id = str(raw_chunk["chunk_id"])
            entry = index_store.lookup(chunk_id, manifest=manifest)
            if entry is None:
                raise IntegrityError("chunk missing from index: %s" % chunk_id)
            if entry.logical_size != chunk_size:
                raise IntegrityError("chunk logical size mismatch")
            chunk_data = pack_store.read_chunk(
                PackChunkLocation(
                    pack_id=entry.pack_id,
                    offset=entry.offset,
                    stored_size=entry.stored_size,
                    logical_size=entry.logical_size,
                )
            )
            if entry.compression != "none":
                raise IntegrityError("unsupported chunk compression: %s" % entry.compression)
            if len(chunk_data) != chunk_size:
                raise IntegrityError("chunk size mismatch")
            chunk_checksum = OBJECT_HASH + ":" + _sha256_hex(chunk_data)
            if chunk_checksum != _integrity_sha256(str(raw_chunk["checksum"])):
                raise IntegrityError("chunk checksum mismatch")
            if entry.checksum != _integrity_sha256(str(raw_chunk["checksum"])):
                raise IntegrityError("chunk index checksum mismatch")

            local_start = max(start, chunk_offset) - chunk_offset
            local_end = min(end, chunk_end) - chunk_offset
            parts.append(chunk_data[local_start:local_end])

        return b"".join(parts)

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
        :raises EntryNotFoundError: Raised when the requested file is absent.
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``filename`` is invalid.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
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

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        resolved_revision = revision or DEFAULT_BRANCH
        normalized_path = _normalize_repo_path(filename)

        with self._read_locked():
            snapshot = self._snapshot_for_revision(resolved_revision)
            try:
                file_object_id = snapshot[normalized_path]
            except KeyError:
                raise EntryNotFoundError("path not found: %s" % normalized_path)

            file_payload = self._read_object_payload("files", file_object_id)
            data = self._read_file_bytes_by_object_id(file_object_id)
            self._materialize_content_pool(file_payload, data)

            if local_dir is not None:
                target_root = Path(local_dir)
                self._validate_detached_target_root(target_root)
                target_path = target_root / normalized_path
                self._ensure_detached_view(target_path, data, file_payload)
                return str(target_path)

            resolved_head = self._resolve_revision(resolved_revision)
            public_head = self._public_commit_oid_or_none(resolved_head)
            view_key = _sha256_hex((((public_head or "") + ":" + normalized_path).encode("utf-8")))
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

    def snapshot_download(
        self,
        revision: Optional[str] = None,
        local_dir: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> str:
        """
        Materialize a detached snapshot directory for a revision.

        The return value intentionally follows the role of
        :func:`huggingface_hub.snapshot_download` while omitting remote-only
        parameters that have no local behavior.

        :param revision: Revision to inspect, defaults to the default branch
        :type revision: Optional[str], optional
        :param local_dir: Optional external directory where the detached
            snapshot should be materialized
        :type local_dir: Optional[str], optional
        :param allow_patterns: Optional allowlist for repo-relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]], optional
        :param ignore_patterns: Optional denylist for repo-relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]], optional
        :return: Filesystem path to the snapshot directory
        :rtype: str
        :raises RevisionNotFoundError: Raised when ``revision`` cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``local_dir`` points into the
            repository root.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     _ = backend.create_commit(
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     path = backend.snapshot_download()
            ...     path.endswith("cache/snapshots/" + path.split("cache/snapshots/")[-1])
            True
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        selected_revision = revision or DEFAULT_BRANCH

        with self._read_locked():
            resolved_head = self._resolve_revision(selected_revision, allow_empty_ref=True)
            public_head = self._public_commit_oid_or_none(resolved_head)
            snapshot = self._snapshot_for_commit(resolved_head)
            selected_paths = _filter_repo_paths(
                sorted(snapshot),
                allow_patterns=allow_patterns,
                ignore_patterns=ignore_patterns,
            )
            normalized_allow = _normalize_glob_patterns(allow_patterns) or []
            normalized_ignore = _normalize_glob_patterns(ignore_patterns) or []

            view_key = _sha256_hex(
                _stable_json_bytes(
                    {
                        "commit_id": public_head,
                        "allow_patterns": normalized_allow,
                        "ignore_patterns": normalized_ignore,
                    }
                )
            )

            if local_dir is None:
                target_root = self._repo_path / "cache" / "snapshots" / view_key
                meta_path = self._repo_path / "cache" / "views" / "snapshots" / (view_key + ".json")
                target_metadata_path = str(target_root.relative_to(self._repo_path))
            else:
                target_root = Path(local_dir)
                self._validate_detached_target_root(target_root)
                meta_path = target_root / ".cache" / "hubvault" / "snapshot.json"
                target_metadata_path = os.path.realpath(str(target_root))

            previous_paths = []
            if meta_path.exists():
                try:
                    previous_meta = _read_json(meta_path)
                    if not isinstance(previous_meta, dict):
                        raise TypeError("snapshot metadata must be a JSON object")
                    raw_files = previous_meta.get("files", [])
                    if not isinstance(raw_files, list):
                        raise TypeError("snapshot metadata files must be a list")
                    previous_paths = [str(item["path"]) for item in raw_files]
                except (AttributeError, KeyError, OSError, TypeError, ValueError) as err:
                    warnings.warn(
                        "Ignoring malformed detached snapshot metadata at %s: %s" % (meta_path, err),
                        RuntimeWarning,
                    )
                    previous_paths = []

            target_root.mkdir(parents=True, exist_ok=True)
            current_paths = set(selected_paths)
            for stale_path in previous_paths:
                if stale_path in current_paths:
                    continue
                self._remove_detached_path(target_root / stale_path, target_root)

            file_entries = []
            for repo_path in selected_paths:
                file_object_id = snapshot[repo_path]
                file_payload = self._read_object_payload("files", file_object_id)
                data = self._read_file_bytes_by_object_id(file_object_id)
                self._materialize_content_pool(file_payload, data)
                self._ensure_detached_view(target_root / repo_path, data, file_payload)
                file_entries.append(
                    {
                        "path": repo_path,
                        "sha256": _public_sha256_hex(str(file_payload["sha256"])),
                        "oid": str(file_payload["oid"]),
                        "size": int(file_payload["logical_size"]),
                    }
                )

            metadata = {
                "view_key": view_key,
                "revision": selected_revision,
                "commit_id": public_head,
                "allow_patterns": normalized_allow,
                "ignore_patterns": normalized_ignore,
                "target_path": target_metadata_path,
                "files": file_entries,
                "created_at": _utc_now(),
            }
            _write_json_atomic(meta_path, metadata)

            if local_dir is not None:
                return os.path.realpath(str(target_root))
            return str(target_root)

    def upload_file(
        self,
        *,
        path_or_fileobj: Union[str, Path, bytes, io.BufferedIOBase],
        path_in_repo: str,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Upload a single file through the public commit API.

        :param path_or_fileobj: File content source
        :type path_or_fileobj: Union[str, pathlib.Path, bytes, io.BufferedIOBase]
        :param path_in_repo: Target repo-relative path
        :type path_in_repo: str
        :param revision: Target branch name, defaults to the default branch
        :type revision: Optional[str], optional
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str], optional
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str], optional
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str], optional
        :return: Public commit metadata for the created commit
        :rtype: CommitInfo

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     info = backend.upload_file(path_or_fileobj=b"hello", path_in_repo="demo.txt")
            ...     info.commit_message
            'Upload demo.txt with hubvault'
        """

        self._ensure_repo()
        repo_config = self._repo_config()
        normalized_path = _normalize_repo_path(path_in_repo)
        selected_revision = revision or str(repo_config["default_branch"])
        commit_info = self.create_commit(
            operations=[CommitOperationAdd(path_in_repo=normalized_path, path_or_fileobj=path_or_fileobj)],
            commit_message=commit_message or "Upload %s with hubvault" % normalized_path,
            commit_description=commit_description,
            revision=selected_revision,
            parent_commit=parent_commit,
        )
        return CommitInfo(
            commit_url=commit_info.commit_url,
            commit_message=commit_info.commit_message,
            commit_description=commit_info.commit_description,
            oid=commit_info.oid,
            pr_url=commit_info.pr_url,
            _url=self._blob_url(selected_revision, normalized_path),
        )

    def upload_folder(
        self,
        *,
        folder_path: Union[str, Path],
        path_in_repo: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
        delete_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> CommitInfo:
        """
        Upload a local folder while preserving its relative layout.

        Any nested ``.git`` directory is ignored automatically, matching the
        broad public behavior of :meth:`huggingface_hub.HfApi.upload_folder`.

        :param folder_path: Local folder to upload
        :type folder_path: Union[str, pathlib.Path]
        :param path_in_repo: Optional target directory in the repo root
        :type path_in_repo: Optional[str], optional
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str], optional
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str], optional
        :param revision: Target branch name, defaults to the default branch
        :type revision: Optional[str], optional
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str], optional
        :param allow_patterns: Optional allowlist for local relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]], optional
        :param ignore_patterns: Optional denylist for local relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]], optional
        :param delete_patterns: Optional denylist applied to already uploaded
            repo files beneath ``path_in_repo`` before new files are added
        :type delete_patterns: Optional[Union[Sequence[str], str]], optional
        :return: Public commit metadata for the created commit
        :rtype: CommitInfo
        :raises ValueError: Raised when ``folder_path`` is not a local
            directory.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     repo_root = Path(tmpdir)
            ...     source = repo_root / "source"
            ...     source.mkdir()
            ...     (source / "demo.txt").write_text("hello", encoding="utf-8")
            ...     backend = RepositoryBackend(repo_root / "repo")
            ...     _ = backend.create_repo()
            ...     info = backend.upload_folder(folder_path=source)
            ...     info.commit_message
            'Upload folder using hubvault'
        """

        self._ensure_repo()
        root = Path(folder_path)
        if not root.is_dir():
            raise ValueError("folder_path must point to an existing local directory")

        repo_config = self._repo_config()
        selected_revision = revision or str(repo_config["default_branch"])
        base_path = "" if path_in_repo in (None, "") else _normalize_repo_path(path_in_repo)

        local_paths = []
        for current_root, dirnames, filenames in os.walk(str(root)):
            dirnames[:] = sorted(name for name in dirnames if name != ".git")
            current_root_path = Path(current_root)
            for filename in sorted(filenames):
                relative_path = (current_root_path / filename).relative_to(root).as_posix()
                local_paths.append(relative_path)

        filtered_local_paths = _filter_repo_paths(
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
            delete_rules = _normalize_glob_patterns(delete_patterns) or []
            target_head = self._resolve_revision(selected_revision, allow_empty_ref=True)
            existing_snapshot = self._snapshot_for_commit(target_head)
            for existing_path in sorted(existing_snapshot):
                relative_existing_path = existing_path
                if base_path:
                    prefix = base_path + "/"
                    if not existing_path.startswith(prefix):
                        continue
                    relative_existing_path = existing_path[len(prefix):]
                if relative_existing_path == ".gitattributes":
                    continue
                if any(fnmatch(relative_existing_path, rule) for rule in delete_rules):
                    delete_operations.append(CommitOperationDelete(path_in_repo=existing_path))

        if add_operations:
            added_paths = {operation.path_in_repo for operation in add_operations}
            delete_operations = [
                operation
                for operation in delete_operations
                if operation.path_in_repo not in added_paths
            ]

        commit_info = self.create_commit(
            operations=delete_operations + add_operations,
            commit_message=commit_message or "Upload folder using hubvault",
            commit_description=commit_description,
            revision=selected_revision,
            parent_commit=parent_commit,
        )
        return CommitInfo(
            commit_url=commit_info.commit_url,
            commit_message=commit_info.commit_message,
            commit_description=commit_info.commit_description,
            oid=commit_info.oid,
            pr_url=commit_info.pr_url,
            _url=self._tree_url(selected_revision, base_path),
        )

    def upload_large_folder(
        self,
        *,
        folder_path: Union[str, Path],
        revision: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> CommitInfo:
        """
        Upload a large local folder through one atomic local commit.

        The method name intentionally follows
        :meth:`huggingface_hub.HfApi.upload_large_folder`, but the local
        repository keeps the operation atomic and therefore returns a single
        :class:`CommitInfo` instead of spreading the upload across multiple
        commits.

        :param folder_path: Local folder to upload
        :type folder_path: Union[str, pathlib.Path]
        :param revision: Target branch name, defaults to the default branch
        :type revision: Optional[str], optional
        :param allow_patterns: Optional allowlist for local relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]], optional
        :param ignore_patterns: Optional denylist for local relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]], optional
        :return: Public commit metadata for the created commit
        :rtype: CommitInfo
        :raises ValueError: Raised when ``folder_path`` is not a local
            directory.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     repo_root = Path(tmpdir)
            ...     source = repo_root / "source"
            ...     source.mkdir()
            ...     (source / "demo.txt").write_text("hello", encoding="utf-8")
            ...     backend = RepositoryBackend(repo_root / "repo")
            ...     _ = backend.create_repo()
            ...     info = backend.upload_large_folder(folder_path=source)
            ...     info.commit_message
            'Upload large folder using hubvault'
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
        )

    def delete_file(
        self,
        path_in_repo: str,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Delete a single file through the public commit API.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Target branch name, defaults to the default branch
        :type revision: Optional[str], optional
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str], optional
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str], optional
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str], optional
        :return: Public commit metadata for the created commit
        :rtype: CommitInfo
        """

        self._ensure_repo()
        repo_config = self._repo_config()
        normalized_path = _normalize_repo_path(path_in_repo)
        return self.create_commit(
            operations=[CommitOperationDelete(path_in_repo=normalized_path, is_folder=False)],
            revision=revision or str(repo_config["default_branch"]),
            commit_message=commit_message or "Delete %s with hubvault" % normalized_path,
            commit_description=commit_description,
            parent_commit=parent_commit,
        )

    def delete_folder(
        self,
        path_in_repo: str,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Delete a folder subtree through the public commit API.

        :param path_in_repo: Repo-relative folder path
        :type path_in_repo: str
        :param revision: Target branch name, defaults to the default branch
        :type revision: Optional[str], optional
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str], optional
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str], optional
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str], optional
        :return: Public commit metadata for the created commit
        :rtype: CommitInfo
        """

        self._ensure_repo()
        repo_config = self._repo_config()
        normalized_path = _normalize_repo_path(path_in_repo)
        return self.create_commit(
            operations=[CommitOperationDelete(path_in_repo=normalized_path, is_folder=True)],
            revision=revision or str(repo_config["default_branch"]),
            commit_message=commit_message or "Delete folder %s with hubvault" % normalized_path,
            commit_description=commit_description,
            parent_commit=parent_commit,
        )

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
        :raises RevisionNotFoundError: Raised when the target revision cannot be
            resolved.
        :raises UnsupportedPathError: Raised when ``ref_name`` violates ref
            naming rules.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     commit = backend.create_commit(
            ...         revision="main",
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     backend.reset_ref("main", commit.oid).oid == commit.oid
            True
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()
            branch_name = _validate_ref_name(ref_name)
            target_commit_id = self._resolve_revision(to_revision)
            old_head = self._read_ref(branch_name)
            txdir = self._create_txdir(branch_name, old_head)
            try:
                result = self._commit_info(target_commit_id, branch_name)
                self._commit_branch_ref_update_unlocked(
                    txdir=txdir,
                    branch_name=branch_name,
                    old_head=old_head,
                    new_head=target_commit_id,
                    message="reset ref",
                    failpoint_prefix="reset_ref",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)
            return result

    def quick_verify(self) -> VerifyReport:
        """
        Perform a minimal repository consistency check.

        The verification pass checks repository format compatibility, validates
        commit closure for all visible refs, and reports stale detached views as
        warnings instead of fatal errors.

        :return: Verification summary for the current repository state
        :rtype: VerifyReport
        :raises RepositoryNotFoundError: Raised when the configured root is not a
            valid repository.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.quick_verify().ok
            True
        """

        self._ensure_repo()
        recovery_error = None
        try:
            self._rollback_interrupted_ref_updates_if_needed()
        except IntegrityError as err:
            recovery_error = err
        with self._read_locked():
            warnings = []
            errors = []
            checked_refs = []
            config = self._repo_config()

            if config.get("format_version") != FORMAT_VERSION:
                errors.append("unsupported format version")
            if recovery_error is not None:
                errors.append("transaction recovery: %s" % recovery_error)

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
                # Detached file views are cache artifacts, not repository truth.
                except (AttributeError, KeyError, OSError, TypeError, ValueError) as err:  # pragma: no cover
                    warnings.append("failed to inspect file view %s: %s" % (view_meta_path.name, err))

            for view_meta_path in sorted((self._repo_path / "cache" / "views" / "snapshots").glob("*.json")):
                try:
                    view_meta = _read_json(view_meta_path)
                    target_root = self._repo_path / str(view_meta["target_path"])
                    for file_info in view_meta.get("files", []):
                        target_path = target_root / str(file_info["path"])
                        if not target_path.exists():
                            warnings.append("stale snapshot view: %s" % view_meta_path.name)
                            break
                        data_sha256 = _sha256_hex(target_path.read_bytes())
                        if data_sha256 != str(file_info["sha256"]):
                            warnings.append("stale snapshot view: %s" % view_meta_path.name)
                            break
                # Detached snapshot views are cache artifacts, not repository truth.
                except (AttributeError, KeyError, OSError, TypeError, ValueError) as err:  # pragma: no cover
                    warnings.append("failed to inspect snapshot view %s: %s" % (view_meta_path.name, err))

            txn_root = self._repo_path / "txn"
            if txn_root.exists():
                for txn_entry in sorted(txn_root.iterdir()):
                    if not txn_entry.is_dir():
                        warnings.append("unexpected txn entry: %s" % txn_entry.name)
                    else:
                        warnings.append("pending transaction directory: %s" % txn_entry.name)

            lock_root = self._repo_path / "locks"
            if lock_root.exists():
                for lock_entry in sorted(lock_root.iterdir()):
                    if lock_entry.name == REPO_LOCK_FILENAME and lock_entry.is_file():
                        continue
                    warnings.append("unexpected lock artifact: %s" % lock_entry.name)

            return VerifyReport(
                ok=not errors,
                checked_refs=checked_refs,
                warnings=warnings,
                errors=errors,
            )

    def full_verify(self) -> VerifyReport:
        """
        Perform a complete repository verification pass.

        The full pass verifies the live ref graph, validates published object
        containers, inspects visible chunk index segments, and reads chunk
        payloads through pack storage so corruption can be localized before
        space-management operations are attempted.

        :return: Verification summary for the current repository state
        :rtype: VerifyReport
        :raises RepositoryNotFoundError: Raised when the configured root is not
            a valid repository.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.full_verify().ok
            True
        """

        self._ensure_repo()
        recovery_error = None
        try:
            self._rollback_interrupted_ref_updates_if_needed()
        except IntegrityError as err:
            recovery_error = err
        with self._read_locked():
            return self._full_verify_unlocked(recovery_error=recovery_error)

    def get_storage_overview(self) -> StorageOverview:
        """
        Analyze repository disk usage and safe reclamation opportunities.

        The report separates immediately reclaimable space from space that is
        still retained for rollback history and therefore requires an explicit
        rewrite such as :meth:`squash_history` before :meth:`gc` can release it.

        :return: Repository storage overview
        :rtype: StorageOverview
        :raises RepositoryNotFoundError: Raised when the configured root is not
            a valid repository.
        :raises IntegrityError: Raised when persisted storage cannot be analyzed
            safely because the live graph is inconsistent.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.get_storage_overview().total_size >= 0
            True
        """

        self._ensure_repo()
        self._rollback_interrupted_ref_updates_if_needed()
        with self._read_locked():
            return self._storage_overview_unlocked()["overview"]

    def gc(self, dry_run: bool = False, prune_cache: bool = True) -> GcReport:
        """
        Reclaim unreachable objects and compact live chunk storage.

        The maintenance pass preserves all currently visible refs, rewrites the
        live chunk set into a compact pack/index view, and optionally prunes the
        rebuildable managed cache directories under ``cache/``.

        :param dry_run: Whether to compute the result without mutating storage
        :type dry_run: bool, optional
        :param prune_cache: Whether rebuildable managed caches should also be
            removed
        :type prune_cache: bool, optional
        :return: Garbage-collection summary
        :rtype: GcReport
        :raises RepositoryNotFoundError: Raised when the configured root is not
            a valid repository.
        :raises VerificationError: Raised when the repository fails full
            verification and therefore cannot be reclaimed safely.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     backend.gc(dry_run=True).dry_run
            True
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()
            return self._gc_unlocked(dry_run=bool(dry_run), prune_cache=bool(prune_cache))

    def squash_history(
        self,
        ref_name: str,
        root_revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        run_gc: bool = True,
        prune_cache: bool = False,
    ) -> SquashReport:
        """
        Rewrite a branch so older history becomes reclaimable.

        The rewritten branch keeps the same visible tip snapshot but the chosen
        root commit becomes a new parentless starting point. Older ancestors on
        that branch therefore become unreachable from the rewritten ref and can
        be reclaimed by a follow-up GC pass.

        :param ref_name: Branch name or full branch ref to rewrite
        :type ref_name: str
        :param root_revision: Oldest commit to preserve on the rewritten branch.
            When omitted, the current branch head is collapsed into a single new
            root commit.
        :type root_revision: Optional[str], optional
        :param commit_message: Optional replacement title for the rewritten root
            commit
        :type commit_message: Optional[str], optional
        :param commit_description: Optional replacement body for the rewritten
            root commit
        :type commit_description: Optional[str], optional
        :param run_gc: Whether to run :meth:`gc` immediately after rewriting
        :type run_gc: bool, optional
        :param prune_cache: Whether the follow-up GC pass should also prune
            managed caches
        :type prune_cache: bool, optional
        :return: History rewrite summary
        :rtype: SquashReport
        :raises ConflictError: Raised when ``root_revision`` is not an ancestor
            of the selected branch head.
        :raises RevisionNotFoundError: Raised when the selected branch or
            revision does not exist.
        :raises UnsupportedPathError: Raised when ``ref_name`` is not a valid
            branch ref.

        Example::

            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     backend = RepositoryBackend(Path(tmpdir) / "repo")
            ...     _ = backend.create_repo()
            ...     commit = backend.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     report = backend.squash_history("main", root_revision=commit.oid, run_gc=False)
            ...     report.ref_name
            'refs/heads/main'
        """

        self._ensure_repo()
        with self._write_locked():
            self._recover_transactions()
            short_branch_name, full_ref_name, old_head = self._resolve_branch_ref_for_squash_unlocked(ref_name)
            lineage = self._commit_lineage_unlocked(old_head)
            if root_revision is None:
                root_commit_before = old_head
                rewrite_lineage = [old_head]
                dropped_ancestor_count = len(lineage) - 1
            else:
                root_commit_before = self._resolve_revision(root_revision)
                if root_commit_before not in lineage:
                    raise ConflictError("root_revision is not an ancestor of the selected branch head")
                index = lineage.index(root_commit_before)
                rewrite_lineage = list(reversed(lineage[:index + 1]))
                dropped_ancestor_count = len(lineage) - (index + 1)

            txdir = self._create_txdir(short_branch_name, old_head)
            try:
                previous_new_commit_id = None
                for position, old_commit_id in enumerate(rewrite_lineage):
                    old_payload = self._read_object_payload("commits", old_commit_id)
                    title, description = self._commit_title_and_description(old_payload)
                    if position == 0:
                        if commit_message is not None:
                            title = str(commit_message)
                        if commit_description is not None:
                            description = str(commit_description)
                        old_payload["title"] = title
                        old_payload["description"] = description
                        old_payload["message"] = self._compose_commit_text(title, description)
                        old_payload["parents"] = []
                    else:
                        old_payload["parents"] = [previous_new_commit_id]
                    old_payload["git_oid"] = _git_commit_oid(
                        tree_oid=self._public_tree_oid(str(old_payload["tree_id"]), txdir=txdir),
                        parent_oids=[
                            self._public_commit_oid(str(parent_id), txdir=txdir)
                            for parent_id in old_payload.get("parents", [])
                        ],
                        message=str(old_payload.get("message", "")),
                        created_at=str(old_payload["created_at"]),
                    )
                    previous_new_commit_id = self._stage_json_object(txdir, "commits", old_payload)

                new_head = previous_new_commit_id
                public_old_head = self._public_commit_oid(old_head)
                public_new_head = self._public_commit_oid(new_head, txdir=txdir)
                public_root_commit_before = self._public_commit_oid(root_commit_before)
                self._write_tx_state(txdir, "STAGED")
                self._publish_staged_objects(txdir)
                self._write_tx_state(txdir, "PUBLISHED_OBJECTS")
                self._maybe_failpoint("squash_history.after_publish")
                self._commit_branch_ref_update_unlocked(
                    txdir=txdir,
                    branch_name=short_branch_name,
                    old_head=old_head,
                    new_head=new_head,
                    message="squash history",
                    failpoint_prefix="squash_history",
                )
            except BaseException:
                self._rollback_transaction_unlocked(txdir)
                raise
            self._safe_cleanup_txdir(txdir)

            blocking_refs = self._blocking_refs_for_lineage_unlocked(
                lineage_set=set(lineage),
                excluded_ref_name=full_ref_name,
            )
            gc_report = None
            if run_gc:
                gc_report = self._gc_unlocked(dry_run=False, prune_cache=prune_cache)

            return SquashReport(
                ref_name=full_ref_name,
                old_head=public_old_head,
                new_head=public_new_head,
                root_commit_before=public_root_commit_before,
                rewritten_commit_count=len(rewrite_lineage),
                dropped_ancestor_count=dropped_ancestor_count,
                blocking_refs=blocking_refs,
                gc_report=gc_report,
            )

    def _full_verify_unlocked(self, recovery_error: Optional[IntegrityError] = None) -> VerifyReport:
        """Build a full verification report while a repo lock is already held."""

        warnings = []
        errors = []
        checked_refs = []
        config = self._repo_config()

        if config.get("format_version") != FORMAT_VERSION:
            errors.append("unsupported format version")
        if recovery_error is not None:
            errors.append("transaction recovery: %s" % recovery_error)

        ref_targets = self._ref_targets_unlocked()
        checked_refs.extend(sorted(ref_targets))
        for ref_name, head in sorted(ref_targets.items()):
            if head is None:
                continue
            try:
                self._verify_commit_closure(head)
            except IntegrityError as err:
                errors.append("%s: %s" % (ref_name, err))

        for object_type in ("commits", "trees", "files", "blobs"):
            for object_id in self._iter_object_ids_unlocked(object_type):
                try:
                    self._verify_object_container_unlocked(object_type, object_id)
                except IntegrityError as err:
                    errors.append("%s %s: %s" % (object_type[:-1], object_id, err))

        try:
            manifest = IndexStore(self._repo_path / "chunks" / "index").read_manifest()
            pack_store = PackStore(self._repo_path / "chunks" / "packs")
            index_store = IndexStore(self._repo_path / "chunks" / "index")
            for level in ("L0", "L1", "L2"):
                for segment_name in manifest.levels.get(level, tuple()):
                    entries = index_store.load_segment(level, segment_name)
                    for entry in entries:
                        chunk_data = pack_store.read_chunk(
                            PackChunkLocation(
                                pack_id=entry.pack_id,
                                offset=entry.offset,
                                stored_size=entry.stored_size,
                                logical_size=entry.logical_size,
                            )
                        )
                        if entry.compression != "none":
                            raise IntegrityError("unsupported chunk compression: %s" % entry.compression)
                        if len(chunk_data) != entry.logical_size:
                            raise IntegrityError("chunk size mismatch")
                        checksum = OBJECT_HASH + ":" + _sha256_hex(chunk_data)
                        if checksum != entry.checksum:
                            raise IntegrityError("chunk checksum mismatch")
        except IntegrityError as err:
            errors.append("chunk storage: %s" % err)

        for view_meta_path in sorted((self._repo_path / "cache" / "views" / "files").glob("*.json")):
            try:
                view_meta = _read_json(view_meta_path)
                target_path = self._repo_path / str(view_meta["target_path"])
                if target_path.exists():
                    data_sha256 = _sha256_hex(target_path.read_bytes())
                    if data_sha256 != _public_sha256_hex(str(view_meta["sha256"])):
                        warnings.append("stale file view: %s" % view_meta_path.name)
            except (AttributeError, KeyError, OSError, TypeError, ValueError) as err:  # pragma: no cover
                warnings.append("failed to inspect file view %s: %s" % (view_meta_path.name, err))

        for view_meta_path in sorted((self._repo_path / "cache" / "views" / "snapshots").glob("*.json")):
            try:
                view_meta = _read_json(view_meta_path)
                target_root = self._repo_path / str(view_meta["target_path"])
                for file_info in view_meta.get("files", []):
                    target_path = target_root / str(file_info["path"])
                    if not target_path.exists():
                        warnings.append("stale snapshot view: %s" % view_meta_path.name)
                        break
                    data_sha256 = _sha256_hex(target_path.read_bytes())
                    if data_sha256 != str(file_info["sha256"]):
                        warnings.append("stale snapshot view: %s" % view_meta_path.name)
                        break
            except (AttributeError, KeyError, OSError, TypeError, ValueError) as err:  # pragma: no cover
                warnings.append("failed to inspect snapshot view %s: %s" % (view_meta_path.name, err))

        txn_root = self._repo_path / "txn"
        if txn_root.exists():
            for txn_entry in sorted(txn_root.iterdir()):
                if not txn_entry.is_dir():
                    warnings.append("unexpected txn entry: %s" % txn_entry.name)
                else:
                    warnings.append("pending transaction directory: %s" % txn_entry.name)

        lock_root = self._repo_path / "locks"
        if lock_root.exists():
            for lock_entry in sorted(lock_root.iterdir()):
                if lock_entry.name == REPO_LOCK_FILENAME and lock_entry.is_file():
                    continue
                warnings.append("unexpected lock artifact: %s" % lock_entry.name)

        return VerifyReport(
            ok=not errors,
            checked_refs=checked_refs,
            warnings=warnings,
            errors=errors,
        )

    def _storage_overview_unlocked(self) -> Dict[str, object]:
        """Build storage-analysis data while a repo lock is already held."""

        ref_targets = self._ref_targets_unlocked()
        live_heads = [head for head in ref_targets.values() if head is not None]
        live_state = self._collect_graph_state_unlocked(live_heads, include_parents=True)
        tip_state = self._collect_graph_state_unlocked(live_heads, include_parents=False)

        object_type_to_state_key = {
            "commits": "commits",
            "trees": "trees",
            "files": "files",
            "blobs": "blobs",
        }
        object_sizes = {}
        live_object_bytes = {}
        tip_object_bytes = {}
        unreachable_object_bytes = {}
        actual_object_bytes = {}
        for object_type, state_key in object_type_to_state_key.items():
            all_ids = set(self._iter_object_ids_unlocked(object_type))
            size_map = dict((object_id, self._object_disk_size_unlocked(object_type, object_id)) for object_id in all_ids)
            object_sizes[object_type] = size_map
            live_ids = live_state[state_key]
            tip_ids = tip_state[state_key]
            live_object_bytes[object_type] = sum(size_map.get(object_id, 0) for object_id in live_ids)
            tip_object_bytes[object_type] = sum(size_map.get(object_id, 0) for object_id in tip_ids)
            unreachable_object_bytes[object_type] = sum(
                size_map.get(object_id, 0) for object_id in (all_ids - live_ids)
            )
            actual_object_bytes[object_type] = sum(size_map.values())

        live_chunk_plan = self._chunk_storage_plan_unlocked(
            live_state["chunk_ids"],
            pack_id=GC_ANALYSIS_PACK_ID,
            with_data=False,
        )
        tip_chunk_plan = self._chunk_storage_plan_unlocked(
            tip_state["chunk_ids"],
            pack_id=GC_ANALYSIS_PACK_ID,
            with_data=False,
        )
        live_chunk_bytes = int(live_chunk_plan["pack_size"]) + int(live_chunk_plan["index_total_size"])
        tip_chunk_bytes = int(tip_chunk_plan["pack_size"]) + int(tip_chunk_plan["index_total_size"])

        metadata_size = (
            _path_metrics(self._format_path)[0]
            + _path_metrics(self._repo_config_path)[0]
            + _path_metrics(self._repo_path / "refs")[0]
            + _path_metrics(self._repo_path / "logs" / "refs")[0]
            + _path_metrics(self._repo_path / "locks")[0]
        )
        actual_pack_bytes, actual_pack_files = _path_metrics(self._repo_path / "chunks" / "packs")
        actual_index_bytes, actual_index_files = _path_metrics(self._repo_path / "chunks" / "index")
        cache_size, cache_files = _path_metrics(self._repo_path / "cache")
        quarantine_size, quarantine_files = _path_metrics(self._repo_path / "quarantine")
        txn_size, txn_files = _path_metrics(self._repo_path / "txn")
        total_size, _ = _path_metrics(self._repo_path)

        historical_object_bytes = sum(
            max(0, int(live_object_bytes[object_type]) - int(tip_object_bytes[object_type]))
            for object_type in object_type_to_state_key
        )
        historical_chunk_bytes = max(0, live_chunk_bytes - tip_chunk_bytes)
        reclaimable_gc_size = (
            sum(unreachable_object_bytes.values())
            + max(0, actual_pack_bytes + actual_index_bytes - live_chunk_bytes)
        )
        reachable_size = metadata_size + sum(live_object_bytes.values()) + live_chunk_bytes
        historical_retained_size = historical_object_bytes + historical_chunk_bytes

        recommendations = []
        if reclaimable_gc_size > 0:
            recommendations.append(
                "Run gc() to reclaim about %s of unreachable objects and stale chunk storage."
                % _format_bytes(reclaimable_gc_size)
            )
        if cache_size > 0:
            recommendations.append(
                "Managed cache directories account for about %s; run gc(prune_cache=True) to rebuild them on demand."
                % _format_bytes(cache_size)
            )
        if historical_retained_size > 0:
            recommendations.append(
                "About %s is retained only for rollback/history; use squash_history(...) before gc() if you want to free it."
                % _format_bytes(historical_retained_size)
            )
        if txn_size > 0:
            recommendations.append(
                "The txn/ area still contains %s of leftovers; inspect it before deleting because it may include unexpected manual files."
                % _format_bytes(txn_size)
            )
        if quarantine_size > 0:
            recommendations.append(
                "The quarantine/ area already contains %s of previously isolated data and can be cleaned by gc()."
                % _format_bytes(quarantine_size)
            )
        if not recommendations:
            recommendations.append("No immediate storage maintenance action is needed.")

        sections = [
            StorageSectionInfo(
                name="repo.metadata",
                path="FORMAT + repo.json + refs/ + logs/refs/ + locks/",
                total_size=metadata_size,
                file_count=(
                    _path_metrics(self._format_path)[1]
                    + _path_metrics(self._repo_config_path)[1]
                    + _path_metrics(self._repo_path / "refs")[1]
                    + _path_metrics(self._repo_path / "logs" / "refs")[1]
                    + _path_metrics(self._repo_path / "locks")[1]
                ),
                reclaimable_size=0,
                reclaim_strategy="keep",
                notes="Core repository metadata and lock files required for normal operation.",
            ),
            StorageSectionInfo(
                name="objects.commits",
                path="objects/commits/",
                total_size=actual_object_bytes["commits"],
                file_count=len(object_sizes["commits"]),
                reclaimable_size=unreachable_object_bytes["commits"],
                reclaim_strategy="gc",
                notes="Commit containers; unreachable ones are removed by gc(), while reachable historical ones require squash_history().",
            ),
            StorageSectionInfo(
                name="objects.trees",
                path="objects/trees/",
                total_size=actual_object_bytes["trees"],
                file_count=len(object_sizes["trees"]),
                reclaimable_size=unreachable_object_bytes["trees"],
                reclaim_strategy="gc",
                notes="Tree containers for directory snapshots.",
            ),
            StorageSectionInfo(
                name="objects.files",
                path="objects/files/",
                total_size=actual_object_bytes["files"],
                file_count=len(object_sizes["files"]),
                reclaimable_size=unreachable_object_bytes["files"],
                reclaim_strategy="gc",
                notes="File metadata objects; older live versions are counted under historical_retained_size until history is squashed.",
            ),
            StorageSectionInfo(
                name="objects.blobs.meta",
                path="objects/blobs/*.meta.json",
                total_size=sum(
                    self._blob_meta_path(object_id).stat().st_size
                    for object_id in object_sizes["blobs"]
                    if self._blob_meta_path(object_id).exists()
                ),
                file_count=len(object_sizes["blobs"]),
                reclaimable_size=0,
                reclaim_strategy="gc",
                notes="Blob metadata sidecars. Their reclaimable bytes are tied to blob payload reclamation below.",
            ),
            StorageSectionInfo(
                name="objects.blobs.data",
                path="objects/blobs/*.data",
                total_size=sum(
                    self._blob_data_path(object_id).stat().st_size
                    for object_id in object_sizes["blobs"]
                    if self._blob_data_path(object_id).exists()
                ),
                file_count=len(object_sizes["blobs"]),
                reclaimable_size=unreachable_object_bytes["blobs"],
                reclaim_strategy="gc",
                notes="Whole-file blob payloads.",
            ),
            StorageSectionInfo(
                name="chunks.packs",
                path="chunks/packs/",
                total_size=actual_pack_bytes,
                file_count=actual_pack_files,
                reclaimable_size=max(0, actual_pack_bytes - int(live_chunk_plan["pack_size"])),
                reclaim_strategy="gc",
                notes="Chunk pack files. gc() rewrites live chunks into a compact pack layout before deleting old packs.",
            ),
            StorageSectionInfo(
                name="chunks.index",
                path="chunks/index/",
                total_size=actual_index_bytes,
                file_count=actual_index_files,
                reclaimable_size=max(0, actual_index_bytes - int(live_chunk_plan["index_total_size"])),
                reclaim_strategy="gc",
                notes="Visible manifest plus immutable index segments for chunk lookups.",
            ),
            StorageSectionInfo(
                name="cache",
                path="cache/",
                total_size=cache_size,
                file_count=cache_files,
                reclaimable_size=cache_size,
                reclaim_strategy="prune-cache",
                notes="Managed detached downloads and snapshots that can be rebuilt without changing committed data.",
            ),
            StorageSectionInfo(
                name="txn",
                path="txn/",
                total_size=txn_size,
                file_count=txn_files,
                reclaimable_size=0,
                reclaim_strategy="manual-review",
                notes="Transaction leftovers should normally be empty after recovery; inspect before manual removal.",
            ),
            StorageSectionInfo(
                name="quarantine",
                path="quarantine/",
                total_size=quarantine_size,
                file_count=quarantine_files,
                reclaimable_size=quarantine_size,
                reclaim_strategy="gc",
                notes="Previously isolated files awaiting final deletion.",
            ),
        ]

        overview = StorageOverview(
            total_size=total_size,
            reachable_size=reachable_size,
            historical_retained_size=historical_retained_size,
            reclaimable_gc_size=reclaimable_gc_size,
            reclaimable_cache_size=cache_size,
            reclaimable_temporary_size=quarantine_size,
            sections=sections,
            recommendations=recommendations,
        )
        return {
            "overview": overview,
            "checked_refs": sorted(ref_targets),
            "live_chunk_plan": live_chunk_plan,
            "object_sizes": object_sizes,
            "live_state": live_state,
            "tip_state": tip_state,
            "unreachable_object_ids": dict(
                (object_type, set(object_sizes[object_type]) - live_state[state_key])
                for object_type, state_key in object_type_to_state_key.items()
            ),
            "quarantine_size": quarantine_size,
            "quarantine_file_count": quarantine_files,
        }

    def _gc_unlocked(self, dry_run: bool, prune_cache: bool) -> GcReport:
        """Run GC while the exclusive repository lock is already held."""

        verify_report = self._full_verify_unlocked()
        if not verify_report.ok:
            raise VerificationError("repository verification failed: %s" % verify_report.errors[0])

        state = self._storage_overview_unlocked()
        overview = state["overview"]
        live_chunk_plan = state["live_chunk_plan"]
        unreachable_object_ids = state["unreachable_object_ids"]
        object_sizes = state["object_sizes"]

        actual_chunk_reclaimable = (
            max(0, _path_metrics(self._repo_path / "chunks" / "packs")[0] - int(live_chunk_plan["pack_size"]))
            + max(0, _path_metrics(self._repo_path / "chunks" / "index")[0] - int(live_chunk_plan["index_total_size"]))
        )
        cache_size = overview.reclaimable_cache_size if prune_cache else 0
        temporary_size = int(state["quarantine_size"])
        reclaimable_size = overview.reclaimable_gc_size + cache_size + temporary_size
        reclaimed_object_size_estimate = 0
        removed_file_count = 0
        for object_type in ("commits", "trees", "files"):
            reclaimed_object_size_estimate += sum(
                object_sizes[object_type].get(object_id, 0) for object_id in unreachable_object_ids[object_type]
            )
            removed_file_count += len(unreachable_object_ids[object_type])
        for object_id in unreachable_object_ids["blobs"]:
            reclaimed_object_size_estimate += object_sizes["blobs"].get(object_id, 0)
            if self._blob_meta_path(object_id).exists():
                removed_file_count += 1
            if self._blob_data_path(object_id).exists():
                removed_file_count += 1
        if prune_cache:
            removed_file_count += _path_metrics(self._repo_path / "cache")[1]
        removed_file_count += int(state["quarantine_file_count"])
        current_pack_file_count = _path_metrics(self._repo_path / "chunks" / "packs")[1]
        current_index_file_count = _path_metrics(self._repo_path / "chunks" / "index")[1]
        removed_file_count += max(0, current_pack_file_count - (1 if live_chunk_plan["index_entries"] else 0))
        removed_file_count += max(0, current_index_file_count - (2 if live_chunk_plan["index_entries"] else 1))

        notes = []
        if overview.historical_retained_size > 0:
            notes.append(
                "Rollback history still retains about %s; use squash_history(...) to make that space reclaimable."
                % _format_bytes(overview.historical_retained_size)
            )
        if dry_run:
            notes.append("dry-run: no files were modified")
            return GcReport(
                dry_run=True,
                checked_refs=state["checked_refs"],
                reclaimed_size=reclaimable_size,
                reclaimed_object_size=reclaimed_object_size_estimate,
                reclaimed_chunk_size=actual_chunk_reclaimable,
                reclaimed_cache_size=cache_size,
                reclaimed_temporary_size=temporary_size,
                removed_file_count=removed_file_count,
                notes=notes,
            )

        txdir = self._create_txdir("gc", None)
        gcid = txdir.name
        try:
            write_chunk_plan = self._chunk_storage_plan_unlocked(
                state["live_state"]["chunk_ids"],
                pack_id="gc-%s" % gcid,
                with_data=True,
            )
            live_index_entries = list(write_chunk_plan["index_entries"])
            if live_index_entries:
                pack_id = "gc-%s" % gcid
                pack_payloads = write_chunk_plan["pack_payloads"]
                PackStore(txdir / "chunks" / "packs").write_pack(pack_id, pack_payloads)
                segment_name = "seg-%s.idx" % pack_id
                staged_index = IndexStore(txdir / "chunks" / "index")
                remapped_entries = []
                running_offset = len(b"hubvault-pack/v1\n")
                for entry, payload in zip(live_index_entries, pack_payloads):
                    remapped_entries.append(
                        IndexEntry(
                            chunk_id=entry.chunk_id,
                            pack_id=pack_id,
                            offset=running_offset,
                            stored_size=len(payload),
                            logical_size=entry.logical_size,
                            compression=entry.compression,
                            checksum=entry.checksum,
                        )
                    )
                    running_offset += len(payload)
                staged_index.write_segment("L0", segment_name, remapped_entries)
                staged_index.write_manifest(IndexManifest.empty().add_segment("L0", segment_name))
            else:
                IndexStore(txdir / "chunks" / "index").write_manifest(IndexManifest.empty())

            self._write_tx_state(txdir, "STAGED")
            self._publish_staged_objects(txdir)
            self._write_tx_state(txdir, "PUBLISHED_OBJECTS")
            self._maybe_failpoint("gc.after_publish")
            self._write_tx_state(txdir, "COMMITTED")
        except BaseException:
            self._rollback_transaction_unlocked(txdir)
            raise
        self._safe_cleanup_txdir(txdir)

        q_objects_root = self._repo_path / "quarantine" / "objects" / gcid
        q_packs_root = self._repo_path / "quarantine" / "packs" / gcid
        q_index_root = self._repo_path / "quarantine" / "manifests" / gcid
        reclaimed_object_size = 0
        reclaimed_chunk_size = 0

        for object_type in ("commits", "trees", "files"):
            for object_id in sorted(unreachable_object_ids[object_type]):
                path = self._object_json_path(object_type, object_id)
                reclaimed_object_size += self._quarantine_move_file_unlocked(
                    source_path=path,
                    quarantine_root=q_objects_root,
                    relative_root=self._repo_path / "objects",
                )

        for object_id in sorted(unreachable_object_ids["blobs"]):
            reclaimed_object_size += self._quarantine_move_file_unlocked(
                source_path=self._blob_meta_path(object_id),
                quarantine_root=q_objects_root,
                relative_root=self._repo_path / "objects",
            )
            reclaimed_object_size += self._quarantine_move_file_unlocked(
                source_path=self._blob_data_path(object_id),
                quarantine_root=q_objects_root,
                relative_root=self._repo_path / "objects",
            )

        live_pack_name = None
        live_segment_name = None
        if live_chunk_plan["index_entries"]:
            live_pack_name = "gc-%s.pack" % gcid
            live_segment_name = "seg-gc-%s.idx" % gcid

        for path in sorted((self._repo_path / "chunks" / "packs").glob("*.pack")):
            if live_pack_name is not None and path.name == live_pack_name:
                continue
            reclaimed_chunk_size += self._quarantine_move_file_unlocked(
                source_path=path,
                quarantine_root=q_packs_root,
                relative_root=self._repo_path / "chunks" / "packs",
            )

        for level in ("L0", "L1", "L2"):
            for path in sorted((self._repo_path / "chunks" / "index" / level).glob("*.idx")):
                if live_segment_name is not None and level == "L0" and path.name == live_segment_name:
                    continue
                reclaimed_chunk_size += self._quarantine_move_file_unlocked(
                    source_path=path,
                    quarantine_root=q_index_root,
                    relative_root=self._repo_path / "chunks" / "index",
                )

        reclaimed_cache_size = 0
        if prune_cache:
            reclaimed_cache_size = self._clear_directory_children_unlocked(self._repo_path / "cache")

        self._clear_directory_children_unlocked(self._repo_path / "quarantine" / "objects")
        self._clear_directory_children_unlocked(self._repo_path / "quarantine" / "packs")
        self._clear_directory_children_unlocked(self._repo_path / "quarantine" / "manifests")

        return GcReport(
            dry_run=False,
            checked_refs=state["checked_refs"],
            reclaimed_size=reclaimed_object_size + reclaimed_chunk_size + reclaimed_cache_size + temporary_size,
            reclaimed_object_size=reclaimed_object_size,
            reclaimed_chunk_size=reclaimed_chunk_size,
            reclaimed_cache_size=reclaimed_cache_size,
            reclaimed_temporary_size=temporary_size,
            removed_file_count=removed_file_count,
            notes=notes,
        )

    def _ref_targets_unlocked(self) -> Dict[str, Optional[str]]:
        """Return all visible branch and tag heads while a repo lock is held."""

        targets = {}
        for branch_name in self._list_branch_names():
            targets["refs/heads/" + branch_name] = self._read_ref(branch_name)
        for tag_name in self._list_tag_names():
            targets["refs/tags/" + tag_name] = self._read_tag_ref(tag_name)
        return targets

    def _resolve_branch_ref_for_squash_unlocked(self, ref_name: str) -> Tuple[str, str, str]:
        """Resolve a branch ref for history rewriting."""

        if ref_name.startswith("refs/tags/"):
            raise UnsupportedPathError("squash_history only supports branch refs")
        if ref_name.startswith("refs/heads/"):
            branch_name = _validate_ref_name(ref_name.split("/", 2)[-1])
        else:
            branch_name = _validate_ref_name(ref_name)
        head = self._read_ref(branch_name)
        if head is None:
            raise RevisionNotFoundError("revision has no commits yet: %s" % branch_name)
        return branch_name, "refs/heads/" + branch_name, head

    def _resolve_target_branch_name_unlocked(self, revision: str) -> str:
        """Resolve a merge target to an existing branch name."""

        text = str(revision)
        if text.startswith(OBJECT_HASH + ":") or text.startswith("refs/tags/") or GIT_OID_PATTERN.fullmatch(text):
            raise UnsupportedPathError("merge target must be a branch ref")
        if text.startswith("refs/heads/"):
            branch_name = _validate_ref_name(text.split("/", 2)[-1])
        else:
            branch_name = _validate_ref_name(text)
        self._read_ref(branch_name)
        return branch_name

    @staticmethod
    def _default_merge_title(source_revision: str, target_branch_name: str) -> str:
        """Build the default merge-commit or merge-reflog title."""

        return "Merge %s into %s" % (source_revision, target_branch_name)

    def _commit_lineage_unlocked(self, head_commit_id: str) -> List[str]:
        """Return the first-parent lineage from a head commit back to the root."""

        lineage = []
        current_commit_id = head_commit_id
        seen = set()
        while current_commit_id is not None and current_commit_id not in seen:
            seen.add(current_commit_id)
            lineage.append(current_commit_id)
            commit_payload = self._read_object_payload("commits", current_commit_id)
            parents = list(commit_payload.get("parents", []))
            current_commit_id = str(parents[0]) if parents else None
        return lineage

    def _reachable_commit_order_unlocked(self, head_commit_id: str) -> List[str]:
        """Return a stable parent-first traversal order for reachable commits."""

        ordered = []
        seen = set()
        stack = [head_commit_id]
        while stack:
            current_commit_id = stack.pop()
            if current_commit_id is None or current_commit_id in seen:
                continue
            seen.add(current_commit_id)
            ordered.append(current_commit_id)
            payload = self._read_object_payload("commits", current_commit_id)
            parents = [str(parent_id) for parent_id in payload.get("parents", [])]
            stack.extend(reversed(parents))
        return ordered

    def _ancestor_distances_unlocked(self, commit_id: Optional[str]) -> Dict[str, int]:
        """Return the shortest parent-distance from a commit to each ancestor."""

        if commit_id is None:
            return {}
        distances = {}
        pending = [(commit_id, 0)]
        while pending:
            current_commit_id, distance = pending.pop(0)
            previous = distances.get(current_commit_id)
            if previous is not None and previous <= distance:
                continue
            distances[current_commit_id] = distance
            payload = self._read_object_payload("commits", current_commit_id)
            pending.extend((str(parent_id), distance + 1) for parent_id in payload.get("parents", []))
        return distances

    def _is_ancestor_unlocked(self, ancestor_commit_id: Optional[str], descendant_commit_id: Optional[str]) -> bool:
        """Return whether one commit is reachable from another through parents."""

        if ancestor_commit_id is None or descendant_commit_id is None:
            return False
        return ancestor_commit_id in self._ancestor_distances_unlocked(descendant_commit_id)

    def _find_merge_base_unlocked(
        self,
        target_commit_id: Optional[str],
        source_commit_id: Optional[str],
    ) -> Optional[str]:
        """Resolve the nearest common ancestor used as the merge base."""

        if target_commit_id is None or source_commit_id is None:
            return None
        target_distances = self._ancestor_distances_unlocked(target_commit_id)
        source_distances = self._ancestor_distances_unlocked(source_commit_id)
        candidates = set(target_distances).intersection(source_distances)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda commit_id: (
                target_distances[commit_id] + source_distances[commit_id],
                max(target_distances[commit_id], source_distances[commit_id]),
                commit_id,
            ),
        )

    def _file_identity_unlocked(
        self,
        file_object_id: Optional[str],
        cache: Dict[str, Tuple[str, int, str]],
    ) -> Optional[Tuple[str, int, str]]:
        """Return a stable logical identity tuple for a file object."""

        if file_object_id is None:
            return None
        identity = cache.get(file_object_id)
        if identity is not None:
            return identity
        payload = self._read_object_payload("files", file_object_id)
        identity = (
            _public_sha256_hex(str(payload["sha256"])),
            int(payload["logical_size"]),
            str(payload["oid"]),
        )
        cache[file_object_id] = identity
        return identity

    def _same_file_version_unlocked(
        self,
        left_file_object_id: Optional[str],
        right_file_object_id: Optional[str],
        cache: Dict[str, Tuple[str, int, str]],
    ) -> bool:
        """Return whether two snapshot entries represent the same logical file."""

        return self._file_identity_unlocked(left_file_object_id, cache) == self._file_identity_unlocked(
            right_file_object_id,
            cache,
        )

    def _make_merge_conflict_unlocked(
        self,
        path: str,
        conflict_type: str,
        message: str,
        base_file_object_id: Optional[str],
        target_file_object_id: Optional[str],
        source_file_object_id: Optional[str],
        identity_cache: Dict[str, Tuple[str, int, str]],
        related_path: Optional[str] = None,
    ) -> MergeConflict:
        """Build a public merge-conflict entry from file-object identifiers."""

        base_identity = self._file_identity_unlocked(base_file_object_id, identity_cache)
        target_identity = self._file_identity_unlocked(target_file_object_id, identity_cache)
        source_identity = self._file_identity_unlocked(source_file_object_id, identity_cache)
        return MergeConflict(
            path=path,
            conflict_type=conflict_type,
            message=message,
            base_oid=base_identity[2] if base_identity is not None else None,
            target_oid=target_identity[2] if target_identity is not None else None,
            source_oid=source_identity[2] if source_identity is not None else None,
            related_path=related_path,
        )

    def _merge_structural_conflicts_unlocked(self, snapshot: Dict[str, str]) -> List[MergeConflict]:
        """Return structural conflicts for a merged snapshot candidate."""

        conflicts = []
        seen_pairs = set()
        seen_per_dir = {}
        for path in sorted(snapshot):
            parts = path.split("/")
            for index in range(1, len(parts)):
                prefix = "/".join(parts[:index])
                if prefix in snapshot:
                    key = (prefix, path, "file/directory")
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    conflicts.append(
                        MergeConflict(
                            path=prefix,
                            conflict_type="file/directory",
                            message="file and directory paths conflict",
                            base_oid=None,
                            target_oid=None,
                            source_oid=None,
                            related_path=path,
                        )
                    )

            parent = "/".join(parts[:-1])
            directory_entries = seen_per_dir.setdefault(parent, {})
            folded = parts[-1].casefold()
            if folded in directory_entries and directory_entries[folded] != parts[-1]:
                other_name = directory_entries[folded]
                other_path = other_name if not parent else parent + "/" + other_name
                key = tuple(sorted((other_path, path)) + ["case-fold"])
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    conflicts.append(
                        MergeConflict(
                            path=other_path,
                            conflict_type="case-fold",
                            message="case-insensitive path conflict",
                            base_oid=None,
                            target_oid=None,
                            source_oid=None,
                            related_path=path,
                        )
                    )
            directory_entries[folded] = parts[-1]
        return conflicts

    def _merge_snapshots_unlocked(
        self,
        base_snapshot: Dict[str, str],
        target_snapshot: Dict[str, str],
        source_snapshot: Dict[str, str],
    ) -> Tuple[Dict[str, str], List[MergeConflict]]:
        """Three-way merge flat snapshots and return merged paths plus conflicts."""

        identity_cache = {}
        merged_snapshot = {}
        conflicts = []
        for path in sorted(set(base_snapshot).union(target_snapshot).union(source_snapshot)):
            base_file_object_id = base_snapshot.get(path)
            target_file_object_id = target_snapshot.get(path)
            source_file_object_id = source_snapshot.get(path)

            if self._same_file_version_unlocked(target_file_object_id, source_file_object_id, identity_cache):
                if target_file_object_id is not None:
                    merged_snapshot[path] = target_file_object_id
                continue

            if self._same_file_version_unlocked(base_file_object_id, target_file_object_id, identity_cache):
                if source_file_object_id is not None:
                    merged_snapshot[path] = source_file_object_id
                continue

            if self._same_file_version_unlocked(base_file_object_id, source_file_object_id, identity_cache):
                if target_file_object_id is not None:
                    merged_snapshot[path] = target_file_object_id
                continue

            if base_file_object_id is None:
                conflict_type = "add/add"
                message = "Both sides added %s differently." % path
            elif target_file_object_id is None or source_file_object_id is None:
                conflict_type = "delete/modify"
                message = "One side deleted %s while the other changed it." % path
            else:
                conflict_type = "modify/modify"
                message = "Both sides changed %s differently." % path
            conflicts.append(
                self._make_merge_conflict_unlocked(
                    path=path,
                    conflict_type=conflict_type,
                    message=message,
                    base_file_object_id=base_file_object_id,
                    target_file_object_id=target_file_object_id,
                    source_file_object_id=source_file_object_id,
                    identity_cache=identity_cache,
                )
            )

        if conflicts:
            return {}, conflicts

        structural_conflicts = self._merge_structural_conflicts_unlocked(merged_snapshot)
        if structural_conflicts:
            return {}, structural_conflicts
        return merged_snapshot, []

    def _collect_graph_state_unlocked(self, commit_ids: Sequence[str], include_parents: bool) -> Dict[str, set]:
        """Collect reachable commit/tree/file/blob/chunk identifiers."""

        state = {
            "commits": set(),
            "trees": set(),
            "files": set(),
            "blobs": set(),
            "chunk_ids": set(),
        }
        pending = [commit_id for commit_id in commit_ids if commit_id is not None]
        while pending:
            commit_id = pending.pop()
            if commit_id in state["commits"]:
                continue
            state["commits"].add(commit_id)
            payload = self._read_object_payload("commits", commit_id)
            self._walk_tree_graph_unlocked(str(payload["tree_id"]), state)
            if include_parents:
                pending.extend(str(parent_id) for parent_id in payload.get("parents", []))
        return state

    def _walk_tree_graph_unlocked(self, tree_id: str, state: Dict[str, set]) -> None:
        """Walk a tree object into the graph state collector."""

        if tree_id in state["trees"]:
            return
        state["trees"].add(tree_id)
        payload = self._read_object_payload("trees", tree_id)
        for entry in payload.get("entries", []):
            if entry["entry_type"] == "tree":
                self._walk_tree_graph_unlocked(str(entry["object_id"]), state)
                continue
            if entry["entry_type"] != "file":
                raise IntegrityError("unknown tree entry type")
            file_object_id = str(entry["object_id"])
            if file_object_id in state["files"]:
                continue
            state["files"].add(file_object_id)
            file_payload = self._read_object_payload("files", file_object_id)
            if str(file_payload.get("storage_kind")) == "chunked":
                for chunk in file_payload.get("chunks", []):
                    state["chunk_ids"].add(str(chunk["chunk_id"]))
            else:
                state["blobs"].add(str(file_payload["content_object_id"]))

    def _iter_object_ids_unlocked(self, object_type: str) -> List[str]:
        """List published object identifiers for a logical object type."""

        root = self._repo_path / "objects" / object_type / OBJECT_HASH
        if not root.exists():
            return []
        if object_type == "blobs":
            suffix = ".meta.json"
        else:
            suffix = ".json"
        object_ids = []
        for prefix_root in sorted(root.iterdir()):
            if not prefix_root.is_dir():
                continue
            for path in sorted(prefix_root.glob("*" + suffix)):
                digest = prefix_root.name + path.name[:-len(suffix)]
                object_ids.append(OBJECT_HASH + ":" + digest)
        return object_ids

    def _object_disk_size_unlocked(self, object_type: str, object_id: str) -> int:
        """Return the current on-disk byte size for one published object."""

        if object_type == "blobs":
            size = 0
            meta_path = self._blob_meta_path(object_id)
            data_path = self._blob_data_path(object_id)
            if meta_path.exists():
                size += meta_path.stat().st_size
            if data_path.exists():
                size += data_path.stat().st_size
            return size
        path = self._object_json_path(object_type, object_id)
        if not path.exists():
            return 0
        return path.stat().st_size

    def _verify_object_container_unlocked(self, object_type: str, object_id: str) -> None:
        """Verify a published object container and its canonical checksum."""

        expected_type = "blob" if object_type == "blobs" else object_type[:-1]
        if object_type == "blobs":
            path = self._blob_meta_path(object_id)
        else:
            path = self._object_json_path(object_type, object_id)
        container = _read_json(path)
        if not isinstance(container, dict) or "payload" not in container:
            raise IntegrityError("invalid object container")
        if int(container.get("format_version", 0)) != FORMAT_VERSION:
            raise IntegrityError("unsupported object format version")
        if str(container.get("object_type")) != expected_type:
            raise IntegrityError("unexpected object type")
        payload_checksum = OBJECT_HASH + ":" + _sha256_hex(_stable_json_bytes(container["payload"]))
        if str(container.get("payload_sha256")) != payload_checksum:
            raise IntegrityError("payload checksum mismatch")
        computed_object_id, _ = _object_id_from_container(container)
        if computed_object_id != object_id:
            raise IntegrityError("object id mismatch")

    def _chunk_storage_plan_unlocked(self, chunk_ids: Sequence[str], pack_id: str, with_data: bool) -> Dict[str, object]:
        """Build a deterministic compacted chunk-storage plan for a chunk-id set."""

        manifest = IndexStore(self._repo_path / "chunks" / "index").read_manifest()
        index_store = IndexStore(self._repo_path / "chunks" / "index")
        pack_store = PackStore(self._repo_path / "chunks" / "packs")
        ordered_chunk_ids = sorted(set(chunk_ids))
        payloads = []
        entries = []
        running_offset = len(b"hubvault-pack/v1\n")
        for chunk_id in ordered_chunk_ids:
            entry = index_store.lookup(chunk_id, manifest=manifest)
            if entry is None:
                raise IntegrityError("chunk missing from index: %s" % chunk_id)
            chunk_data = pack_store.read_chunk(
                PackChunkLocation(
                    pack_id=entry.pack_id,
                    offset=entry.offset,
                    stored_size=entry.stored_size,
                    logical_size=entry.logical_size,
                )
            )
            if entry.compression != "none":
                raise IntegrityError("unsupported chunk compression: %s" % entry.compression)
            if len(chunk_data) != entry.logical_size:
                raise IntegrityError("chunk size mismatch")
            checksum = OBJECT_HASH + ":" + _sha256_hex(chunk_data)
            if checksum != entry.checksum:
                raise IntegrityError("chunk checksum mismatch")
            payloads.append(chunk_data)
            entries.append(
                IndexEntry(
                    chunk_id=chunk_id,
                    pack_id=pack_id,
                    offset=running_offset,
                    stored_size=len(chunk_data),
                    logical_size=entry.logical_size,
                    compression="none",
                    checksum=checksum,
                )
            )
            running_offset += len(chunk_data)

        segment_name = "seg-%s.idx" % pack_id
        segment_lines = [
            json.dumps(entry.to_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8")
            for entry in entries
        ]
        segment_size = sum(len(line) + 1 for line in segment_lines)
        manifest_obj = IndexManifest.empty()
        if entries:
            manifest_obj = manifest_obj.add_segment("L0", segment_name)
        manifest_size = len(_stable_json_bytes(manifest_obj.to_dict()))
        return {
            "pack_payloads": tuple(payloads) if with_data else tuple(),
            "index_entries": tuple(entries),
            "pack_size": (len(b"hubvault-pack/v1\n") + sum(len(item) for item in payloads)) if entries else 0,
            "index_total_size": segment_size + manifest_size,
            "segment_name": segment_name,
            "manifest": manifest_obj,
        }

    def _commit_title_and_description(self, payload: Dict[str, object]) -> Tuple[str, str]:
        """Extract title and description fields with HF-style fallback behavior."""

        title = payload.get("title")
        description = payload.get("description")
        if title is None or description is None:
            fallback_title, fallback_description = self._split_commit_message(str(payload.get("message", "")))
            if title is None:
                title = fallback_title
            if description is None:
                description = fallback_description
        return str(title), str(description)

    def _blocking_refs_for_lineage_unlocked(self, lineage_set: set, excluded_ref_name: str) -> List[str]:
        """Find refs whose current lineage still intersects an old rewritten history."""

        blocking_refs = []
        for ref_name, head in sorted(self._ref_targets_unlocked().items()):
            if ref_name == excluded_ref_name or head is None:
                continue
            current_commit_id = head
            seen = set()
            while current_commit_id is not None and current_commit_id not in seen:
                if current_commit_id in lineage_set:
                    blocking_refs.append(ref_name)
                    break
                seen.add(current_commit_id)
                payload = self._read_object_payload("commits", current_commit_id)
                parents = list(payload.get("parents", []))
                current_commit_id = str(parents[0]) if parents else None
        return blocking_refs

    def _quarantine_move_file_unlocked(self, source_path: Path, quarantine_root: Path, relative_root: Path) -> int:
        """Move one file into quarantine while keeping its relative layout."""

        if not source_path.exists():
            return 0
        size = source_path.stat().st_size
        target_path = quarantine_root / source_path.relative_to(relative_root)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(source_path), str(target_path))
        _fsync_directory(target_path.parent)
        return size

    def _clear_directory_children_unlocked(self, root: Path) -> int:
        """Delete all children beneath a directory and return reclaimed bytes."""

        if not root.exists():
            return 0
        reclaimed_size = 0
        for entry in sorted(root.iterdir()):
            reclaimed_size += _path_metrics(entry)[0]
            self._remove_detached_path(entry, root)
        return reclaimed_size

    @property
    def _format_path(self) -> Path:
        """
        Return the repository ``FORMAT`` marker path.

        :return: Absolute path to ``FORMAT``
        :rtype: pathlib.Path

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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
            "chunks/packs",
            "chunks/index/L0",
            "chunks/index/L1",
            "chunks/index/L2",
        ]:
            (self._repo_path / relative).mkdir(parents=True, exist_ok=True)
        manifest_path = self._repo_path / "chunks" / "index" / "MANIFEST"
        if not manifest_path.exists():
            IndexStore(self._repo_path / "chunks" / "index").write_manifest(IndexManifest.empty())

    def _ensure_repo(self) -> None:
        """
        Validate the repository root and ensure cache/layout directories exist.

        :return: ``None``.
        :rtype: None
        :raises RepositoryNotFoundError: Raised when the root does not contain a valid
            repository marker set.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._ensure_repo()  # doctest: +SKIP
        """

        if not self._is_repo():
            raise RepositoryNotFoundError("repository not found")
        self._ensure_layout()

    def _repo_config(self) -> Dict[str, object]:
        """
        Load the repository configuration payload.

        :return: Repository configuration mapping
        :rtype: Dict[str, object]

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._reflog_path("main").name
            'main.log'
        """

        return self._repo_path / "logs" / "refs" / "heads" / (name + ".log")

    def _tag_reflog_path(self, name: str) -> Path:
        """
        Build the reflog path for a tag name.

        :param name: Normalized tag name
        :type name: str
        :return: Absolute tag reflog path
        :rtype: pathlib.Path

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._tag_reflog_path("v1").name
            'v1.log'
        """

        return self._repo_path / "logs" / "refs" / "tags" / (name + ".log")

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._write_ref("main", None)  # doctest: +SKIP
        """

        path = self._ref_path(name)
        content = "" if commit_id is None else commit_id + "\n"
        _write_text_atomic(path, content)

    def _write_tag_ref(self, name: str, commit_id: str) -> None:
        """
        Persist a tag ref value.

        :param name: Normalized tag name
        :type name: str
        :param commit_id: Target commit object ID
        :type commit_id: str
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._write_tag_ref("v1", "sha256:" + "a" * 64)  # doctest: +SKIP
        """

        path = self._tag_ref_path(name)
        _write_text_atomic(path, commit_id + "\n")

    def _delete_ref_file(self, path: Path, stop_root: Path) -> None:
        """
        Delete a ref file and prune empty parent directories.

        :param path: Ref file path to remove
        :type path: pathlib.Path
        :param stop_root: Ref root that must not be removed
        :type stop_root: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._delete_ref_file(Path("/tmp/demo-repo/refs/heads/dev"), Path("/tmp/demo-repo/refs/heads"))  # doctest: +SKIP
        """

        path.unlink()
        _fsync_directory(path.parent)
        parent = path.parent
        while parent != stop_root and parent.exists():
            try:
                parent.rmdir()
                _fsync_directory(parent.parent)
            except OSError:
                break
            parent = parent.parent

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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
                if GIT_OID_PATTERN.fullmatch(str(revision)):
                    for commit_id in self._iter_object_ids_unlocked("commits"):
                        if self._public_commit_oid(commit_id) == revision:
                            return commit_id
                raise RevisionNotFoundError("revision not found: %s" % revision)

        if head is None and not allow_empty_ref:
            raise RevisionNotFoundError("revision has no commits yet: %s" % revision)
        return head

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

    def _compose_commit_text(self, commit_message: str, commit_description: str) -> str:
        """
        Compose the stored commit text from title and description parts.

        :param commit_message: Commit title
        :type commit_message: str
        :param commit_description: Commit description/body
        :type commit_description: str
        :return: Stored commit text
        :rtype: str

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._compose_commit_text("seed", "body")
            'seed\\n\\nbody'
        """

        if commit_description:
            return "%s\n\n%s" % (commit_message, commit_description)
        return commit_message

    def _repo_url(self) -> str:
        """
        Build the local repository URL string used in commit results.

        :return: Repository URL string
        :rtype: str

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._repo_url().startswith("file:")
            True
        """

        return self._repo_path.resolve().as_uri()

    def _commit_url(self, commit_id: str, txdir: Optional[Path] = None) -> str:
        """
        Build the local commit URL string used in commit results.

        :param commit_id: Commit object identifier
        :type commit_id: str
        :param txdir: Optional transaction directory used when the commit is
            still staged
        :type txdir: Optional[pathlib.Path], optional
        :return: Commit URL string
        :rtype: str

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._commit_url("sha256:" + "a" * 64).endswith("#commit=sha256:" + "a" * 64)
            True
        """

        return self._repo_url() + "#commit=" + self._public_commit_oid(commit_id, txdir=txdir)

    def _blob_url(self, revision: str, path_in_repo: str) -> str:
        """
        Build a local blob-style URL string for upload results.

        :param revision: Branch or tag name used for the public URL
        :type revision: str
        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :return: Blob-style URL string
        :rtype: str

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._blob_url("main", "demo.txt").endswith("#blob=main:demo.txt")
            True
        """

        return self._repo_url() + "#blob=" + revision + ":" + path_in_repo

    def _tree_url(self, revision: str, path_in_repo: str) -> str:
        """
        Build a local tree-style URL string for upload results.

        :param revision: Branch or tag name used for the public URL
        :type revision: str
        :param path_in_repo: Repo-relative directory path, or ``""`` for the
            repository root
        :type path_in_repo: str
        :return: Tree-style URL string
        :rtype: str

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._tree_url("main", "nested").endswith("#tree=main:nested")
            True
        """

        suffix = path_in_repo or ""
        return self._repo_url() + "#tree=" + revision + ":" + suffix

    def _repo_file_info(self, path: str, file_object_id: str) -> RepoFile:
        """
        Build HF-style public file metadata for a file object.

        :param path: Repo-relative file path
        :type path: str
        :param file_object_id: File object identifier
        :type file_object_id: str
        :return: Public file metadata
        :rtype: RepoFile

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._repo_file_info("demo.txt", "sha256:" + "a" * 64)  # doctest: +SKIP
        """

        payload = self._read_object_payload("files", file_object_id)
        sha256_hex = _public_sha256_hex(str(payload["sha256"]))
        logical_size = int(payload["logical_size"])
        lfs_info = None
        if str(payload.get("storage_kind")) == "chunked":
            pointer_size = payload.get("pointer_size")
            if pointer_size is None:
                pointer_size = len(canonical_lfs_pointer(sha256_hex, logical_size))
            lfs_info = BlobLfsInfo(
                size=logical_size,
                sha256=sha256_hex,
                pointer_size=int(pointer_size),
            )
        return RepoFile(
            path=path,
            size=logical_size,
            blob_id=str(payload["oid"]),
            lfs=lfs_info,
            last_commit=None,
            security=None,
            oid=str(payload["oid"]),
            sha256=sha256_hex,
            etag=str(payload["etag"]),
        )

    def _repo_folder_info(self, revision: str, path: str) -> RepoFolder:
        """
        Build HF-style public folder metadata for a repo path.

        :param revision: Revision containing the folder
        :type revision: str
        :param path: Repo-relative folder path
        :type path: str
        :return: Public folder metadata
        :rtype: RepoFolder

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._repo_folder_info("main", "nested")  # doctest: +SKIP
        """

        head_commit_id = self._resolve_revision(revision)
        commit_payload = self._read_object_payload("commits", head_commit_id)
        tree_id = self._tree_id_for_directory(str(commit_payload["tree_id"]), path)
        return RepoFolder(path=path, tree_id=self._public_tree_oid(tree_id), last_commit=None)

    def _tree_id_for_directory(self, root_tree_id: str, path_in_repo: str) -> str:
        """
        Resolve the tree object ID for a repo directory path.

        :param root_tree_id: Root tree object ID for the selected revision
        :type root_tree_id: str
        :param path_in_repo: Repo-relative directory path
        :type path_in_repo: str
        :return: Tree object ID for the requested directory
        :rtype: str
        :raises EntryNotFoundError: Raised when the directory does not exist.
        :raises UnsupportedPathError: Raised when the path points to a file.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._tree_id_for_directory("sha256:" + "a" * 64, "nested")  # doctest: +SKIP
        """

        normalized_path = _normalize_repo_path(path_in_repo)
        tree_id = root_tree_id
        for part in normalized_path.split("/"):
            tree_payload = self._read_object_payload("trees", tree_id)
            next_tree_id = None
            for entry in tree_payload.get("entries", []):
                if entry["name"] != part:
                    continue
                if entry["entry_type"] == "file":
                    raise UnsupportedPathError("path_in_repo must refer to a directory")
                next_tree_id = str(entry["object_id"])
                break
            if next_tree_id is None:
                raise EntryNotFoundError("directory not found: %s" % normalized_path)
            tree_id = next_tree_id
        return tree_id

    def _list_tree_entries(
        self,
        tree_id: str,
        prefix: str,
        recursive: bool,
    ) -> List[Union[RepoFile, RepoFolder]]:
        """
        Materialize HF-style file and folder entries for a tree object.

        :param tree_id: Tree object identifier
        :type tree_id: str
        :param prefix: Repo-relative prefix for the tree
        :type prefix: str
        :param recursive: Whether to recurse into descendant trees
        :type recursive: bool
        :return: Tree entries ordered by path
        :rtype: List[Union[RepoFile, RepoFolder]]

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._list_tree_entries("sha256:" + "a" * 64, "", False)  # doctest: +SKIP
        """

        items = []
        tree_payload = self._read_object_payload("trees", tree_id)
        for entry in tree_payload.get("entries", []):
            name = str(entry["name"])
            full_path = name if not prefix else prefix + "/" + name
            if entry["entry_type"] == "file":
                items.append(self._repo_file_info(full_path, str(entry["object_id"])))
            elif entry["entry_type"] == "tree":
                child_tree_id = str(entry["object_id"])
                items.append(RepoFolder(path=full_path, tree_id=self._public_tree_oid(child_tree_id), last_commit=None))
                if recursive:
                    items.extend(self._list_tree_entries(child_tree_id, full_path, recursive=True))
            else:
                raise IntegrityError("unknown tree entry type")
        return items

    def _stage_add_operation(
        self,
        txdir: Path,
        operation: CommitOperationAdd,
    ) -> Tuple[Optional[str], str, Dict[str, object]]:
        """
        Stage the storage objects needed for an add operation.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param operation: Public add operation
        :type operation: CommitOperationAdd
        :return: Tuple of content object ID when applicable, file ID, and file
            payload
        :rtype: Tuple[Optional[str], str, Dict[str, object]]

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> operation = CommitOperationAdd("demo.txt", b"hello")
            >>> backend._stage_add_operation(Path("/tmp/demo-repo/txn/demo"), operation)  # doctest: +SKIP
        """

        normalized_path = _normalize_repo_path(operation.path_in_repo)
        del normalized_path
        with operation.as_file() as fileobj:
            data = fileobj.read()
        repo_config = self._repo_config()
        threshold = int(repo_config.get("large_file_threshold", LARGE_FILE_THRESHOLD))
        if len(data) >= threshold:
            return self._stage_chunked_add_operation(txdir, data)

        return self._stage_blob_add_operation(txdir, data)

    def _stage_blob_add_operation(
        self,
        txdir: Path,
        data: bytes,
    ) -> Tuple[str, str, Dict[str, object]]:
        """
        Stage a whole-blob file payload.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param data: Logical file payload bytes
        :type data: bytes
        :return: Tuple of blob ID, file ID, and file payload
        :rtype: Tuple[str, str, Dict[str, object]]
        """

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

    def _next_pack_id(self, txdir: Path) -> str:
        """
        Build the next staged pack identifier for a transaction.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: Unique pack identifier
        :rtype: str
        """

        pack_dir = txdir / "chunks" / "packs"
        existing = sorted(pack_dir.glob("*.pack")) if pack_dir.exists() else []
        return "%s-%06d" % (txdir.name, len(existing) + 1)

    def _stage_chunked_add_operation(
        self,
        txdir: Path,
        data: bytes,
    ) -> Tuple[None, str, Dict[str, object]]:
        """
        Stage a chunked file payload together with pack and index data.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param data: Logical file payload bytes
        :type data: bytes
        :return: Tuple of ``None``, file ID, and file payload
        :rtype: Tuple[None, str, Dict[str, object]]
        """

        chunk_plan = ChunkStore().plan_bytes(data)
        pack_id = self._next_pack_id(txdir)
        pack_store = PackStore(txdir / "chunks" / "packs")
        pack_result = pack_store.write_pack(pack_id, [part.data for part in chunk_plan.parts])

        index_entries = []
        file_chunks = []
        for part, location in zip(chunk_plan.parts, pack_result.chunks):
            descriptor = part.descriptor
            index_entries.append(
                IndexEntry(
                    chunk_id=descriptor.chunk_id,
                    pack_id=location.pack_id,
                    offset=location.offset,
                    stored_size=location.stored_size,
                    logical_size=descriptor.logical_size,
                    compression=descriptor.compression,
                    checksum=descriptor.checksum,
                )
            )
            file_chunks.append(
                {
                    "chunk_id": descriptor.chunk_id,
                    "checksum": descriptor.checksum,
                    "logical_offset": descriptor.logical_offset,
                    "logical_size": descriptor.logical_size,
                    "stored_size": descriptor.stored_size,
                    "compression": descriptor.compression,
                }
            )

        IndexStore(txdir / "chunks" / "index").write_segment(
            "L0",
            "seg-%s.idx" % pack_id,
            index_entries,
        )
        file_payload = {
            "format_version": FORMAT_VERSION,
            "storage_kind": "chunked",
            "logical_size": chunk_plan.logical_size,
            "sha256": chunk_plan.sha256,
            "oid": chunk_plan.oid,
            "etag": chunk_plan.etag,
            "pointer_size": chunk_plan.pointer_size,
            "content_type_hint": None,
            "content_object_id": None,
            "chunks": file_chunks,
        }
        file_object_id = self._stage_json_object(txdir, "files", file_payload)
        return None, file_object_id, file_payload

    def _stage_chunk_manifest(self, txdir: Path) -> None:
        """
        Stage an updated visible chunk-index manifest for a transaction.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None
        """

        staged_index = IndexStore(txdir / "chunks" / "index")
        discovered = []
        for level in ("L0", "L1", "L2"):
            level_root = staged_index.segment_path(level, "placeholder").parent
            if not level_root.exists():
                continue
            for path in sorted(level_root.glob("*.idx")):
                discovered.append((level, path.name))

        if not discovered:
            return

        manifest = IndexStore(self._repo_path / "chunks" / "index").read_manifest()
        for level, segment_name in discovered:
            manifest = manifest.add_segment(level, segment_name)
        staged_index.write_manifest(manifest)

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
        :raises EntryNotFoundError: Raised when the target path is absent.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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
                raise EntryNotFoundError("path not found: %s" % normalized_path)
            return

        try:
            del snapshot[normalized_path]
        except KeyError:
            raise EntryNotFoundError("path not found: %s" % normalized_path)

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
        :raises EntryNotFoundError: Raised when the source path is absent.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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
            raise EntryNotFoundError("path not found: %s" % src_path)
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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
        tree_payload["git_oid"] = _git_tree_oid(
            [
                {
                    "name": str(entry["name"]),
                    "entry_type": str(entry["entry_type"]),
                    "mode": str(entry["mode"]),
                    "git_oid": (
                        self._public_tree_oid(str(entry["object_id"]), txdir=txdir)
                        if str(entry["entry_type"]) == "tree"
                        else str(self._read_staged_or_published_file_payload(txdir, str(entry["object_id"]))["oid"])
                    ),
                }
                for entry in entries
            ]
        )
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._read_staged_or_published_file_payload(Path("/tmp/demo-repo/txn/demo"), "sha256:" + "a" * 64)  # doctest: +SKIP
        """

        staged_path = self._stage_object_json_path(txdir, "files", object_id)
        if staged_path.exists():
            return dict(_read_json(staged_path)["payload"])
        return self._read_object_payload("files", object_id)

    def _publish_staged_objects(self, txdir: Path) -> None:
        """
        Publish staged transaction data into the repository stores.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when a staged object conflicts with an
            existing published object.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._publish_staged_objects(Path("/tmp/demo-repo/txn/demo"))  # doctest: +SKIP
        """

        staged_root = txdir / "objects"
        if staged_root.exists():
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
                    _fsync_directory(path.parent)
                    continue
                os.replace(str(path), str(target))
                _fsync_directory(target.parent)

        staged_packs = txdir / "chunks" / "packs"
        if staged_packs.exists():
            for path in sorted(staged_packs.glob("*.pack")):
                target = self._repo_path / "chunks" / "packs" / path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if path.read_bytes() != target.read_bytes():
                        raise IntegrityError("staged pack does not match existing pack")
                    path.unlink()
                    _fsync_directory(path.parent)
                    continue
                os.replace(str(path), str(target))
                _fsync_directory(target.parent)

        staged_index = txdir / "chunks" / "index"
        if staged_index.exists():
            for level in ("L0", "L1", "L2"):
                staged_level_root = staged_index / level
                if not staged_level_root.exists():
                    continue
                for path in sorted(staged_level_root.glob("*.idx")):
                    target = self._repo_path / "chunks" / "index" / level / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        if path.read_bytes() != target.read_bytes():
                            raise IntegrityError("staged index segment does not match existing segment")
                        path.unlink()
                        _fsync_directory(path.parent)
                        continue
                    os.replace(str(path), str(target))
                    _fsync_directory(target.parent)

            manifest_path = staged_index / "MANIFEST"
            if manifest_path.exists():
                target_manifest = self._repo_path / "chunks" / "index" / "MANIFEST"
                target_manifest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(str(manifest_path), str(target_manifest))
                _fsync_directory(target_manifest.parent)

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._commit_info("sha256:" + "a" * 64, "main")  # doctest: +SKIP
        """

        commit_payload = self._read_object_payload("commits", commit_id)
        raw_message = str(commit_payload.get("message", ""))
        title = str(commit_payload.get("title", ""))
        description = str(commit_payload.get("description", ""))
        if not title:
            title, description = self._split_commit_message(raw_message)
        return CommitInfo(
            commit_url=self._commit_url(commit_id),
            commit_message=title,
            commit_description=description,
            oid=self._public_commit_oid(commit_id),
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._git_commit_info("sha256:" + "a" * 64)  # doctest: +SKIP
        """

        commit_payload = self._read_object_payload("commits", commit_id)
        raw_message = str(commit_payload.get("message", ""))
        title = str(commit_payload.get("title", ""))
        message = str(commit_payload.get("description", ""))
        if not title:
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
            commit_id=self._public_commit_oid(commit_id),
            authors=[],
            created_at=created_at,
            title=title,
            message=message,
            formatted_title=formatted_title,
            formatted_message=formatted_message,
        )

    def _resolve_reflog_query(self, ref_name: str) -> Tuple[Path, str]:
        """
        Resolve a public reflog query to a concrete reflog path.

        :param ref_name: Full ref name or an unambiguous short ref name
        :type ref_name: str
        :return: Reflog path and normalized full ref name
        :rtype: Tuple[pathlib.Path, str]
        :raises ConflictError: Raised when a short name matches both a branch
            and a tag.
        :raises RevisionNotFoundError: Raised when the requested ref is absent.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._resolve_reflog_query("refs/heads/main")  # doctest: +SKIP
        """

        if ref_name.startswith("refs/heads/"):
            name = _validate_ref_name(ref_name[len("refs/heads/"):])
            path = self._reflog_path(name)
            if not path.exists() and not self._ref_path(name).exists():
                raise RevisionNotFoundError("reflog not found: %s" % ref_name)
            return path, "refs/heads/" + name

        if ref_name.startswith("refs/tags/"):
            name = _validate_ref_name(ref_name[len("refs/tags/"):])
            path = self._tag_reflog_path(name)
            if not path.exists() and not self._tag_ref_path(name).exists():
                raise RevisionNotFoundError("reflog not found: %s" % ref_name)
            return path, "refs/tags/" + name

        short_name = _validate_ref_name(ref_name)
        branch_path = self._reflog_path(short_name)
        tag_path = self._tag_reflog_path(short_name)
        branch_visible = branch_path.exists() or self._ref_path(short_name).exists()
        tag_visible = tag_path.exists() or self._tag_ref_path(short_name).exists()

        if branch_visible and tag_visible:
            raise ConflictError("ambiguous ref name: %s" % short_name)
        if branch_visible:
            return branch_path, "refs/heads/" + short_name
        if tag_visible:
            return tag_path, "refs/tags/" + short_name
        raise RevisionNotFoundError("reflog not found: %s" % short_name)

    @staticmethod
    def _split_commit_message(message: str) -> Tuple[str, str]:
        """
        Split a stored commit message into title and body segments.

        :param message: Raw stored commit message
        :type message: str
        :return: Two-tuple of title and body message
        :rtype: Tuple[str, str]

        Example::

            >>> RepositoryBackend._split_commit_message("title\\n\\nbody")
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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
        Verify a file object and its referenced content.

        :param file_object_id: File object identifier
        :type file_object_id: str
        :return: ``None``.
        :rtype: None
        :raises IntegrityError: Raised when file metadata, blob metadata, or
            blob content is inconsistent.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._verify_file_object("sha256:" + "a" * 64)  # doctest: +SKIP
        """

        try:
            payload = self._read_object_payload("files", file_object_id)
            if str(payload.get("storage_kind")) == "chunked":
                data = self._read_chunked_file_bytes(payload)
                if len(data) != int(payload["logical_size"]):
                    raise IntegrityError("file logical size mismatch")
                stored_pointer_size = payload.get("pointer_size")
                if stored_pointer_size is not None:
                    expected_pointer_size = len(
                        canonical_lfs_pointer(
                            _public_sha256_hex(str(payload["sha256"])),
                            int(payload["logical_size"]),
                        )
                    )
                    if int(stored_pointer_size) != expected_pointer_size:
                        raise IntegrityError("file pointer size mismatch")
                return

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

    def _create_txdir(self, revision: str, expected_head: Optional[str]) -> Path:
        """
        Create a new transaction working directory.

        :param revision: Target revision for the transaction
        :type revision: str
        :param expected_head: Expected branch head recorded for crash recovery
            and optimistic-concurrency diagnostics
        :type expected_head: Optional[str]
        :return: Absolute transaction directory path
        :rtype: pathlib.Path

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._create_txdir("main", None)  # doctest: +SKIP
        """

        txid = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        txdir = self._repo_path / "txn" / txid
        txdir.mkdir(parents=True, exist_ok=False)
        _fsync_directory(txdir.parent)
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

    def _write_tx_ref_update(
        self,
        txdir: Path,
        ref_kind: str,
        ref_name: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
        ref_existed_before: bool,
    ) -> None:
        """
        Persist ref-transition metadata needed for crash recovery.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param ref_kind: Ref collection kind, either ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized branch or tag name
        :type ref_name: str
        :param old_head: Previous ref head
        :type old_head: Optional[str]
        :param new_head: New ref head
        :type new_head: Optional[str]
        :param message: Reflog message for successful committed writes
        :type message: str
        :param ref_existed_before: Whether the ref existed before the write began
        :type ref_existed_before: bool
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._write_tx_ref_update(Path("/tmp/demo-repo/txn/demo"), "branch", "main", None, None, "seed", True)  # doctest: +SKIP
        """

        reflog_path, _ = self._reflog_record(
            revision=ref_name,
            old_head=old_head,
            new_head=new_head,
            message=message,
            ref_kind=ref_kind,
        )
        reflog_existed_before = reflog_path.exists()
        reflog_size_before = reflog_path.stat().st_size if reflog_existed_before else 0

        _write_json_atomic(
            txdir / "REF_UPDATE.json",
            {
                "ref_kind": ref_kind,
                "ref_name": ref_name,
                "old_head": old_head,
                "new_head": new_head,
                "message": message,
                "ref_existed_before": bool(ref_existed_before),
                "reflog_path": str(reflog_path.relative_to(self._repo_path)),
                "reflog_existed_before": reflog_existed_before,
                "reflog_size_before": reflog_size_before,
                "updated_at": _utc_now(),
            },
        )

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._write_tx_state(Path("/tmp/demo-repo/txn/demo"), "PREPARING")  # doctest: +SKIP
        """

        _write_json_atomic(txdir / "STATE.json", {"state": state, "updated_at": _utc_now()})

    def _commit_branch_ref_update_unlocked(
        self,
        txdir: Path,
        branch_name: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
        failpoint_prefix: str = "ref_update.branch",
    ) -> None:
        """
        Persist and finalize one committed branch-head update.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param branch_name: Normalized branch name
        :type branch_name: str
        :param old_head: Previous branch head
        :type old_head: Optional[str]
        :param new_head: New branch head
        :type new_head: Optional[str]
        :param message: Reflog message for the committed update
        :type message: str
        :param failpoint_prefix: Failpoint namespace used by fault-injection
            tests
        :type failpoint_prefix: str, optional
        :return: ``None``.
        :rtype: None
        """

        self._finalize_ref_update_unlocked(
            txdir=txdir,
            ref_kind="branch",
            ref_name=branch_name,
            old_head=old_head,
            new_head=new_head,
            message=message,
            ref_existed_before=True,
            apply_ref_change=lambda: self._write_ref(branch_name, new_head),
            failpoint_prefix=failpoint_prefix,
        )

    def _maybe_failpoint(self, name: str) -> None:
        """
        Trigger a controlled test failure when the selected failpoint matches.

        The hook is intentionally environment-driven so subprocess tests can
        inject failures through the public API without importing private helper
        code or monkeypatching internals.

        :param name: Fully-qualified failpoint name
        :type name: str
        :return: ``None``.
        :rtype: None
        :raises RuntimeError: Raised when ``HUBVAULT_FAIL_ACTION`` requests a
            runtime failure.
        :raises OSError: Raised when ``HUBVAULT_FAIL_ACTION`` requests an OS
            level failure.
        :raises KeyboardInterrupt: Raised when ``HUBVAULT_FAIL_ACTION``
            requests an interrupt-style failure.
        :raises ValueError: Raised when the configured fail action is unknown.
        """

        configured = os.environ.get(FAILPOINT_ENV, "")
        if not configured:
            return
        names = [item.strip() for item in configured.split(",") if item.strip()]
        if name not in names:
            return

        action = os.environ.get(FAIL_ACTION_ENV, "raise-runtime").strip().lower()
        if action in ("raise-runtime", "runtime", "raise"):
            raise RuntimeError("hubvault failpoint triggered: %s" % name)
        if action in ("raise-oserror", "oserror", "os"):
            raise OSError("hubvault failpoint triggered: %s" % name)
        if action in ("raise-keyboard", "keyboard", "keyboardinterrupt"):
            raise KeyboardInterrupt("hubvault failpoint triggered: %s" % name)
        if action == "exit":
            os._exit(FAILPOINT_EXIT_CODE)
        raise ValueError("unknown hubvault fail action: %s" % action)

    def _safe_cleanup_txdir(self, txdir: Path) -> None:
        """
        Best-effort cleanup for a completed transaction directory.

        Cleanup happens after the transaction is already durable. A cleanup
        failure therefore must not turn a successful public write into a failed
        one; leftover committed txdirs are cleaned on the next repo open.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None
        """

        try:
            self._cleanup_txdir(txdir)
        except OSError as err:
            warnings.warn(
                "Failed to clean committed transaction directory %s: %s" % (txdir.name, err),
                RuntimeWarning,
            )

    def _rollback_transaction_unlocked(self, txdir: Path) -> None:
        """
        Roll back an interrupted transaction while the write lock is held.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None
        """

        if not txdir.exists():
            return
        if (txdir / "REF_UPDATE.json").exists():
            self._recover_ref_update_transaction(txdir)
        else:
            self._cleanup_txdir(txdir)

    def _restore_reflog_state(
        self,
        ref_kind: str,
        reflog_path: Path,
        reflog_existed_before: bool,
        reflog_size_before: int,
    ) -> None:
        """
        Restore reflog bytes to their pre-transaction state.

        :param ref_kind: Ref collection kind, either ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param reflog_path: Absolute reflog file path
        :type reflog_path: pathlib.Path
        :param reflog_existed_before: Whether the reflog existed before the
            interrupted write
        :type reflog_existed_before: bool
        :param reflog_size_before: Previous reflog byte size
        :type reflog_size_before: int
        :return: ``None``.
        :rtype: None
        """

        if reflog_existed_before:
            reflog_path.parent.mkdir(parents=True, exist_ok=True)
            with reflog_path.open("ab") as file_:
                file_.truncate(reflog_size_before)
                file_.flush()
                os.fsync(file_.fileno())
            _fsync_directory(reflog_path.parent)
            return

        if reflog_path.exists():
            if ref_kind == "branch":
                self._delete_ref_file(reflog_path, self._repo_path / "logs" / "refs" / "heads")
            elif ref_kind == "tag":
                self._delete_ref_file(reflog_path, self._repo_path / "logs" / "refs" / "tags")
            else:
                raise ValueError("ref_kind must be 'branch' or 'tag'")

    def _finalize_ref_update_unlocked(
        self,
        txdir: Path,
        ref_kind: str,
        ref_name: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
        ref_existed_before: bool,
        apply_ref_change: Callable[[], None],
        failpoint_prefix: str,
    ) -> None:
        """
        Apply one ref update transaction and mark it committed atomically.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :param ref_kind: Ref collection kind, either ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized branch or tag name
        :type ref_name: str
        :param old_head: Previous ref target
        :type old_head: Optional[str]
        :param new_head: New ref target
        :type new_head: Optional[str]
        :param message: Reflog message
        :type message: str
        :param ref_existed_before: Whether the ref existed before the write
        :type ref_existed_before: bool
        :param apply_ref_change: Callback that writes or deletes the target ref
        :type apply_ref_change: Callable[[], None]
        :param failpoint_prefix: Failpoint namespace for fault-injection tests
        :type failpoint_prefix: str
        :return: ``None``.
        :rtype: None
        """

        self._write_tx_ref_update(
            txdir=txdir,
            ref_kind=ref_kind,
            ref_name=ref_name,
            old_head=old_head,
            new_head=new_head,
            message=message,
            ref_existed_before=ref_existed_before,
        )
        apply_ref_change()
        self._write_tx_state(txdir, "UPDATED_REF")
        self._maybe_failpoint(failpoint_prefix + ".after_ref_write")
        self._append_reflog(
            revision=ref_name,
            old_head=old_head,
            new_head=new_head,
            message=message,
            ref_kind=ref_kind,
        )
        self._write_tx_state(txdir, "APPENDED_REFLOG")
        self._maybe_failpoint(failpoint_prefix + ".after_reflog_append")
        self._write_tx_state(txdir, "COMMITTED")

    def _read_tx_state(self, txdir: Path) -> Optional[str]:
        """
        Read the persisted transaction state marker if available.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: State label, or ``None`` when missing/unreadable
        :rtype: Optional[str]
        """

        state_path = txdir / "STATE.json"
        if not state_path.exists():
            return None
        try:
            payload = _read_json(state_path)
        except (OSError, TypeError, ValueError):
            # Treat unreadable state as not committed so recovery chooses rollback.
            return None
        if not isinstance(payload, dict):
            return None
        return str(payload.get("state", ""))

    def _restore_ref_value(
        self,
        ref_kind: str,
        ref_name: str,
        old_head: Optional[str],
        ref_existed_before: bool,
    ) -> None:
        """
        Restore a branch or tag to its pre-transaction value.

        :param ref_kind: Ref collection kind, either ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :param ref_name: Normalized branch or tag name
        :type ref_name: str
        :param old_head: Previous ref target
        :type old_head: Optional[str]
        :param ref_existed_before: Whether the ref existed before the write began
        :type ref_existed_before: bool
        :return: ``None``.
        :rtype: None
        """

        if ref_kind == "branch":
            path = self._ref_path(ref_name)
            if ref_existed_before:
                self._write_ref(ref_name, old_head)
            elif path.exists():
                self._delete_ref_file(path, self._repo_path / "refs" / "heads")
            return

        if ref_kind == "tag":
            path = self._tag_ref_path(ref_name)
            if ref_existed_before and old_head is not None:
                self._write_tag_ref(ref_name, old_head)
            elif path.exists():
                self._delete_ref_file(path, self._repo_path / "refs" / "tags")
            return

        raise ValueError("ref_kind must be 'branch' or 'tag'")

    def _recover_ref_update_transaction(self, txdir: Path) -> None:
        """
        Resolve a ref-changing transaction by cleanup or rollback.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._recover_ref_update_transaction(Path("/tmp/demo-repo/txn/demo"))  # doctest: +SKIP
        """

        ref_update_path = txdir / "REF_UPDATE.json"
        if not ref_update_path.exists():
            self._cleanup_txdir(txdir)
            return

        try:
            payload = _read_json(ref_update_path)
        except (OSError, TypeError, ValueError) as err:
            raise IntegrityError("invalid ref update journal %s: %s" % (txdir.name, err))
        if not isinstance(payload, dict):
            raise IntegrityError("invalid ref update journal %s: expected JSON object" % txdir.name)
        try:
            ref_kind = str(payload["ref_kind"])
            ref_name = str(payload["ref_name"])
        except KeyError as err:
            raise IntegrityError("invalid ref update journal %s: missing %s" % (txdir.name, err.args[0]))
        old_head = payload.get("old_head")
        ref_existed_before = payload.get("ref_existed_before", True)
        new_head = payload.get("new_head")
        message = str(payload.get("message", ""))
        reflog_raw_path = payload.get("reflog_path")
        reflog_existed_before = payload.get("reflog_existed_before")
        reflog_size_before = payload.get("reflog_size_before")
        if old_head is not None and not isinstance(old_head, str):
            raise IntegrityError("invalid ref update journal %s: old_head must be a string or null" % txdir.name)
        if new_head is not None and not isinstance(new_head, str):
            raise IntegrityError("invalid ref update journal %s: new_head must be a string or null" % txdir.name)
        if not isinstance(ref_existed_before, bool):
            raise IntegrityError("invalid ref update journal %s: ref_existed_before must be a boolean" % txdir.name)

        if reflog_raw_path is None:
            try:
                reflog_path, _ = self._reflog_record(
                    revision=ref_name,
                    old_head=old_head,
                    new_head=new_head,
                    message=message,
                    ref_kind=ref_kind,
                )
            except ValueError as err:
                raise IntegrityError("invalid ref update journal %s: %s" % (txdir.name, err))
            reflog_existed_before = reflog_path.exists()
            reflog_size_before = reflog_path.stat().st_size if reflog_existed_before else 0
        else:
            if not isinstance(reflog_raw_path, str):
                raise IntegrityError("invalid ref update journal %s: reflog_path must be a string" % txdir.name)
            if not isinstance(reflog_existed_before, bool):
                raise IntegrityError("invalid ref update journal %s: reflog_existed_before must be a boolean" % txdir.name)
            if not isinstance(reflog_size_before, int) or reflog_size_before < 0:
                raise IntegrityError("invalid ref update journal %s: reflog_size_before must be a non-negative integer" % txdir.name)
            reflog_path = self._repo_path / reflog_raw_path

        if self._read_tx_state(txdir) != "COMMITTED":
            try:
                self._restore_ref_value(
                    ref_kind=ref_kind,
                    ref_name=ref_name,
                    old_head=old_head,
                    ref_existed_before=ref_existed_before,
                )
                self._restore_reflog_state(
                    ref_kind=ref_kind,
                    reflog_path=reflog_path,
                    reflog_existed_before=reflog_existed_before,
                    reflog_size_before=reflog_size_before,
                )
            except ValueError as err:
                raise IntegrityError("invalid ref update journal %s: %s" % (txdir.name, err))
        self._cleanup_txdir(txdir)

    def _cleanup_txdir(self, txdir: Path) -> None:
        """
        Remove a transaction directory if it still exists.

        :param txdir: Transaction working directory
        :type txdir: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._cleanup_txdir(Path("/tmp/demo-repo/txn/demo"))  # doctest: +SKIP
        """

        if txdir.exists():
            self._remove_tree(txdir)
            _fsync_directory(txdir.parent)

    def _has_ref_update_transactions(self) -> bool:
        """
        Check whether the transaction area contains ref-changing leftovers.

        :return: Whether any transaction still carries ``REF_UPDATE.json``
        :rtype: bool
        """

        txn_root = self._repo_path / "txn"
        if not txn_root.exists():
            return False
        for txdir in txn_root.iterdir():
            if txdir.is_dir() and (txdir / "REF_UPDATE.json").exists():
                return True
        return False

    def _rollback_interrupted_ref_updates_if_needed(self) -> None:
        """
        Roll back interrupted ref-changing transactions before serving reads.

        :return: ``None``.
        :rtype: None
        """

        if not self._has_ref_update_transactions():
            return
        with self._write_locked():
            txn_root = self._repo_path / "txn"
            if not txn_root.exists():
                return
            for txdir in sorted(txn_root.iterdir()):
                if txdir.is_dir() and (txdir / "REF_UPDATE.json").exists():
                    self._recover_ref_update_transaction(txdir)

    def _recover_transactions(self) -> None:
        """
        Recover or clean abandoned transactions while holding the write lock.

        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._recover_transactions()  # doctest: +SKIP
        """

        txn_root = self._repo_path / "txn"
        if not txn_root.exists():
            return

        for txdir in sorted(txn_root.iterdir()):
            if not txdir.is_dir():
                continue
            if (txdir / "REF_UPDATE.json").exists():
                self._recover_ref_update_transaction(txdir)
            else:
                self._cleanup_txdir(txdir)

    def _reflog_record(
        self,
        revision: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
        ref_kind: str,
    ) -> Tuple[Path, Dict[str, object]]:
        """
        Build the reflog path and record payload for a ref update.

        :param revision: Branch or tag name
        :type revision: str
        :param old_head: Previous head commit
        :type old_head: Optional[str]
        :param new_head: New head commit
        :type new_head: Optional[str]
        :param message: Short reflog message
        :type message: str
        :param ref_kind: Ref collection kind, either ``"branch"`` or ``"tag"``
        :type ref_kind: str
        :return: Tuple of reflog file path and JSON-serializable record
        :rtype: Tuple[pathlib.Path, Dict[str, object]]

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._reflog_record("main", None, None, "seed", "branch")[0].name
            'main.log'
        """

        if ref_kind == "branch":
            path = self._reflog_path(revision)
            full_ref_name = "refs/heads/" + revision
        elif ref_kind == "tag":
            path = self._tag_reflog_path(revision)
            full_ref_name = "refs/tags/" + revision
        else:
            raise ValueError("ref_kind must be 'branch' or 'tag'")

        record = {
            "timestamp": _utc_now(),
            "ref_name": full_ref_name,
            "old_head": old_head,
            "new_head": new_head,
            "message": message,
            "checksum": OBJECT_HASH + ":" + _sha256_hex(_stable_json_bytes([old_head, new_head, message])),
        }
        return path, record

    @staticmethod
    def _last_jsonl_record(path: Path) -> Optional[Dict[str, object]]:
        """
        Read the last non-empty JSON Lines record from a file.

        :param path: JSONL file path
        :type path: pathlib.Path
        :return: Parsed last record, or ``None`` if unavailable
        :rtype: Optional[Dict[str, object]]

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._last_jsonl_record(Path("/tmp/missing.jsonl"))
        """

        if not path.exists():
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                return None
            if isinstance(payload, dict):
                return dict(payload)
            return None
        return None

    def _append_reflog(
        self,
        revision: str,
        old_head: Optional[str],
        new_head: Optional[str],
        message: str,
        ref_kind: str = "branch",
    ) -> None:
        """
        Append a reflog record for a branch or tag update.

        :param revision: Branch or tag name
        :type revision: str
        :param old_head: Previous head commit
        :type old_head: Optional[str]
        :param new_head: New head commit
        :type new_head: Optional[str]
        :param message: Short reflog message
        :type message: str
        :param ref_kind: Ref collection kind, either ``"branch"`` or ``"tag"``
        :type ref_kind: str, optional
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._append_reflog("main", None, "sha256:" + "a" * 64, "seed")  # doctest: +SKIP
        """

        path, record = self._reflog_record(
            revision=revision,
            old_head=old_head,
            new_head=new_head,
            message=message,
            ref_kind=ref_kind,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        last_record = self._last_jsonl_record(path)
        if (
            last_record is not None
            and last_record.get("checksum") == record["checksum"]
            and last_record.get("ref_name") == record["ref_name"]
            and last_record.get("old_head") == record["old_head"]
            and last_record.get("new_head") == record["new_head"]
            and last_record.get("message") == record["message"]
        ):
            return
        with path.open("a", encoding="utf-8") as file_:
            file_.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            file_.write("\n")
            file_.flush()
            os.fsync(file_.fileno())
        _fsync_directory(path.parent)

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
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

    def _validate_detached_target_root(self, target_root: Path) -> None:
        """
        Validate that a detached export root does not overlap repository truth.

        :param target_root: User-supplied detached export directory
        :type target_root: pathlib.Path
        :return: ``None``.
        :rtype: None
        :raises UnsupportedPathError: Raised when the export directory points
            inside the repository root.

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))
            >>> backend._validate_detached_target_root(Path("/tmp/export"))
        """

        resolved_root = Path(os.path.realpath(str(target_root)))
        resolved_repo = Path(os.path.realpath(str(self._repo_path)))
        if _is_relative_to(resolved_root, resolved_repo):
            raise UnsupportedPathError("local_dir must be outside the repository root")

    def _remove_detached_path(self, target_path: Path, root_path: Path) -> None:
        """
        Remove a detached snapshot or file-view path and prune empty parents.

        :param target_path: Detached file or directory path to remove
        :type target_path: pathlib.Path
        :param root_path: Root directory that must be preserved
        :type root_path: pathlib.Path
        :return: ``None``.
        :rtype: None

        Example::

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._remove_detached_path(Path("/tmp/demo/file.txt"), Path("/tmp/demo"))  # doctest: +SKIP
        """

        if target_path.is_symlink() or target_path.is_file():
            self._unlink_path(target_path)
        elif target_path.is_dir():
            self._remove_tree(target_path)
        elif target_path.exists():
            self._unlink_path(target_path)

        parent = target_path.parent
        while parent != root_path and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

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

            >>> backend = RepositoryBackend(Path("/tmp/demo-repo"))  # doctest: +SKIP
            >>> backend._ensure_detached_view(Path("/tmp/demo-repo/cache/files/demo.txt"), b"demo", {"sha256": "a" * 64})  # doctest: +SKIP
        """

        expected_sha256 = _public_sha256_hex(str(file_payload["sha256"]))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            if target_path.is_symlink():
                self._unlink_path(target_path)
            elif target_path.is_dir():
                self._remove_tree(target_path)
            elif target_path.is_file():
                current_sha256 = _sha256_hex(target_path.read_bytes())
                if current_sha256 == expected_sha256:
                    return
                self._unlink_path(target_path)
            else:  # pragma: no cover - defensive path for unusual filesystem nodes
                self._unlink_path(target_path)
        _write_bytes_atomic(target_path, data)

    @staticmethod
    def _chmod_writable(path: Path) -> None:
        """
        Best-effort removal of a filesystem read-only attribute.

        :param path: File or directory path to adjust
        :type path: pathlib.Path
        :return: ``None``.
        :rtype: None
        """

        try:
            mode = stat.S_IWRITE | stat.S_IREAD
            if path.is_dir():
                mode |= stat.S_IEXEC
            path.chmod(mode)
        except OSError:
            pass

    def _unlink_path(self, path: Path) -> None:
        """
        Remove one filesystem entry, retrying after clearing read-only bits.

        :param path: File-system path to unlink
        :type path: pathlib.Path
        :return: ``None``.
        :rtype: None
        """

        try:
            path.unlink()
        except FileNotFoundError:
            return
        except PermissionError:
            self._chmod_writable(path)
            path.unlink()

    def _rmtree_onerror(self, func, path, exc_info) -> None:
        """
        Retry tree deletion after clearing read-only attributes.

        :param func: Filesystem callable that raised the original error
        :type func: object
        :param path: Path passed to ``func``
        :type path: object
        :param exc_info: Exception tuple from :func:`shutil.rmtree`
        :type exc_info: object
        :return: ``None``.
        :rtype: None
        """

        err = exc_info[1]
        if isinstance(err, FileNotFoundError):
            return
        retry_path = Path(path)
        self._chmod_writable(retry_path)
        func(path)

    def _remove_tree(self, path: Path) -> None:
        """
        Remove a directory tree while tolerating Windows read-only files.

        :param path: Directory tree root
        :type path: pathlib.Path
        :return: ``None``.
        :rtype: None
        """

        shutil.rmtree(str(path), onerror=self._rmtree_onerror)
