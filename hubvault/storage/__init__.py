"""
Storage package exports for :mod:`hubvault`.

This package groups the Phase 3 large-file storage helpers used by the
repository backend.

The package contains:

* :class:`ChunkStore` - Content-defined chunk planner for logical file payloads
* :class:`PackStore` - Append-only pack-file reader and writer
* :class:`IndexStore` - Immutable segment and manifest index layer

Example::

    >>> from hubvault.storage import ChunkStore, PackStore, IndexStore
    >>> ChunkStore is not None and PackStore is not None and IndexStore is not None
    True
"""

from .chunk import ChunkPlan, ChunkDescriptor, ChunkPart, ChunkStore, DEFAULT_CHUNK_SIZE, canonical_lfs_pointer, git_blob_oid
from .index import INDEX_LEVELS, IndexEntry, IndexManifest, IndexStore
from .pack import PACK_MAGIC, PackChunkLocation, PackStore, PackWriteResult

__all__ = [
    "ChunkDescriptor",
    "ChunkPart",
    "ChunkPlan",
    "ChunkStore",
    "DEFAULT_CHUNK_SIZE",
    "INDEX_LEVELS",
    "IndexEntry",
    "IndexManifest",
    "IndexStore",
    "PACK_MAGIC",
    "PackChunkLocation",
    "PackStore",
    "PackWriteResult",
    "canonical_lfs_pointer",
    "git_blob_oid",
]
