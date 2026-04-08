hubvault.storage.pack
========================================================

.. currentmodule:: hubvault.storage.pack

.. automodule:: hubvault.storage.pack


PACK\_MAGIC
-----------------------------------------------------

.. autodata:: PACK_MAGIC


PackChunkLocation
-----------------------------------------------------

.. autoclass:: PackChunkLocation
    :members: pack_id,offset,stored_size,logical_size


PackWriteResult
-----------------------------------------------------

.. autoclass:: PackWriteResult
    :members: pack_id,pack_path,total_size,chunks


PackStore
-----------------------------------------------------

.. autoclass:: PackStore
    :members: __init__,pack_path,write_pack,read_chunk,read_range


