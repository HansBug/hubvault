from pathlib import Path
from types import SimpleNamespace

import pytest

from hubvault.remote.cache import (
    build_download_target,
    build_snapshot_target,
    get_remote_cache_layout,
    snapshot_is_complete,
)


@pytest.mark.unittest
class TestRemoteCache:
    def test_cache_layout_honors_environment_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HUBVAULT_REMOTE_CACHE_DIR", str(tmp_path / "cache-root"))

        layout = get_remote_cache_layout()

        assert layout.download_root == str(tmp_path / "cache-root" / "downloads")
        assert layout.snapshot_root == str(tmp_path / "cache-root" / "snapshots")

    def test_cache_layout_uses_xdg_cache_home_when_available(self, monkeypatch, tmp_path):
        monkeypatch.delenv("HUBVAULT_REMOTE_CACHE_DIR", raising=False)
        monkeypatch.setattr(
            "hubvault.remote.cache.os",
            SimpleNamespace(
                name="posix",
                environ={"XDG_CACHE_HOME": str(tmp_path / "xdg-cache")},
            ),
        )

        layout = get_remote_cache_layout()

        assert layout.download_root == str(tmp_path / "xdg-cache" / "hubvault" / "remote" / "downloads")
        assert layout.snapshot_root == str(tmp_path / "xdg-cache" / "hubvault" / "remote" / "snapshots")

    def test_cache_layout_uses_home_fallbacks_for_posix_and_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr("hubvault.remote.cache.Path.home", staticmethod(lambda: tmp_path / "home"))

        monkeypatch.setattr(
            "hubvault.remote.cache.os",
            SimpleNamespace(
                name="posix",
                environ={},
            ),
        )
        posix_layout = get_remote_cache_layout()

        monkeypatch.setattr(
            "hubvault.remote.cache.os",
            SimpleNamespace(
                name="nt",
                environ={},
            ),
        )
        windows_layout = get_remote_cache_layout()

        assert posix_layout.download_root == str(tmp_path / "home" / ".cache" / "hubvault" / "remote" / "downloads")
        assert windows_layout.download_root == str(
            tmp_path / "home" / "AppData" / "Local" / "hubvault" / "remote" / "downloads"
        )

    def test_cache_layout_uses_localappdata_on_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "hubvault.remote.cache.os",
            SimpleNamespace(
                name="nt",
                environ={"LOCALAPPDATA": str(tmp_path / "LocalAppData")},
            ),
        )

        layout = get_remote_cache_layout()

        assert layout.download_root == str(tmp_path / "LocalAppData" / "hubvault" / "remote" / "downloads")

    def test_download_target_preserves_repo_relative_suffixes(self, tmp_path):
        layout = get_remote_cache_layout(tmp_path / "cache-root")

        cached_target = build_download_target(
            layout,
            base_url="https://example.com/api",
            path_in_repo="nested/path/model.bin",
            etag="etag-value",
            revision="main",
        )
        explicit_target = build_download_target(
            layout,
            base_url="https://example.com/api",
            path_in_repo="nested/path/model.bin",
            etag=None,
            revision="main",
            local_dir=tmp_path / "export",
        )

        assert cached_target.parts[-3:] == ("nested", "path", "model.bin")
        assert explicit_target == tmp_path / "export" / "nested" / "path" / "model.bin"

    def test_download_target_uses_revision_hash_when_etag_is_missing(self, tmp_path):
        layout = get_remote_cache_layout(tmp_path / "cache-root")

        target = build_download_target(
            layout,
            base_url="https://example.com/api",
            path_in_repo="nested/path/model.bin",
            etag=None,
            revision="release/v1",
        )

        assert target.parts[-3:] == ("nested", "path", "model.bin")
        assert len(target.parts[-4]) == 16

    def test_snapshot_target_and_completeness_checks(self, tmp_path):
        layout = get_remote_cache_layout(tmp_path / "cache-root")
        target_dir = build_snapshot_target(
            layout,
            base_url="https://example.com/api",
            snapshot_id="commit-1",
        )

        (target_dir / "docs").mkdir(parents=True, exist_ok=True)
        (target_dir / "docs" / "guide.md").write_text("guide")

        assert build_snapshot_target(
            layout,
            base_url="https://example.com/api",
            snapshot_id="commit-1",
            local_dir=tmp_path / "explicit-snapshot",
        ) == tmp_path / "explicit-snapshot"
        assert snapshot_is_complete(target_dir, ["docs/guide.md"]) is True
        assert snapshot_is_complete(target_dir, ["docs/guide.md", "artifacts/model.bin"]) is False
        assert snapshot_is_complete(target_dir, []) is True
