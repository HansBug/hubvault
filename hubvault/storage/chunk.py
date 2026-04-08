"""
Chunk planning helpers for :mod:`hubvault.storage`.

This module contains the deterministic chunk-planning logic used by the local
repository backend when a file is large enough to switch from whole-blob
storage to chunked pack storage.

The module contains:

* :class:`ChunkDescriptor` - Logical metadata for one chunk in a file
* :class:`ChunkPart` - Chunk descriptor paired with chunk payload bytes
* :class:`ChunkPlan` - Full chunk plan and LFS-style public metadata for a file
* :class:`ChunkStore` - Planner that splits bytes into deterministic chunks
* :func:`canonical_lfs_pointer` - Build canonical Git LFS pointer bytes
* :func:`git_blob_oid` - Compute a Git-compatible blob OID

Example::

    >>> store = ChunkStore(chunk_size=4)
    >>> plan = store.plan_bytes(b"abcdefgh")
    >>> len(plan.chunks)
    2
    >>> plan.etag == plan.sha256
    True
"""

from dataclasses import dataclass
from hashlib import sha1, sha256
from typing import Tuple

OBJECT_HASH = "sha256"
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024


def sha256_hex(data: bytes) -> str:
    """
    Compute a lowercase hexadecimal SHA-256 digest.

    :param data: Input bytes
    :type data: bytes
    :return: Lowercase hexadecimal digest
    :rtype: str

    Example::

        >>> sha256_hex(b"abc")
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    """

    return sha256(data).hexdigest()


def git_blob_oid(data: bytes) -> str:
    """
    Compute a Git-compatible blob OID for bytes.

    :param data: Blob payload bytes
    :type data: bytes
    :return: Git SHA-1 blob OID without a prefix
    :rtype: str

    Example::

        >>> len(git_blob_oid(b"abc"))
        40
    """

    header = ("blob %d\0" % len(data)).encode("utf-8")
    return sha1(header + data).hexdigest()


def canonical_lfs_pointer(file_sha256: str, size: int) -> bytes:
    """
    Build canonical Git LFS pointer bytes for a file.

    :param file_sha256: Raw hexadecimal SHA-256 digest of the logical file
    :type file_sha256: str
    :param size: Logical file size in bytes
    :type size: int
    :return: Canonical pointer payload bytes
    :rtype: bytes

    Example::

        >>> canonical_lfs_pointer("a" * 64, 5).startswith(b"version https://git-lfs.github.com/spec/v1\\n")
        True
    """

    return (
        "version https://git-lfs.github.com/spec/v1\n"
        "oid sha256:%s\n"
        "size %d\n"
    ).encode("utf-8") % (file_sha256.encode("utf-8"), size)


@dataclass(frozen=True)
class ChunkDescriptor:
    """
    Describe one logical chunk inside a larger file.

    :param chunk_id: Internal chunk identifier with an explicit hash prefix
    :type chunk_id: str
    :param checksum: Integrity checksum for the logical chunk payload
    :type checksum: str
    :param logical_offset: Starting byte offset within the logical file
    :type logical_offset: int
    :param logical_size: Logical chunk size in bytes
    :type logical_size: int
    :param stored_size: Stored chunk size in bytes
    :type stored_size: int
    :param compression: Storage compression label, defaults to ``"none"``
    :type compression: str, optional

    Example::

        >>> descriptor = ChunkDescriptor("sha256:" + "a" * 64, "sha256:" + "a" * 64, 0, 4, 4)
        >>> descriptor.logical_offset
        0
    """

    chunk_id: str
    checksum: str
    logical_offset: int
    logical_size: int
    stored_size: int
    compression: str = "none"


@dataclass(frozen=True)
class ChunkPart:
    """
    Pair a chunk descriptor with its payload bytes.

    :param descriptor: Logical chunk metadata
    :type descriptor: ChunkDescriptor
    :param data: Chunk payload bytes
    :type data: bytes

    Example::

        >>> part = ChunkPart(ChunkDescriptor("sha256:" + "a" * 64, "sha256:" + "a" * 64, 0, 4, 4), b"data")
        >>> part.data
        b'data'
    """

    descriptor: ChunkDescriptor
    data: bytes


