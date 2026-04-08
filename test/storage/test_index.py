import pytest

from hubvault import IntegrityError
from hubvault.storage.index import IndexEntry, IndexManifest, IndexStore


def _entry(chunk_id, pack_id, offset):
    return IndexEntry(
        chunk_id=chunk_id,
        pack_id=pack_id,
        offset=offset,
        stored_size=4,
        logical_size=4,
        compression="none",
        checksum=chunk_id,
    )


@pytest.mark.unittest
class TestIndexStore:
    def test_manifest_and_segment_round_trip(self, tmp_path):
        store = IndexStore(tmp_path / "index")
        entry = _entry("sha256:a", "pack-a", 16)

        path = store.write_segment("L0", "seg-a.idx", [entry])
        store.write_manifest(IndexManifest.empty().add_segment("L0", "seg-a.idx"))

        assert path.name == "seg-a.idx"
        assert store.read_manifest().levels["L0"] == ("seg-a.idx",)
        assert store.load_segment("L0", "seg-a.idx") == (entry,)
        assert store.lookup("sha256:a") == entry

    def test_lookup_prefers_newest_visible_segment(self, tmp_path):
        store = IndexStore(tmp_path / "index")
        older = _entry("sha256:dup", "pack-old", 16)
        newer = _entry("sha256:dup", "pack-new", 32)

        store.write_segment("L0", "seg-old.idx", [older])
        store.write_segment("L0", "seg-new.idx", [newer])
        store.write_manifest(
            IndexManifest.empty()
            .add_segment("L0", "seg-old.idx")
            .add_segment("L0", "seg-new.idx")
        )

        assert store.lookup("sha256:dup") == newer

    def test_index_store_detects_invalid_inputs(self, tmp_path):
        store = IndexStore(tmp_path / "index")

        with pytest.raises(ValueError):
            store.segment_path("LX", "seg.idx")

        store.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        store.manifest_path.write_text("[]", encoding="utf-8")
        with pytest.raises(IntegrityError):
            store.read_manifest()

        broken_store = IndexStore(tmp_path / "broken-index")
        broken_path = broken_store.segment_path("L0", "broken.idx")
        broken_path.parent.mkdir(parents=True, exist_ok=True)
        broken_path.write_text("{broken}\n", encoding="utf-8")
        with pytest.raises(IntegrityError):
            broken_store.load_segment("L0", "broken.idx")

        good_entry = _entry("sha256:b", "pack-b", 24)
        store = IndexStore(tmp_path / "dup-index")
        _ = store.write_segment("L0", "seg.idx", [good_entry])
        with pytest.raises(IntegrityError):
            store.write_segment("L0", "seg.idx", [good_entry])
