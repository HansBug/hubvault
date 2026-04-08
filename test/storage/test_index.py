import os
import stat

import pytest

from hubvault import IntegrityError
import hubvault.storage.index as index_module
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
    def test_index_entry_and_manifest_validation_errors(self):
        with pytest.raises(IntegrityError):
            IndexEntry.from_dict({"chunk_id": "sha256:a"})

        manifest = IndexManifest.empty().add_segment("L0", "seg-a.idx").add_segment("L0", "seg-a.idx")
        assert manifest.levels["L0"] == ("seg-a.idx",)
        assert manifest.to_dict()["levels"]["L0"] == ["seg-a.idx"]

        with pytest.raises(ValueError):
            IndexManifest.empty().add_segment("LX", "seg-a.idx")

        with pytest.raises(IntegrityError):
            IndexManifest.from_dict({})

        with pytest.raises(IntegrityError):
            IndexManifest.from_dict({"levels": []})

        with pytest.raises(IntegrityError):
            IndexManifest.from_dict({"levels": {"L0": "not-a-list"}})

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

        assert store.read_manifest().levels["L0"] == ()
        assert store.lookup("sha256:missing") is None

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

    def test_index_store_detects_malformed_manifest_and_segment_shapes(self, tmp_path):
        manifest_store = IndexStore(tmp_path / "bad-manifest")
        manifest_store.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_store.manifest_path.write_text("{bad json", encoding="utf-8")
        with pytest.raises(IntegrityError):
            manifest_store.read_manifest()

        directory_manifest_store = IndexStore(tmp_path / "dir-manifest")
        directory_manifest_store.manifest_path.mkdir(parents=True)
        with pytest.raises(IntegrityError):
            directory_manifest_store.read_manifest()

        missing_segment_store = IndexStore(tmp_path / "missing-segment")
        with pytest.raises(IntegrityError):
            missing_segment_store.load_segment("L0", "missing.idx")

        blank_segment_store = IndexStore(tmp_path / "blank-segment")
        entry = _entry("sha256:blank", "pack-blank", 32)
        path = blank_segment_store.segment_path("L0", "blank.idx")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n%s\n\n" % entry.to_dict(), encoding="utf-8")
        with pytest.raises(IntegrityError):
            blank_segment_store.load_segment("L0", "blank.idx")

        valid_blank_store = IndexStore(tmp_path / "valid-blank-segment")
        valid_blank_path = valid_blank_store.segment_path("L0", "valid.idx")
        valid_blank_path.parent.mkdir(parents=True, exist_ok=True)
        valid_blank_path.write_text(
            "\n"
            '{"checksum":"sha256:blank","chunk_id":"sha256:blank","compression":"none",'
            '"logical_size":4,"offset":32,"pack_id":"pack-blank","stored_size":4}'
            "\n\n",
            encoding="utf-8",
        )
        assert valid_blank_store.load_segment("L0", "valid.idx") == (entry,)

        non_object_store = IndexStore(tmp_path / "non-object-segment")
        non_object_path = non_object_store.segment_path("L0", "non-object.idx")
        non_object_path.parent.mkdir(parents=True, exist_ok=True)
        non_object_path.write_text("[]\n", encoding="utf-8")
        with pytest.raises(IntegrityError):
            non_object_store.load_segment("L0", "non-object.idx")

        directory_segment_store = IndexStore(tmp_path / "dir-segment")
        directory_segment_store.segment_path("L0", "segment-dir.idx").mkdir(parents=True)
        with pytest.raises(IntegrityError):
            directory_segment_store.load_segment("L0", "segment-dir.idx")

    def test_index_store_tolerates_directory_fsync_failures(self, tmp_path, monkeypatch):
        entry = _entry("sha256:dir-fsync", "pack-dir", 16)

        open_failure_store = IndexStore(tmp_path / "open-failure-index")
        original_open = index_module.os.open
        monkeypatch.setattr(
            index_module.os,
            "open",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("directory open blocked")),
        )
        open_failure_store.write_segment("L0", "seg-open.idx", [entry])
        assert open_failure_store.load_segment("L0", "seg-open.idx") == (entry,)

        monkeypatch.setattr(index_module.os, "open", original_open)
        original_fsync = index_module.os.fsync

        def selective_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory fsync blocked")
            return original_fsync(fd)

        monkeypatch.setattr(index_module.os, "fsync", selective_fsync)
        fsync_failure_store = IndexStore(tmp_path / "fsync-failure-index")
        fsync_failure_store.write_manifest(IndexManifest.empty().add_segment("L0", "seg-fsync.idx"))
        assert fsync_failure_store.read_manifest().levels["L0"] == ("seg-fsync.idx",)
