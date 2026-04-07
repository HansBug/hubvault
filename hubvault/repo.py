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
from datetime import datetime
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
from .models import CommitInfo, PathInfo, RepoInfo, VerifyReport
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
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_json_bytes(data: object) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


def _git_blob_oid(data: bytes) -> str:
    header = "blob %d\0" % len(data)
    return sha1(header.encode("utf-8") + data).hexdigest()


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / (path.name + ".tmp." + secrets.token_hex(4))
    with temp_path.open("wb") as file_:
        file_.write(data)
        file_.flush()
        os.fsync(file_.fileno())
    os.replace(str(temp_path), str(path))


def _write_text_atomic(path: Path, text: str) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"))


def _write_json_atomic(path: Path, payload: object) -> None:
    _write_bytes_atomic(path, _stable_json_bytes(payload))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as file_:
        return json.load(file_)


def _normalize_repo_path(path_in_repo: str) -> str:
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
    if not REF_NAME_PATTERN.fullmatch(name or ""):
        raise UnsupportedPathError("invalid ref name")
    normalized = _normalize_repo_path(name)
    return normalized


def _split_object_id(object_id: str) -> Tuple[str, str]:
    try:
        algorithm, digest = object_id.split(":", 1)
    except ValueError:
        raise IntegrityError("invalid object id format")
    if algorithm != OBJECT_HASH or not digest:
        raise IntegrityError("unsupported object id")
    return algorithm, digest


def _object_id_from_container(container: object) -> Tuple[str, bytes]:
    container_bytes = _stable_json_bytes(container)
    return OBJECT_HASH + ":" + _sha256_hex(container_bytes), container_bytes


def _build_object_container(object_type: str, payload: object) -> Tuple[str, bytes]:
    payload_bytes = _stable_json_bytes(payload)
    container = {
        "format_version": FORMAT_VERSION,
        "object_type": object_type,
        "payload_sha256": OBJECT_HASH + ":" + _sha256_hex(payload_bytes),
        "payload": payload,
    }
    return _object_id_from_container(container)


class _WriteLock(object):
    def __init__(self, lock_dir: Path, owner_path: Path):
        self._lock_dir = lock_dir
        self._owner_path = owner_path

    def release(self) -> None:
        if self._owner_path.exists():
            self._owner_path.unlink()
        if self._lock_dir.exists():
            self._lock_dir.rmdir()


