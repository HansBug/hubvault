hubvault.storage.chunk
========================================================

.. currentmodule:: hubvault.storage.chunk

.. automodule:: hubvault.storage.chunk


OBJECT\_HASH
-----------------------------------------------------

.. autodata:: OBJECT_HASH


DEFAULT\_CHUNK\_SIZE
-----------------------------------------------------

.. autodata:: DEFAULT_CHUNK_SIZE


DEFAULT\_MIN\_CHUNK\_SIZE
-----------------------------------------------------

.. autodata:: DEFAULT_MIN_CHUNK_SIZE


DEFAULT\_MAX\_CHUNK\_SIZE
-----------------------------------------------------

.. autodata:: DEFAULT_MAX_CHUNK_SIZE


FASTCDC\_MIN\_CHUNK\_SIZE
-----------------------------------------------------

.. autodata:: FASTCDC_MIN_CHUNK_SIZE


FASTCDC\_MIN\_AVG\_SIZE
-----------------------------------------------------

.. autodata:: FASTCDC_MIN_AVG_SIZE


FASTCDC\_MIN\_MAX\_SIZE
-----------------------------------------------------

.. autodata:: FASTCDC_MIN_MAX_SIZE


ChunkDescriptor
-----------------------------------------------------

.. autoclass:: ChunkDescriptor
    :members: chunk_id,checksum,logical_offset,logical_size,stored_size,compression


ChunkPart
-----------------------------------------------------

.. autoclass:: ChunkPart
    :members: descriptor,data


ChunkPlan
-----------------------------------------------------

.. autoclass:: ChunkPlan
    :members: logical_size,sha256,oid,etag,pointer_size,chunks,parts


ChunkStore
-----------------------------------------------------

.. autoclass:: ChunkStore
    :members: __init__,plan_bytes


sha256\_hex
-----------------------------------------------------

.. autofunction:: sha256_hex


git\_blob\_oid
-----------------------------------------------------

.. autofunction:: git_blob_oid


canonical\_lfs\_pointer
-----------------------------------------------------

.. autofunction:: canonical_lfs_pointer


