from pathlib import Path

import pytest

from hubvault import IntegrityError
from hubvault.storage.pack import PACK_MAGIC, PackStore


@pytest.mark.unittest
class TestPackStore:
    def test_write_pack_and_read_chunk_and_range(self, tmp_path):
        store = PackStore(tmp_path / "packs")

        result = store.write_pack("demo", [b"abc", b"defg"])

        assert Path(result.pack_path).name == "demo.pack"
        assert result.total_size == len(PACK_MAGIC) + 7
        assert [chunk.stored_size for chunk in result.chunks] == [3, 4]
        assert store.read_chunk(result.chunks[0]) == b"abc"
        assert store.read_range("demo", result.chunks[1].offset + 1, 2) == b"ef"

    def test_pack_store_detects_duplicate_ids_and_truncation(self, tmp_path):
        store = PackStore(tmp_path / "packs")
        result = store.write_pack("demo", [b"abc", b"defg"])

        with pytest.raises(IntegrityError):
            store.write_pack("demo", [b"x"])

        pack_path = store.pack_path("demo")
        pack_path.write_bytes(pack_path.read_bytes()[:-1])

        with pytest.raises(IntegrityError):
            store.read_chunk(result.chunks[1])

    def test_pack_store_rejects_invalid_ranges(self, tmp_path):
        store = PackStore(tmp_path / "packs")
        _ = store.write_pack("demo", [b"abc"])

        with pytest.raises(ValueError):
            store.read_range("demo", -1, 1)

        with pytest.raises(ValueError):
            store.read_range("demo", len(PACK_MAGIC), -1)

        with pytest.raises(IntegrityError):
            store.read_range("demo", 0, 1)

        with pytest.raises(IntegrityError):
            store.read_range("missing", len(PACK_MAGIC), 1)

    def test_pack_store_supports_empty_pack_and_detects_invalid_header(self, tmp_path):
        store = PackStore(tmp_path / "packs")

        empty_result = store.write_pack("empty", [])
        assert empty_result.total_size == len(PACK_MAGIC)
        assert empty_result.chunks == ()
        assert store.read_range("empty", len(PACK_MAGIC), 0) == b""

        _ = store.write_pack("demo", [b"abc"])
        pack_path = store.pack_path("demo")
        pack_path.write_bytes(b"broken-pack\nabc")

        with pytest.raises(IntegrityError):
            store.read_range("demo", len(PACK_MAGIC), 1)
