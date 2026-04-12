import io
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete
from hubvault.errors import EntryNotFoundError
from hubvault.optional import MissingOptionalDependencyError
from hubvault.remote import HubVaultRemoteAPI, HubVaultRemoteApi
from hubvault.remote.cache import build_snapshot_target, get_remote_cache_layout
from hubvault.remote.errors import HubVaultRemoteAuthError
from test.support import (
    TEST_DEFAULT_BRANCH,
    create_phase45_app,
    patch_remote_test_client,
    seed_phase45_repo,
    seed_phase78_repo,
)


@pytest.mark.unittest
class TestRemoteApi:
    def test_aliases_and_lazy_client_construction_are_available(self):
        api = HubVaultRemoteApi("https://example.com", token="secret")

        assert HubVaultRemoteAPI is HubVaultRemoteApi
        assert api.endpoint == "https://example.com"
        assert api.token == "secret"

    def test_missing_remote_extra_is_deferred_to_build_client(self, monkeypatch):
        api = HubVaultRemoteApi("https://example.com", token="secret")

        def _raise_missing(*args, **kwargs):
            raise MissingOptionalDependencyError(extra="remote", feature="test remote client", missing_name="httpx")

        monkeypatch.setattr("hubvault.remote.client.import_optional_dependency", _raise_missing)

        with pytest.raises(MissingOptionalDependencyError, match="hubvault\\[remote\\]"):
            api.build_client()

    def test_remote_readonly_methods_match_local_api_models(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="ro-token", revision=TEST_DEFAULT_BRANCH)

        assert remote_api.repo_info() == seeded["api"].repo_info()
        assert remote_api.get_paths_info(["artifacts", "artifacts/model.bin"]) == seeded["api"].get_paths_info(
            ["artifacts", "artifacts/model.bin"]
        )
        assert remote_api.list_repo_tree() == seeded["api"].list_repo_tree()
        assert remote_api.list_repo_tree("artifacts") == seeded["api"].list_repo_tree("artifacts")
        assert remote_api.list_repo_files() == seeded["api"].list_repo_files()
        assert remote_api.list_repo_commits(formatted=True) == seeded["api"].list_repo_commits(formatted=True)
        assert remote_api.get_commit_detail(seeded["head_commit"].oid, formatted=True) == seeded["api"].get_commit_detail(
            seeded["head_commit"].oid,
            formatted=True,
        )
        assert remote_api.list_repo_refs(include_pull_requests=True) == seeded["api"].list_repo_refs(
            include_pull_requests=True
        )
        assert remote_api.list_repo_reflog("release/v1", limit=2) == seeded["api"].list_repo_reflog(
            "release/v1", limit=2
        )

    def test_remote_reads_downloads_and_snapshots_round_trip(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        cache_dir = tmp_path / "remote-cache"
        export_dir = tmp_path / "export"
        remote_api = HubVaultRemoteApi(
            "http://testserver",
            token="ro-token",
            revision=TEST_DEFAULT_BRANCH,
            cache_dir=cache_dir,
        )

        assert remote_api.read_bytes("artifacts/model.bin") == seeded["model_bytes"]
        assert remote_api.read_range("artifacts/model.bin", start=2, length=6) == seeded["api"].read_range(
            "artifacts/model.bin",
            start=2,
            length=6,
        )

        cached_download = Path(remote_api.hf_hub_download("artifacts/model.bin"))
        repeated_download = Path(remote_api.hf_hub_download("artifacts/model.bin"))
        explicit_download = Path(remote_api.hf_hub_download("artifacts/model.bin", local_dir=export_dir))
        snapshot_dir = Path(
            remote_api.snapshot_download(
                allow_patterns=["artifacts/*", "docs/"],
                ignore_patterns=["*.tmp"],
            )
        )
        repeated_snapshot = Path(
            remote_api.snapshot_download(
                allow_patterns=["artifacts/*", "docs/"],
                ignore_patterns=["*.tmp"],
            )
        )

        assert cached_download.read_bytes() == seeded["model_bytes"]
        assert repeated_download == cached_download
        assert explicit_download == export_dir / "artifacts" / "model.bin"
        assert explicit_download.read_bytes() == seeded["model_bytes"]
        assert (snapshot_dir / "artifacts" / "model.bin").read_bytes() == seeded["model_bytes"]
        assert (snapshot_dir / "docs" / "guide.md").read_bytes() == seeded["guide_bytes"]
        assert not (snapshot_dir / "artifacts" / "weights.tmp").exists()
        assert repeated_snapshot == snapshot_dir

        with remote_api.open_file("artifacts/model.bin") as fileobj:
            assert fileobj.read() == seeded["model_bytes"]

    def test_remote_auth_and_missing_entry_errors_are_mapped(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seed_phase45_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)

        bad_token_api = HubVaultRemoteApi("http://testserver", token="bad", revision=TEST_DEFAULT_BRANCH)
        missing_entry_api = HubVaultRemoteApi("http://testserver", token="ro-token", revision=TEST_DEFAULT_BRANCH)

        with pytest.raises(HubVaultRemoteAuthError, match="Invalid authentication token"):
            bad_token_api.repo_info()

        with pytest.raises(EntryNotFoundError, match="missing.txt"):
            missing_entry_api.read_bytes("missing.txt")

        with pytest.raises(EntryNotFoundError, match="missing.txt"):
            missing_entry_api.hf_hub_download("missing.txt")

    def test_remote_snapshot_download_supports_string_patterns_and_partial_cache_reuse(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase45_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        cache_dir = tmp_path / "remote-cache"
        remote_api = HubVaultRemoteApi(
            "http://testserver",
            token="ro-token",
            revision=TEST_DEFAULT_BRANCH,
            cache_dir=cache_dir,
        )

        filtered_dir = Path(remote_api.snapshot_download(allow_patterns="docs/*"))
        assert (filtered_dir / "docs" / "guide.md").read_bytes() == seeded["guide_bytes"]

        layout = get_remote_cache_layout(cache_dir)
        partial_target = build_snapshot_target(
            layout,
            base_url="http://testserver",
            snapshot_id=seeded["head_commit"].oid,
        )
        (partial_target / "artifacts").mkdir(parents=True, exist_ok=True)
        (partial_target / "artifacts" / "model.bin").write_bytes(seeded["model_bytes"])

        rebuilt_dir = Path(remote_api.snapshot_download())

        assert rebuilt_dir == partial_target
        assert (rebuilt_dir / "artifacts" / "model.bin").read_bytes() == seeded["model_bytes"]
        assert (rebuilt_dir / "docs" / "guide.md").read_bytes() == seeded["guide_bytes"]

    def test_remote_write_methods_support_add_sources_and_ref_updates(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)
        local_file = tmp_path / "path-upload.txt"
        local_file.write_bytes(b"path upload\n")
        fileobj = io.BytesIO(b"fileobj upload\n")
        fileobj.seek(4)
        file_operation = CommitOperationAdd("docs/from-fileobj.txt", fileobj)

        commit = remote_api.create_commit(
            operations=[
                CommitOperationAdd("docs/from-bytes.txt", b"bytes upload\n"),
                CommitOperationAdd("docs/from-path.txt", local_file),
                file_operation,
            ],
            commit_message="add remote sources",
        )
        remote_api.create_branch(branch="hotfix")
        remote_api.create_tag(tag="remote-v1")
        remote_api.delete_tag(tag="remote-v1")
        remote_api.delete_branch(branch="hotfix")

        assert commit.commit_message == "add remote sources"
        assert fileobj.tell() == 0
        assert seeded["api"].read_bytes("docs/from-bytes.txt") == b"bytes upload\n"
        assert seeded["api"].read_bytes("docs/from-path.txt") == b"path upload\n"
        assert seeded["api"].read_bytes("docs/from-fileobj.txt") == b"fileobj upload\n"

    def test_remote_upload_progress_callback_tracks_streamed_bytes(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)

        progress_updates = []
        payload = b"progress upload body\n"
        commit = remote_api.upload_file(
            path_or_fileobj=payload,
            path_in_repo="docs/progress.txt",
            progress_callback=lambda sent, total: progress_updates.append((sent, total)),
        )

        assert commit.commit_message == "Upload docs/progress.txt with hubvault"
        assert seeded["api"].read_bytes("docs/progress.txt") == payload
        assert progress_updates[0] == (0, len(payload))
        assert progress_updates[-1] == (len(payload), len(payload))
        assert all(sent <= total for sent, total in progress_updates)

    def test_remote_write_methods_support_copy_delete_reset_and_folder_delete(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)

        copy_delete_commit = remote_api.create_commit(
            operations=[
                CommitOperationCopy(
                    src_path_in_repo="docs/source.txt",
                    path_in_repo="docs/copied.txt",
                    src_revision=TEST_DEFAULT_BRANCH,
                ),
                CommitOperationDelete("README.md", is_folder=False),
            ],
            commit_message="copy and delete remotely",
        )

        assert copy_delete_commit.commit_message == "copy and delete remotely"
        assert seeded["api"].read_bytes("docs/copied.txt") == seeded["shared_text"]
        assert "README.md" not in seeded["api"].list_repo_files()

        reset_commit = remote_api.reset_ref(TEST_DEFAULT_BRANCH, to_revision=seeded["seed_commit"].oid)
        assert reset_commit.oid == seeded["seed_commit"].oid
        assert seeded["api"].repo_info().head == seeded["seed_commit"].oid

        folder_delete_commit = remote_api.delete_folder("docs", revision=TEST_DEFAULT_BRANCH)
        assert folder_delete_commit.oid == seeded["api"].repo_info().head
        assert all(not path.startswith("docs/") for path in seeded["api"].list_repo_files())

    def test_remote_create_commit_rejects_unsupported_operation_objects(self):
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)

        with pytest.raises(TypeError, match="Unsupported commit operation"):
            remote_api.create_commit(
                operations=[object()],
                commit_message="bad operation",
            )

    def test_remote_upload_and_delete_folder_and_large_file_round_trip(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)
        source_dir = tmp_path / "upload-dir"
        source_dir.mkdir()
        (source_dir / "copy-source.txt").write_bytes(seeded["shared_text"])
        nested_dir = source_dir / "nested"
        nested_dir.mkdir()
        (nested_dir / "new.txt").write_bytes(b"nested upload\n")

        upload_commit = remote_api.upload_folder(
            folder_path=source_dir,
            path_in_repo="bundle",
            delete_patterns=["obsolete/*"],
        )
        delete_commit = remote_api.delete_file("bundle/copy-source.txt")
        large_commit = remote_api.upload_file(
            path_or_fileobj=seeded["large_update"],
            path_in_repo="artifacts/large.bin",
        )

        assert upload_commit.commit_message == "Upload folder using hubvault"
        assert delete_commit.commit_message == "Delete bundle/copy-source.txt with hubvault"
        assert large_commit.commit_message == "Upload artifacts/large.bin with hubvault"
        assert seeded["api"].read_bytes("bundle/nested/new.txt") == b"nested upload\n"
        assert "bundle/copy-source.txt" not in seeded["api"].list_repo_files()
        assert seeded["api"].read_bytes("artifacts/large.bin") == seeded["large_update"]

    def test_remote_upload_folder_supports_delete_patterns_and_large_folder_helper(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        seeded["api"].create_commit(
            operations=[
                CommitOperationAdd("bundle/.gitattributes", b"filter=lfs diff=lfs merge=lfs -text\n"),
                CommitOperationAdd("bundle/keep.txt", b"old keep\n"),
                CommitOperationAdd("bundle/remove.txt", b"old remove\n"),
            ],
            commit_message="seed bundle",
        )
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)
        source_dir = tmp_path / "sync-dir"
        source_dir.mkdir()
        (source_dir / "keep.txt").write_bytes(b"new keep\n")
        (source_dir / "drop.log").write_bytes(b"drop me\n")
        (source_dir / "skip.bin").write_bytes(b"skip\n")
        nested_dir = source_dir / "nested"
        nested_dir.mkdir()
        (nested_dir / "nested.txt").write_bytes(b"nested keep\n")
        large_dir = tmp_path / "large-dir"
        large_dir.mkdir()
        (large_dir / "huge.bin").write_bytes(seeded["large_update"])

        upload_commit = remote_api.upload_folder(
            folder_path=source_dir,
            path_in_repo="bundle",
            allow_patterns=["*.txt", "nested/", "skip.bin"],
            ignore_patterns="skip.bin",
            delete_patterns="*",
        )
        large_commit = remote_api.upload_large_folder(folder_path=large_dir, allow_patterns="*.bin")

        assert upload_commit.commit_message == "Upload folder using hubvault"
        assert seeded["api"].read_bytes("bundle/keep.txt") == b"new keep\n"
        assert seeded["api"].read_bytes("bundle/nested/nested.txt") == b"nested keep\n"
        assert "bundle/drop.log" not in seeded["api"].list_repo_files()
        assert "bundle/remove.txt" not in seeded["api"].list_repo_files()
        assert "bundle/skip.bin" not in seeded["api"].list_repo_files()
        assert seeded["api"].read_bytes("bundle/.gitattributes") == b"filter=lfs diff=lfs merge=lfs -text\n"
        assert large_commit.commit_message == "Upload large folder using hubvault"
        assert seeded["api"].read_bytes("huge.bin") == seeded["large_update"]

    def test_remote_upload_folder_rejects_non_directory_inputs(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seed_phase78_repo(repo_dir)
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)
        missing_dir = tmp_path / "missing"

        with pytest.raises(ValueError, match="folder_path must point to an existing local directory"):
            remote_api.upload_folder(folder_path=missing_dir)

    def test_remote_merge_conflict_and_maintenance_reports_round_trip(self, monkeypatch, tmp_path):
        repo_dir = tmp_path / "repo"
        seeded = seed_phase78_repo(repo_dir)
        seeded["api"].create_commit(
            operations=[CommitOperationAdd("docs/source.txt", b"main-side\n")],
            commit_message="change main source",
        )
        app = create_phase45_app(repo_dir)
        patch_remote_test_client(monkeypatch, app)
        remote_api = HubVaultRemoteApi("http://testserver", token="rw-token", revision=TEST_DEFAULT_BRANCH)

        merge_result = remote_api.merge("feature")
        quick_report = remote_api.quick_verify()
        full_report = remote_api.full_verify()
        overview = remote_api.get_storage_overview()
        gc_report = remote_api.gc(dry_run=True, prune_cache=True)
        squash_report = remote_api.squash_history(TEST_DEFAULT_BRANCH, run_gc=False)

        assert merge_result.status == "conflict"
        assert merge_result.conflicts
        assert quick_report.ok is True
        assert full_report.ok is True
        assert overview.total_size > 0
        assert overview.reachable_size > 0
        assert gc_report.dry_run is True
        assert squash_report.ref_name == "refs/heads/%s" % (TEST_DEFAULT_BRANCH,)