class _RepositoryBackend(object):
    """
    Internal repository backend for the MVP.
    """

    def __init__(self, repo_path: Path):
        self._repo_path = Path(repo_path)

    def create_repo(
        self,
        default_branch: str = DEFAULT_BRANCH,
        exist_ok: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> RepoInfo:
        """
        Create a repository at the configured root path.
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

            for operation in operations:
                if isinstance(operation, CommitOperationAdd):
                    normalized_path = _normalize_repo_path(operation.path_in_repo)
                    _, file_object_id, _ = self._stage_add_operation(txdir, operation)
                    staged_snapshot[normalized_path] = file_object_id
                elif isinstance(operation, CommitOperationDelete):
                    self._apply_delete(staged_snapshot, operation.path_in_repo)
                elif isinstance(operation, CommitOperationCopy):
                    self._apply_copy(staged_snapshot, operation.src_path_in_repo, operation.path_in_repo)
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
        expand: bool = False,
    ) -> List[PathInfo]:
        """
        Return public metadata for the requested paths.
        """

        del expand  # Reserved for a later phase.
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
        """

        snapshot = self._snapshot_for_revision(revision)
        return sorted(snapshot)

    def open_file(self, path_in_repo: str, revision: str = DEFAULT_BRANCH) -> io.BufferedReader:
        """
        Open a file from a revision as a read-only binary stream.
        """

        data = self.read_bytes(path_in_repo, revision=revision)
        return io.BufferedReader(io.BytesIO(data))

    def read_bytes(self, path_in_repo: str, revision: str = DEFAULT_BRANCH) -> bytes:
        """
        Read a file from a revision into memory.
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
        repo_id: str,
        filename: str,
        revision: Optional[str] = None,
        local_dir: Optional[str] = None,
    ) -> str:
        """
        Materialize a detached user view for a file and return its path.
        """

        del repo_id
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
                "sha256": file_payload["sha256"],
                "oid": file_payload["oid"],
                "target_path": str(target_path.relative_to(self._repo_path)),
                "created_at": _utc_now(),
            },
        )
        return str(target_path)

    def reset_ref(self, ref_name: str, to_revision: str) -> CommitInfo:
        """
        Reset a branch ref to a target commit.
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
                    data_sha256 = OBJECT_HASH + ":" + _sha256_hex(target_path.read_bytes())
                    if data_sha256 != view_meta["sha256"]:
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
        return self._repo_path / "FORMAT"

    @property
    def _repo_config_path(self) -> Path:
        return self._repo_path / "repo.json"

    def _is_repo(self) -> bool:
        return self._format_path.is_file() and self._repo_config_path.is_file()

    def _ensure_layout(self) -> None:
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
        if not self._is_repo():
            raise RepoNotFoundError("repository not found")
        self._ensure_layout()

    def _repo_config(self) -> Dict[str, object]:
        return dict(_read_json(self._repo_config_path))

    def _list_refs(self) -> List[str]:
        refs = []
        refs.extend("refs/heads/" + name for name in self._list_branch_names())
        refs.extend("refs/tags/" + name for name in self._list_tag_names())
        return sorted(refs)

    def _list_branch_names(self) -> List[str]:
        heads_dir = self._repo_path / "refs" / "heads"
        if not heads_dir.exists():
            return []
        return self._list_ref_names_under(heads_dir)

    def _list_tag_names(self) -> List[str]:
        tags_dir = self._repo_path / "refs" / "tags"
        if not tags_dir.exists():
            return []
        return self._list_ref_names_under(tags_dir)

    def _list_ref_names_under(self, root: Path) -> List[str]:
        names = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            names.append(path.relative_to(root).as_posix())
        return names

    def _ref_path(self, name: str) -> Path:
        return self._repo_path / "refs" / "heads" / name

    def _tag_ref_path(self, name: str) -> Path:
        return self._repo_path / "refs" / "tags" / name

    def _reflog_path(self, name: str) -> Path:
        return self._repo_path / "logs" / "refs" / "heads" / (name + ".log")

    def _write_ref(self, name: str, commit_id: Optional[str]) -> None:
        path = self._ref_path(name)
        content = "" if commit_id is None else commit_id + "\n"
        _write_text_atomic(path, content)

    def _read_ref(self, name: str) -> Optional[str]:
        path = self._ref_path(name)
        if not path.exists():
            raise RevisionNotFoundError("branch not found: %s" % name)
        content = _read_text(path).strip()
        return content or None

    def _read_tag_ref(self, name: str) -> Optional[str]:
        path = self._tag_ref_path(name)
        if not path.exists():
            raise RevisionNotFoundError("tag not found: %s" % name)
        content = _read_text(path).strip()
        return content or None

    def _resolve_revision(self, revision: str, allow_empty_ref: bool = False) -> Optional[str]:
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
        if parent_commit is not None and expected_head is not None and parent_commit != expected_head:
            raise ConflictError("parent_commit and expected_head disagree")
        return expected_head if expected_head is not None else parent_commit

    def _object_json_path(self, object_type: str, object_id: str) -> Path:
        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".json"
        return self._repo_path / "objects" / object_type / OBJECT_HASH / prefix / filename

    def _blob_meta_path(self, object_id: str) -> Path:
        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".meta.json"
        return self._repo_path / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _blob_data_path(self, object_id: str) -> Path:
        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".data"
        return self._repo_path / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _object_exists(self, object_type: str, object_id: str) -> bool:
        if object_type == "blobs":
            return self._blob_meta_path(object_id).exists() and self._blob_data_path(object_id).exists()
        return self._object_json_path(object_type, object_id).exists()

    def _stage_json_object(self, txdir: Path, object_type: str, payload: object) -> str:
        object_id, container_bytes = _build_object_container(object_type[:-1], payload)
        path = self._stage_object_json_path(txdir, object_type, object_id)
        if not path.exists():
            _write_bytes_atomic(path, container_bytes)
        return object_id

    def _stage_blob_object(self, txdir: Path, payload: object, data: bytes) -> str:
        object_id, container_bytes = _build_object_container("blob", payload)
        meta_path = self._stage_blob_meta_path(txdir, object_id)
        data_path = self._stage_blob_data_path(txdir, object_id)
        if not meta_path.exists():
            _write_bytes_atomic(meta_path, container_bytes)
        if not data_path.exists():
            _write_bytes_atomic(data_path, data)
        return object_id

    def _stage_object_json_path(self, txdir: Path, object_type: str, object_id: str) -> Path:
        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".json"
        return txdir / "objects" / object_type / OBJECT_HASH / prefix / filename

    def _stage_blob_meta_path(self, txdir: Path, object_id: str) -> Path:
        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".meta.json"
        return txdir / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _stage_blob_data_path(self, txdir: Path, object_id: str) -> Path:
        _, digest = _split_object_id(object_id)
        prefix = digest[:2]
        filename = digest[2:] + ".data"
        return txdir / "objects" / "blobs" / OBJECT_HASH / prefix / filename

    def _read_object_payload(self, object_type: str, object_id: str) -> Dict[str, object]:
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
        head = self._resolve_revision(revision)
        return self._snapshot_for_commit(head)

    def _snapshot_for_commit(self, commit_id: Optional[str]) -> Dict[str, str]:
        if commit_id is None:
            return {}
        commit_payload = self._read_object_payload("commits", commit_id)
        return self._snapshot_for_tree(str(commit_payload["tree_id"]), prefix="")

    def _snapshot_for_tree(self, tree_id: str, prefix: str) -> Dict[str, str]:
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
        payload = self._read_object_payload("files", file_object_id)
        return PathInfo(
            path=path,
            path_type="file",
            size=int(payload["logical_size"]),
            oid=str(payload["oid"]),
            blob_id=str(payload["oid"]),
            sha256=str(payload["sha256"]),
            etag=str(payload["etag"]),
        )

    def _stage_add_operation(
        self,
        txdir: Path,
        operation: CommitOperationAdd,
    ) -> Tuple[str, str, Dict[str, object]]:
        normalized_path = _normalize_repo_path(operation.path_in_repo)
        data = operation.data
        file_sha256 = OBJECT_HASH + ":" + _sha256_hex(data)
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
            "sha256": file_sha256,
            "oid": oid,
            "etag": oid,
            "content_type_hint": operation.content_type,
            "content_object_id": blob_object_id,
            "chunks": [],
        }
        file_object_id = self._stage_json_object(txdir, "files", file_payload)
        return blob_object_id, file_object_id, file_payload

    def _apply_delete(self, snapshot: Dict[str, str], path_in_repo: str) -> None:
        normalized_path = _normalize_repo_path(path_in_repo)
        removed = False
        if normalized_path in snapshot:
            del snapshot[normalized_path]
            removed = True
        prefix = normalized_path + "/"
        for path in list(snapshot):
            if path.startswith(prefix):
                del snapshot[path]
                removed = True
        if not removed:
            raise PathNotFoundError("path not found: %s" % normalized_path)

    def _apply_copy(self, snapshot: Dict[str, str], src_path_in_repo: str, dst_path_in_repo: str) -> None:
        src_path = _normalize_repo_path(src_path_in_repo)
        dst_path = _normalize_repo_path(dst_path_in_repo)

        if src_path in snapshot:
            snapshot[dst_path] = snapshot[src_path]
            return

        prefix = src_path + "/"
        matches = [(path, object_id) for path, object_id in snapshot.items() if path.startswith(prefix)]
        if not matches:
            raise PathNotFoundError("path not found: %s" % src_path)
        for path, object_id in matches:
            suffix = path[len(prefix):]
            snapshot[dst_path + "/" + suffix] = object_id

    def _validate_snapshot(self, snapshot: Dict[str, str]) -> None:
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
        nested = {}
        for path, file_object_id in snapshot.items():
            current = nested
            parts = path.split("/")
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = file_object_id

        return self._stage_tree_node(txdir, nested)

    def _stage_tree_node(self, txdir: Path, node: Dict[str, object]) -> str:
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
        staged_path = self._stage_object_json_path(txdir, "files", object_id)
        if staged_path.exists():
            return dict(_read_json(staged_path)["payload"])
        return self._read_object_payload("files", object_id)

    def _publish_staged_objects(self, txdir: Path) -> None:
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
        commit_payload = self._read_object_payload("commits", commit_id)
        return CommitInfo(
            commit_id=commit_id,
            revision=revision,
            tree_id=str(commit_payload["tree_id"]),
            parents=list(commit_payload.get("parents", [])),
            message=str(commit_payload.get("message", "")),
        )

    def _verify_commit_closure(self, commit_id: str) -> None:
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
        try:
            payload = self._read_object_payload("files", file_object_id)
            blob_object_id = str(payload["content_object_id"])
            blob_payload = self._read_object_payload("blobs", blob_object_id)
            data_path = self._blob_data_path(blob_object_id)
            if not data_path.exists():
                raise IntegrityError("blob data missing")
            data = data_path.read_bytes()
            data_sha256 = OBJECT_HASH + ":" + _sha256_hex(data)
            if data_sha256 != payload["sha256"]:
                raise IntegrityError("file sha256 mismatch")
            if data_sha256 != blob_payload["payload_sha256"]:
                raise IntegrityError("blob payload sha256 mismatch")
            if _git_blob_oid(data) != payload["oid"]:
                raise IntegrityError("file oid mismatch")
        except (FileNotFoundError, KeyError, TypeError, ValueError, RevisionNotFoundError) as err:
            raise IntegrityError("invalid file object %s: %s" % (file_object_id, err))

    def _acquire_write_lock(self) -> _WriteLock:
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
        _write_json_atomic(txdir / "STATE.json", {"state": state, "updated_at": _utc_now()})

    def _cleanup_txdir(self, txdir: Path) -> None:
        if txdir.exists():
            shutil.rmtree(str(txdir))

    def _recover_transactions(self) -> None:
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
        content_key = str(file_payload["sha256"]).split(":", 1)[1]
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
                "sha256": file_payload["sha256"],
                "size": file_payload["logical_size"],
                "created_at": _utc_now(),
            },
        )

    def _ensure_detached_view(self, target_path: Path, data: bytes, file_payload: Dict[str, object]) -> None:
        expected_sha256 = str(file_payload["sha256"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            if target_path.is_symlink():
                target_path.unlink()
            elif target_path.is_dir():
                shutil.rmtree(str(target_path))
            elif target_path.is_file():
                current_sha256 = OBJECT_HASH + ":" + _sha256_hex(target_path.read_bytes())
                if current_sha256 == expected_sha256:
                    return
                target_path.unlink()
            else:  # pragma: no cover - defensive path for unusual filesystem nodes
                target_path.unlink()
        _write_bytes_atomic(target_path, data)