@dataclass(frozen=True)
class ChunkPlan:
    """
    Describe the chunked storage plan for one logical file.

    :param logical_size: Logical file size in bytes
    :type logical_size: int
    :param sha256: Raw hexadecimal SHA-256 digest of the logical file
    :type sha256: str
    :param oid: Git blob OID of the canonical LFS pointer
    :type oid: str
    :param etag: Public ETag value, aligned with the file SHA-256 for LFS mode
    :type etag: str
    :param pointer_size: Size of the canonical LFS pointer in bytes
    :type pointer_size: int
    :param chunks: Ordered logical chunk descriptors
    :type chunks: Tuple[ChunkDescriptor, ...]
    :param parts: Ordered chunk payloads paired with descriptors
    :type parts: Tuple[ChunkPart, ...]

    Example::

        >>> store = ChunkStore(chunk_size=3)
        >>> plan = store.plan_bytes(b"abcdef")
        >>> plan.pointer_size > 0
        True
    """

    logical_size: int
    sha256: str
    oid: str
    etag: str
    pointer_size: int
    chunks: Tuple[ChunkDescriptor, ...]
    parts: Tuple[ChunkPart, ...]


class ChunkStore:
    """
    Build deterministic chunk plans for large file payloads.

    :param chunk_size: Maximum chunk size in bytes, defaults to
        :data:`DEFAULT_CHUNK_SIZE`
    :type chunk_size: int, optional
    :raises ValueError: Raised when ``chunk_size`` is not positive.

    Example::

        >>> store = ChunkStore(chunk_size=4)
        >>> store.chunk_size
        4
    """

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        """
        Initialize the chunk planner.

        :param chunk_size: Maximum chunk size in bytes, defaults to
            :data:`DEFAULT_CHUNK_SIZE`
        :type chunk_size: int, optional
        :return: ``None``.
        :rtype: None
        :raises ValueError: Raised when ``chunk_size`` is not positive.

        Example::

            >>> ChunkStore(chunk_size=1).chunk_size
            1
        """

        chunk_size = int(chunk_size)
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        self.chunk_size = chunk_size

    def plan_bytes(self, data: bytes) -> ChunkPlan:
        """
        Split bytes into deterministic chunks and compute public metadata.

        :param data: Logical file payload bytes
        :type data: bytes
        :return: Chunk plan with chunk descriptors and canonical LFS metadata
        :rtype: ChunkPlan
        :raises ValueError: Raised when ``data`` is not byte-like.

        Example::

            >>> store = ChunkStore(chunk_size=4)
            >>> plan = store.plan_bytes(b"abcdefgh")
            >>> [part.data for part in plan.parts]
            [b'abcd', b'efgh']
        """

        if not isinstance(data, (bytes, bytearray)):
            raise ValueError("data must be bytes or bytearray")
        payload = bytes(data)

        file_sha256 = sha256_hex(payload)
        pointer = canonical_lfs_pointer(file_sha256, len(payload))
        parts = []
        for index in range(0, len(payload), self.chunk_size):
            chunk = payload[index:index + self.chunk_size]
            chunk_digest = sha256_hex(chunk)
            descriptor = ChunkDescriptor(
                chunk_id=OBJECT_HASH + ":" + chunk_digest,
                checksum=OBJECT_HASH + ":" + chunk_digest,
                logical_offset=index,
                logical_size=len(chunk),
                stored_size=len(chunk),
                compression="none",
            )
            parts.append(ChunkPart(descriptor=descriptor, data=chunk))

        return ChunkPlan(
            logical_size=len(payload),
            sha256=file_sha256,
            oid=git_blob_oid(pointer),
            etag=file_sha256,
            pointer_size=len(pointer),
            chunks=tuple(part.descriptor for part in parts),
            parts=tuple(parts),
        )
