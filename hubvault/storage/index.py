"""
Immutable index-segment helpers for :mod:`hubvault.storage`.

This module provides the minimal file-based index and manifest layer used by
Phase 3 chunked storage. Segment files are immutable once written, while the
manifest is the single mutable entry point that makes staged segments visible.

The module contains:

* :class:`IndexEntry` - Mapping from a chunk ID to a physical pack location
* :class:`IndexManifest` - Visible index-segment manifest
* :class:`IndexStore` - Reader and writer for index segments and manifests

Example::

    >>> from pathlib import Path
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmpdir:
    ...     store = IndexStore(Path(tmpdir))
    ...     manifest = IndexManifest.empty().add_segment("L0", "seg-demo.idx")
    ...     store.write_segment("L0", "seg-demo.idx", [IndexEntry("sha256:a", "pack", 16, 4, 4, "none", "sha256:a")])
    ...     store.write_manifest(manifest)
    ...     store.lookup("sha256:a").pack_id
    'pack'
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union

from ..errors import IntegrityError

INDEX_LEVELS = ("L0", "L1", "L2")


def _fsync_directory(path: Path) -> None:
    """
    Best-effort fsync of a directory entry boundary.

    :param path: Directory path to fsync
    :type path: pathlib.Path
    :return: ``None``.
    :rtype: None
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
    Encode JSON using stable key and whitespace rules.

    :param data: JSON-serializable value
    :type data: object
    :return: Stable UTF-8 JSON bytes
    :rtype: bytes
    """

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """
    Atomically replace a file with bytes.

    :param path: Target file path
    :type path: pathlib.Path
    :param data: File content bytes
    :type data: bytes
    :return: ``None``.
    :rtype: None
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("wb") as file_:
        file_.write(data)
        file_.flush()
        os.fsync(file_.fileno())
    os.replace(str(temp_path), str(path))
    _fsync_directory(path.parent)


