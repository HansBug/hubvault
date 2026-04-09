"""
Chunk planning helpers for :mod:`hubvault.storage`.

This module contains the chunk-planning logic used by the local repository
backend when a file is large enough to switch from whole-blob storage to
chunked pack storage. Phase 10 upgrades this path from fixed-size splitting to
FastCDC content-defined chunking and uses ``blake3`` as the planner's fast
digest.

The module contains:

* :class:`ChunkDescriptor` - Logical metadata for one chunk in a file
* :class:`ChunkPart` - Chunk descriptor paired with chunk payload bytes
* :class:`ChunkPlan` - Full chunk plan and LFS-style public metadata for a file
* :class:`ChunkStore` - Planner that splits bytes into content-defined chunks
* :func:`canonical_lfs_pointer` - Build canonical Git LFS pointer bytes
* :func:`git_blob_oid` - Compute a Git-compatible blob OID

Example::

    >>> store = ChunkStore(chunk_size=256, min_chunk_size=64, max_chunk_size=1024)
    >>> plan = store.plan_bytes(b"abcdefgh")
    >>> sum(chunk.logical_size for chunk in plan.chunks)
    8
    >>> plan.etag == plan.sha256
    True
"""

from blake3 import blake3
from dataclasses import dataclass
from fastcdc import fastcdc
from hashlib import sha1, sha256
from typing import Optional, Tuple

OBJECT_HASH = "sha256"
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024
DEFAULT_MIN_CHUNK_SIZE = max(64, DEFAULT_CHUNK_SIZE // 4)
DEFAULT_MAX_CHUNK_SIZE = DEFAULT_CHUNK_SIZE * 4
FASTCDC_MIN_CHUNK_SIZE = 64
FASTCDC_MIN_AVG_SIZE = 256
FASTCDC_MIN_MAX_SIZE = 1024


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

        >>> store = ChunkStore(chunk_size=256, min_chunk_size=64, max_chunk_size=1024)
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

    :param chunk_size: Target average chunk size in bytes, defaults to
        :data:`DEFAULT_CHUNK_SIZE`
    :type chunk_size: int, optional
    :param min_chunk_size: Optional minimum chunk size, defaults to
        :data:`DEFAULT_MIN_CHUNK_SIZE`
    :type min_chunk_size: Optional[int], optional
    :param max_chunk_size: Optional maximum chunk size, defaults to
        :data:`DEFAULT_MAX_CHUNK_SIZE`
    :type max_chunk_size: Optional[int], optional
    :raises ValueError: Raised when the chunk-size settings are invalid.

    Example::

        >>> store = ChunkStore(chunk_size=256, min_chunk_size=64, max_chunk_size=1024)
        >>> store.chunk_size
        256
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        min_chunk_size: Optional[int] = None,
        max_chunk_size: Optional[int] = None,
    ) -> None:
        """
        Initialize the chunk planner.

        :param chunk_size: Target average chunk size in bytes, defaults to
            :data:`DEFAULT_CHUNK_SIZE`
        :type chunk_size: int, optional
        :param min_chunk_size: Optional minimum chunk size, defaults to
            :data:`DEFAULT_MIN_CHUNK_SIZE`
        :type min_chunk_size: Optional[int], optional
        :param max_chunk_size: Optional maximum chunk size, defaults to
            :data:`DEFAULT_MAX_CHUNK_SIZE`
        :type max_chunk_size: Optional[int], optional
        :return: ``None``.
        :rtype: None
        :raises ValueError: Raised when the chunk-size settings are invalid.

        Example::

            >>> ChunkStore(chunk_size=256, min_chunk_size=64, max_chunk_size=1024).chunk_size
            256
        """

        chunk_size = int(chunk_size)
        if chunk_size < FASTCDC_MIN_AVG_SIZE:
            raise ValueError("chunk_size must be >= %d" % FASTCDC_MIN_AVG_SIZE)
        self.chunk_size = chunk_size
        self.min_chunk_size = int(min_chunk_size) if min_chunk_size is not None else max(64, chunk_size // 4)
        self.max_chunk_size = int(max_chunk_size) if max_chunk_size is not None else max(chunk_size, chunk_size * 4)
        if self.min_chunk_size < FASTCDC_MIN_CHUNK_SIZE:
            raise ValueError("min_chunk_size must be >= %d" % FASTCDC_MIN_CHUNK_SIZE)
        if self.max_chunk_size < FASTCDC_MIN_MAX_SIZE:
            raise ValueError("max_chunk_size must be >= %d" % FASTCDC_MIN_MAX_SIZE)
        if self.max_chunk_size < self.chunk_size:
            raise ValueError("max_chunk_size must be >= chunk_size")
        if self.min_chunk_size > self.chunk_size:
            raise ValueError("min_chunk_size must be <= chunk_size")
        self.algorithm = "fastcdc"

    def plan_bytes(self, data: bytes) -> ChunkPlan:
        """
        Split bytes into content-defined chunks and compute public metadata.

        :param data: Logical file payload bytes
        :type data: bytes
        :return: Chunk plan with chunk descriptors and canonical LFS metadata
        :rtype: ChunkPlan
        :raises ValueError: Raised when ``data`` is not byte-like.

        Example::

            >>> store = ChunkStore(chunk_size=256, min_chunk_size=64, max_chunk_size=1024)
            >>> plan = store.plan_bytes(b"abcdefgh")
            >>> sum(len(part.data) for part in plan.parts)
            8
        """

        if not isinstance(data, (bytes, bytearray)):
            raise ValueError("data must be bytes or bytearray")
        payload = bytes(data)

        file_sha256 = sha256_hex(payload)
        pointer = canonical_lfs_pointer(file_sha256, len(payload))
        parts = []
        chunk_digest_cache = {}
        for boundary in fastcdc(
            payload,
            min_size=self.min_chunk_size,
            avg_size=self.chunk_size,
            max_size=self.max_chunk_size,
            hf=blake3,
        ):
            chunk = payload[int(boundary.offset):int(boundary.offset) + int(boundary.length)]
            cache_key = (str(boundary.hash) or None, len(chunk))
            chunk_digest = None
            cached_items = chunk_digest_cache.get(cache_key, tuple())
            for cached_chunk, cached_digest in cached_items:
                if cached_chunk == chunk:
                    chunk_digest = cached_digest
                    break
            if chunk_digest is None:
                chunk_digest = sha256_hex(chunk)
                chunk_digest_cache.setdefault(cache_key, []).append((chunk, chunk_digest))
            descriptor = ChunkDescriptor(
                chunk_id=OBJECT_HASH + ":" + chunk_digest,
                checksum=OBJECT_HASH + ":" + chunk_digest,
                logical_offset=int(boundary.offset),
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
