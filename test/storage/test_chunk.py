from hashlib import sha256

import pytest

from hubvault.storage.chunk import ChunkStore, canonical_lfs_pointer, git_blob_oid


@pytest.mark.unittest
class TestChunkStore:
    def test_plan_bytes_builds_lfs_metadata_and_deterministic_chunks(self):
        payload = b"abcdefghijkl"
        store = ChunkStore(chunk_size=5)

        plan = store.plan_bytes(payload)
        expected_sha256 = sha256(payload).hexdigest()
        pointer = canonical_lfs_pointer(expected_sha256, len(payload))

        assert plan.logical_size == len(payload)
        assert plan.sha256 == expected_sha256
        assert plan.oid == git_blob_oid(pointer)
        assert plan.etag == expected_sha256
        assert plan.pointer_size == len(pointer)
        assert [chunk.logical_offset for chunk in plan.chunks] == [0, 5, 10]
        assert [chunk.logical_size for chunk in plan.chunks] == [5, 5, 2]
        assert [chunk.stored_size for chunk in plan.chunks] == [5, 5, 2]
        assert [part.data for part in plan.parts] == [b"abcde", b"fghij", b"kl"]
        assert [chunk.chunk_id for chunk in plan.chunks] == [chunk.checksum for chunk in plan.chunks]

    def test_plan_bytes_handles_empty_payload(self):
        plan = ChunkStore(chunk_size=4).plan_bytes(b"")
        expected_sha256 = sha256(b"").hexdigest()

        assert plan.logical_size == 0
        assert plan.sha256 == expected_sha256
        assert plan.etag == expected_sha256
        assert plan.chunks == ()
        assert plan.parts == ()
        assert plan.pointer_size == len(canonical_lfs_pointer(expected_sha256, 0))

    def test_chunk_store_rejects_invalid_inputs(self):
        with pytest.raises(ValueError):
            ChunkStore(chunk_size=0)

        with pytest.raises(ValueError):
            ChunkStore().plan_bytes("not-bytes")
