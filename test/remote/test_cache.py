from pathlib import Path

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

