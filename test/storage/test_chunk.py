from hashlib import sha256

import pytest

from hubvault.storage.chunk import ChunkStore, canonical_lfs_pointer, git_blob_oid


@pytest.mark.unittest
class TestChunkStore:
    def test_plan_bytes_builds_lfs_metadata_and_content_defined_chunks(self):
        payload = (
            (b"phase10-fastcdc-block-0000\n" * 64)
            + (b"phase10-fastcdc-block-1111\n" * 64)
            + (b"phase10-fastcdc-block-2222\n" * 64)
            + (b"phase10-fastcdc-block-3333\n" * 64)
        )
        store = ChunkStore(chunk_size=1024, min_chunk_size=256, max_chunk_size=4096)

        plan = store.plan_bytes(payload)
        expected_sha256 = sha256(payload).hexdigest()
        pointer = canonical_lfs_pointer(expected_sha256, len(payload))

        assert plan.logical_size == len(payload)
        assert plan.sha256 == expected_sha256
        assert plan.oid == git_blob_oid(pointer)
        assert plan.etag == expected_sha256
        assert plan.pointer_size == len(pointer)
        assert len(plan.chunks) >= 2
        assert [part.data for part in plan.parts] == [
            payload[chunk.logical_offset:chunk.logical_offset + chunk.logical_size]
            for chunk in plan.chunks
        ]
        assert b"".join(part.data for part in plan.parts) == payload
        assert plan.chunks[0].logical_offset == 0
        assert plan.chunks[-1].logical_offset + plan.chunks[-1].logical_size == len(payload)
        for previous, current in zip(plan.chunks, plan.chunks[1:]):
            assert previous.logical_offset + previous.logical_size == current.logical_offset
        assert any(chunk.logical_size != store.chunk_size for chunk in plan.chunks)
        assert [chunk.chunk_id for chunk in plan.chunks] == [chunk.checksum for chunk in plan.chunks]
        assert all(chunk.chunk_id.startswith("sha256:") for chunk in plan.chunks)

    def test_plan_bytes_handles_empty_payload(self):
        plan = ChunkStore(chunk_size=256, min_chunk_size=64, max_chunk_size=1024).plan_bytes(b"")
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
            ChunkStore(chunk_size=128)

        with pytest.raises(ValueError):
            ChunkStore(chunk_size=256, min_chunk_size=32)

        with pytest.raises(ValueError):
            ChunkStore(chunk_size=256, max_chunk_size=512)

        with pytest.raises(ValueError):
            ChunkStore().plan_bytes("not-bytes")
