import os
import stat
from pathlib import Path

import pytest

from hubvault import IntegrityError
import hubvault.storage.pack as pack_module
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

    def test_pack_store_tolerates_directory_fsync_failures_and_short_reads(self, tmp_path, monkeypatch):
        open_failure_store = PackStore(tmp_path / "open-failure-packs")
        original_open = pack_module.os.open
        monkeypatch.setattr(
            pack_module.os,
            "open",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("directory open blocked")),
        )
        open_result = open_failure_store.write_pack("open-failure", [b"abc"])
        assert open_failure_store.read_chunk(open_result.chunks[0]) == b"abc"

        monkeypatch.setattr(pack_module.os, "open", original_open)
        original_fsync = pack_module.os.fsync

        def selective_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory fsync blocked")
            return original_fsync(fd)

        monkeypatch.setattr(pack_module.os, "fsync", selective_fsync)
        fsync_failure_store = PackStore(tmp_path / "fsync-failure-packs")
        fsync_result = fsync_failure_store.write_pack("fsync-failure", [b"abcdef"])
        assert fsync_failure_store.read_chunk(fsync_result.chunks[0]) == b"abcdef"

        monkeypatch.setattr(pack_module.os, "fsync", original_fsync)
        original_path_open = pack_module.Path.open
        short_read_pack_path = fsync_failure_store.pack_path("fsync-failure")

        class _ShortReadWrapper:
            def __init__(self, file_):
                self._file = file_
                self._payload_reads = 0

            def __enter__(self):
                self._file.__enter__()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return self._file.__exit__(exc_type, exc_val, exc_tb)

            def read(self, size=-1):
                data = self._file.read(size)
                if size > 0:
                    self._payload_reads += 1
                    if self._payload_reads >= 2 and len(data) == size and size > 0:
                        return data[:-1]
                return data

            def __getattr__(self, item):
                return getattr(self._file, item)

        def fake_open(path_obj, *args, **kwargs):
            file_ = original_path_open(path_obj, *args, **kwargs)
            mode = args[0] if args else kwargs.get("mode", "r")
            if path_obj == short_read_pack_path and "rb" in mode:
                return _ShortReadWrapper(file_)
            return file_

        monkeypatch.setattr(pack_module.Path, "open", fake_open)
        with pytest.raises(IntegrityError, match="pack truncated"):
            fsync_failure_store.read_range(
                "fsync-failure",
                fsync_result.chunks[0].offset,
                fsync_result.chunks[0].stored_size,
            )