@dataclass(frozen=True)
class IndexEntry:
    """
    Map one chunk identifier to its physical pack location.

    :param chunk_id: Internal chunk identifier
    :type chunk_id: str
    :param pack_id: Pack identifier without the file suffix
    :type pack_id: str
    :param offset: Absolute byte offset inside the pack file
    :type offset: int
    :param stored_size: Stored chunk size in bytes
    :type stored_size: int
    :param logical_size: Logical chunk size in bytes
    :type logical_size: int
    :param compression: Compression label, usually ``"none"``
    :type compression: str
    :param checksum: Integrity checksum for the logical chunk payload
    :type checksum: str

    Example::

        >>> entry = IndexEntry("sha256:a", "pack", 16, 4, 4, "none", "sha256:a")
        >>> entry.offset
        16
    """

    chunk_id: str
    pack_id: str
    offset: int
    stored_size: int
    logical_size: int
    compression: str
    checksum: str

    def to_dict(self) -> Dict[str, object]:
        """
        Convert the entry to a JSON-serializable mapping.

        :return: JSON-serializable entry mapping
        :rtype: Dict[str, object]

        Example::

            >>> IndexEntry("sha256:a", "pack", 16, 4, 4, "none", "sha256:a").to_dict()["pack_id"]
            'pack'
        """

        return {
            "chunk_id": self.chunk_id,
            "pack_id": self.pack_id,
            "offset": self.offset,
            "stored_size": self.stored_size,
            "logical_size": self.logical_size,
            "compression": self.compression,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "IndexEntry":
        """
        Build an index entry from a decoded JSON object.

        :param payload: Decoded JSON object
        :type payload: Dict[str, object]
        :return: Parsed index entry
        :rtype: IndexEntry
        :raises IntegrityError: Raised when the payload does not contain the
            required fields.

        Example::

            >>> IndexEntry.from_dict({'chunk_id': 'sha256:a', 'pack_id': 'pack', 'offset': 16, 'stored_size': 4, 'logical_size': 4, 'compression': 'none', 'checksum': 'sha256:a'}).pack_id
            'pack'
        """

        try:
            return cls(
                chunk_id=str(payload["chunk_id"]),
                pack_id=str(payload["pack_id"]),
                offset=int(payload["offset"]),
                stored_size=int(payload["stored_size"]),
                logical_size=int(payload["logical_size"]),
                compression=str(payload["compression"]),
                checksum=str(payload["checksum"]),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise IntegrityError("invalid index entry: %s" % err)


@dataclass(frozen=True)
class IndexManifest:
    """
    Describe the set of visible immutable index segments.

    :param levels: Segment filenames grouped by level name
    :type levels: Dict[str, Tuple[str, ...]]

    Example::

        >>> manifest = IndexManifest.empty().add_segment("L0", "seg-demo.idx")
        >>> manifest.levels["L0"]
        ('seg-demo.idx',)
    """

    levels: Dict[str, Tuple[str, ...]]

    @classmethod
    def empty(cls) -> "IndexManifest":
        """
        Build an empty manifest for all known levels.

        :return: Empty manifest
        :rtype: IndexManifest

        Example::

            >>> IndexManifest.empty().levels["L1"]
            ()
        """

        return cls(levels=dict((level, tuple()) for level in INDEX_LEVELS))

    def add_segment(self, level: str, segment_name: str) -> "IndexManifest":
        """
        Return a new manifest with one additional visible segment.

        :param level: Index level such as ``"L0"``
        :type level: str
        :param segment_name: Segment filename
        :type segment_name: str
        :return: Updated manifest
        :rtype: IndexManifest
        :raises ValueError: Raised when ``level`` is unknown.

        Example::

            >>> IndexManifest.empty().add_segment("L0", "seg-demo.idx").levels["L0"]
            ('seg-demo.idx',)
        """

        if level not in INDEX_LEVELS:
            raise ValueError("unknown index level: %s" % level)
        updated = {}
        for current_level in INDEX_LEVELS:
            items = list(self.levels.get(current_level, tuple()))
            if current_level == level and segment_name not in items:
                items.append(segment_name)
            updated[current_level] = tuple(items)
        return IndexManifest(levels=updated)

    def to_dict(self) -> Dict[str, object]:
        """
        Convert the manifest to a JSON-serializable mapping.

        :return: JSON-serializable manifest mapping
        :rtype: Dict[str, object]

        Example::

            >>> IndexManifest.empty().to_dict()["levels"]["L2"]
            []
        """

        return {
            "format_version": 1,
            "levels": dict((level, list(self.levels.get(level, tuple()))) for level in INDEX_LEVELS),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "IndexManifest":
        """
        Parse a manifest from a decoded JSON object.

        :param payload: Decoded JSON object
        :type payload: Dict[str, object]
        :return: Parsed manifest
        :rtype: IndexManifest
        :raises IntegrityError: Raised when the payload is malformed.

        Example::

            >>> IndexManifest.from_dict({'format_version': 1, 'levels': {'L0': ['seg.idx'], 'L1': [], 'L2': []}}).levels['L0']
            ('seg.idx',)
        """

        try:
            raw_levels = payload["levels"]
            if not isinstance(raw_levels, dict):
                raise TypeError("levels must be a mapping")
            levels = {}
            for level in INDEX_LEVELS:
                raw_items = raw_levels.get(level, [])
                if not isinstance(raw_items, list):
                    raise TypeError("level %s must be a list" % level)
                levels[level] = tuple(str(item) for item in raw_items)
            return cls(levels=levels)
        except (KeyError, TypeError, ValueError) as err:
            raise IntegrityError("invalid manifest: %s" % err)


class IndexStore:
    """
    Read and write immutable index segments and the visible manifest.

    :param index_dir: Directory containing ``MANIFEST`` and level subdirectories
    :type index_dir: Union[str, pathlib.Path]

    Example::

        >>> IndexStore("/tmp/index").index_dir.name
        'index'
    """

    def __init__(self, index_dir: Union[str, Path]) -> None:
        """
        Initialize the index store.

        :param index_dir: Directory containing ``MANIFEST`` and level subdirectories
        :type index_dir: Union[str, pathlib.Path]
        :return: ``None``.
        :rtype: None

        Example::

            >>> IndexStore("/tmp/index").index_dir.name
            'index'
        """

        self.index_dir = Path(index_dir)

    @property
    def manifest_path(self) -> Path:
        """
        Return the manifest file path.

        :return: Absolute manifest path
        :rtype: pathlib.Path

        Example::

            >>> IndexStore("/tmp/index").manifest_path.name
            'MANIFEST'
        """

        return self.index_dir / "MANIFEST"

    def segment_path(self, level: str, segment_name: str) -> Path:
        """
        Build the path for one immutable segment.

        :param level: Index level such as ``"L0"``
        :type level: str
        :param segment_name: Segment filename
        :type segment_name: str
        :return: Absolute segment path
        :rtype: pathlib.Path
        :raises ValueError: Raised when ``level`` is unknown.

        Example::

            >>> IndexStore("/tmp/index").segment_path("L0", "seg.idx").as_posix().endswith("L0/seg.idx")
            True
        """

        if level not in INDEX_LEVELS:
            raise ValueError("unknown index level: %s" % level)
        return self.index_dir / level / segment_name

    def read_manifest(self) -> IndexManifest:
        """
        Load the current visible manifest.

        :return: Parsed manifest, or an empty manifest when missing
        :rtype: IndexManifest
        :raises IntegrityError: Raised when the manifest file is malformed.

        Example::

            >>> IndexStore("/tmp/index").read_manifest().levels["L0"]
            ()
        """

        path = self.manifest_path
        if not path.exists():
            return IndexManifest.empty()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError) as err:
            raise IntegrityError("invalid manifest: %s" % err)
        if not isinstance(payload, dict):
            raise IntegrityError("invalid manifest: expected JSON object")
        return IndexManifest.from_dict(payload)

    def write_manifest(self, manifest: IndexManifest) -> None:
        """
        Atomically replace the visible manifest.

        :param manifest: Manifest to persist
        :type manifest: IndexManifest
        :return: ``None``.
        :rtype: None

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = IndexStore(Path(tmpdir))
            ...     store.write_manifest(IndexManifest.empty())
            ...     store.manifest_path.exists()
            True
        """

        self.index_dir.mkdir(parents=True, exist_ok=True)
        for level in INDEX_LEVELS:
            self.segment_path(level, "placeholder").parent.mkdir(parents=True, exist_ok=True)
        _write_bytes_atomic(self.manifest_path, _stable_json_bytes(manifest.to_dict()))

    def write_segment(self, level: str, segment_name: str, entries: Sequence[IndexEntry]) -> Path:
        """
        Persist an immutable index segment.

        :param level: Index level such as ``"L0"``
        :type level: str
        :param segment_name: Segment filename
        :type segment_name: str
        :param entries: Ordered index entries to write
        :type entries: Sequence[IndexEntry]
        :return: Absolute segment path
        :rtype: pathlib.Path
        :raises IntegrityError: Raised when the target segment already exists.

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = IndexStore(Path(tmpdir))
            ...     path = store.write_segment("L0", "seg.idx", [IndexEntry("sha256:a", "pack", 16, 4, 4, "none", "sha256:a")])
            ...     path.name
            'seg.idx'
        """

        path = self.segment_path(level, segment_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise IntegrityError("index segment already exists: %s" % segment_name)
        lines = []
        for entry in entries:
            lines.append(json.dumps(entry.to_dict(), sort_keys=True, ensure_ascii=False))
        payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        _write_bytes_atomic(path, payload)
        return path

    def load_segment(self, level: str, segment_name: str) -> Tuple[IndexEntry, ...]:
        """
        Load one immutable index segment.

        :param level: Index level such as ``"L0"``
        :type level: str
        :param segment_name: Segment filename
        :type segment_name: str
        :return: Parsed index entries
        :rtype: Tuple[IndexEntry, ...]
        :raises IntegrityError: Raised when the segment is missing or malformed.

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = IndexStore(Path(tmpdir))
            ...     _ = store.write_segment("L0", "seg.idx", [IndexEntry("sha256:a", "pack", 16, 4, 4, "none", "sha256:a")])
            ...     store.load_segment("L0", "seg.idx")[0].chunk_id
            'sha256:a'
        """

        path = self.segment_path(level, segment_name)
        if not path.exists():
            raise IntegrityError("index segment not found: %s" % segment_name)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as err:
            raise IntegrityError("failed to read index segment %s: %s" % (segment_name, err))

        entries = []
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError as err:
                raise IntegrityError("invalid index segment %s: %s" % (segment_name, err))
            if not isinstance(payload, dict):
                raise IntegrityError("invalid index segment %s: expected JSON object" % segment_name)
            entries.append(IndexEntry.from_dict(payload))
        return tuple(entries)

    def lookup(self, chunk_id: str, manifest: Optional[IndexManifest] = None) -> Optional[IndexEntry]:
        """
        Resolve a chunk identifier through the visible manifest.

        :param chunk_id: Internal chunk identifier
        :type chunk_id: str
        :param manifest: Optional already-loaded manifest
        :type manifest: Optional[IndexManifest]
        :return: Resolved index entry, or ``None`` when absent
        :rtype: Optional[IndexEntry]
        :raises IntegrityError: Raised when a visible segment cannot be read.

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = IndexStore(Path(tmpdir))
            ...     entry = IndexEntry("sha256:a", "pack", 16, 4, 4, "none", "sha256:a")
            ...     _ = store.write_segment("L0", "seg.idx", [entry])
            ...     store.write_manifest(IndexManifest.empty().add_segment("L0", "seg.idx"))
            ...     store.lookup("sha256:a").pack_id
            'pack'
        """

        active_manifest = manifest or self.read_manifest()
        for level in INDEX_LEVELS:
            for segment_name in reversed(active_manifest.levels.get(level, tuple())):
                entries = self.load_segment(level, segment_name)
                for entry in reversed(entries):
                    if entry.chunk_id == chunk_id:
                        return entry
        return None
