from pathlib import Path

import pytest

from hubvault.errors import EntryNotFoundError
from hubvault.optional import MissingOptionalDependencyError
from hubvault.remote import HubVaultRemoteAPI, HubVaultRemoteApi
from hubvault.remote.errors import HubVaultRemoteAuthError
from test.support import TEST_DEFAULT_BRANCH, create_phase45_app, patch_remote_test_client, seed_phase45_repo


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
