import hubvault.storage as storage_module
import pytest


@pytest.mark.unittest
class TestStoragePackageInit:
    def test_storage_package_reexports_phase3_helpers(self):
        assert storage_module.ChunkStore is not None
        assert storage_module.PackStore is not None
        assert storage_module.IndexStore is not None
        assert storage_module.DEFAULT_CHUNK_SIZE > 0
        assert storage_module.PACK_MAGIC.startswith(b"hubvault-pack/")
        assert storage_module.INDEX_LEVELS == ("L0", "L1", "L2")
        assert storage_module.__all__ == [
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
