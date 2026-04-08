"""
Append-only pack-file storage helpers for :mod:`hubvault.storage`.

This module provides a small pack-file abstraction used by the repository
backend to persist chunk payload bytes outside the immutable JSON object store.

The module contains:

* :class:`PackChunkLocation` - Physical location of one chunk inside a pack
* :class:`PackWriteResult` - Result metadata for a completed pack write
* :class:`PackStore` - Reader and writer for append-only pack files

Example::

    >>> from pathlib import Path
    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as tmpdir:
    ...     store = PackStore(Path(tmpdir))
    ...     result = store.write_pack("demo", [b"abc", b"def"])
    ...     store.read_chunk(result.chunks[0])
    b'abc'
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple, Union

from ..errors import IntegrityError

PACK_MAGIC = b"hubvault-pack/v1\n"


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


@dataclass(frozen=True)
class PackChunkLocation:
    """
    Describe the stored location of one chunk inside a pack file.

    :param pack_id: Pack identifier without the file suffix
    :type pack_id: str
    :param offset: Absolute byte offset inside the pack file
    :type offset: int
    :param stored_size: Stored chunk size in bytes
    :type stored_size: int
    :param logical_size: Logical chunk size in bytes
    :type logical_size: int

    Example::

        >>> location = PackChunkLocation("demo", 16, 4, 4)
        >>> location.pack_id
        'demo'
    """

    pack_id: str
    offset: int
    stored_size: int
    logical_size: int


@dataclass(frozen=True)
class PackWriteResult:
    """
    Summarize one completed pack write.

    :param pack_id: Pack identifier without the file suffix
    :type pack_id: str
    :param pack_path: Absolute pack path on disk
    :type pack_path: str
    :param total_size: Total pack size in bytes
    :type total_size: int
    :param chunks: Ordered chunk locations written into the pack
    :type chunks: Tuple[PackChunkLocation, ...]

    Example::

        >>> result = PackWriteResult("demo", "/tmp/demo.pack", 32, tuple())
        >>> result.pack_id
        'demo'
    """

    pack_id: str
    pack_path: str
    total_size: int
    chunks: Tuple[PackChunkLocation, ...]


class PackStore:
    """
    Read and write append-only chunk pack files.

    :param pack_dir: Directory containing ``.pack`` files
    :type pack_dir: Union[str, pathlib.Path]

    Example::

        >>> store = PackStore("/tmp/packs")
        >>> store.pack_dir.name
        'packs'
    """

    def __init__(self, pack_dir: Union[str, Path]) -> None:
        """
        Initialize the pack store.

        :param pack_dir: Directory containing ``.pack`` files
        :type pack_dir: Union[str, pathlib.Path]
        :return: ``None``.
        :rtype: None

        Example::

            >>> PackStore("/tmp/packs").pack_dir.name
            'packs'
        """

        self.pack_dir = Path(pack_dir)

    def pack_path(self, pack_id: str) -> Path:
        """
        Build the absolute path for a pack identifier.

        :param pack_id: Pack identifier without the file suffix
        :type pack_id: str
        :return: Absolute pack path
        :rtype: pathlib.Path

        Example::

            >>> PackStore("/tmp/packs").pack_path("demo").name
            'demo.pack'
        """

        return self.pack_dir / (str(pack_id) + ".pack")

    def write_pack(self, pack_id: str, chunks: Sequence[bytes]) -> PackWriteResult:
        """
        Write an append-only pack file for ordered chunk bytes.

        :param pack_id: Pack identifier without the file suffix
        :type pack_id: str
        :param chunks: Ordered chunk payloads to append
        :type chunks: Sequence[bytes]
        :return: Pack metadata and chunk locations
        :rtype: PackWriteResult
        :raises IntegrityError: Raised when the target pack already exists.

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = PackStore(Path(tmpdir))
            ...     result = store.write_pack("demo", [b"ab", b"cd"])
            ...     len(result.chunks)
            2
        """

        path = self.pack_path(pack_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise IntegrityError("pack already exists: %s" % pack_id)

        locations = []
        offset = len(PACK_MAGIC)
        with path.open("wb") as file_:
            file_.write(PACK_MAGIC)
            for chunk in chunks:
                payload = bytes(chunk)
                file_.write(payload)
                locations.append(
                    PackChunkLocation(
                        pack_id=str(pack_id),
                        offset=offset,
                        stored_size=len(payload),
                        logical_size=len(payload),
                    )
                )
                offset += len(payload)
            file_.flush()
            os.fsync(file_.fileno())
        _fsync_directory(path.parent)

        return PackWriteResult(
            pack_id=str(pack_id),
            pack_path=str(path),
            total_size=offset,
            chunks=tuple(locations),
        )

    def read_chunk(self, location: PackChunkLocation) -> bytes:
        """
        Read one full chunk from a pack file.

        :param location: Stored chunk location
        :type location: PackChunkLocation
        :return: Chunk payload bytes
        :rtype: bytes
        :raises IntegrityError: Raised when the pack is missing or truncated.

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = PackStore(Path(tmpdir))
            ...     result = store.write_pack("demo", [b"abc"])
            ...     store.read_chunk(result.chunks[0])
            b'abc'
        """

        return self.read_range(location.pack_id, location.offset, location.stored_size)

    def read_range(self, pack_id: str, offset: int, length: int) -> bytes:
        """
        Read a byte range from a pack file.

        :param pack_id: Pack identifier without the file suffix
        :type pack_id: str
        :param offset: Absolute byte offset inside the pack file
        :type offset: int
        :param length: Number of bytes to read
        :type length: int
        :return: Requested byte range
        :rtype: bytes
        :raises IntegrityError: Raised when the pack header is invalid, the pack
            is missing, or the requested range exceeds the pack size.
        :raises ValueError: Raised when ``offset`` or ``length`` is negative.

        Example::

            >>> from pathlib import Path
            >>> import tempfile
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     store = PackStore(Path(tmpdir))
            ...     result = store.write_pack("demo", [b"abcdef"])
            ...     store.read_range("demo", result.chunks[0].offset + 1, 3)
            b'bcd'
        """

        offset = int(offset)
        length = int(length)
        if offset < 0 or length < 0:
            raise ValueError("offset and length must be >= 0")

        path = self.pack_path(pack_id)
        if not path.exists():
            raise IntegrityError("pack not found: %s" % pack_id)

        with path.open("rb") as file_:
            magic = file_.read(len(PACK_MAGIC))
            if magic != PACK_MAGIC:
                raise IntegrityError("invalid pack header: %s" % pack_id)
            pack_size = path.stat().st_size
            if offset < len(PACK_MAGIC):
                raise IntegrityError("range overlaps pack header: %s" % pack_id)
            if offset + length > pack_size:
                raise IntegrityError("pack truncated: %s" % pack_id)
            file_.seek(offset)
            data = file_.read(length)
        if len(data) != length:
            raise IntegrityError("pack truncated: %s" % pack_id)
        return data
