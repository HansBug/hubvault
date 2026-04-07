import shutil
from pathlib import Path

import pytest

from hubvault import (
    CommitOperationAdd,
    CommitOperationCopy,
    CommitOperationDelete,
    ConflictError,
    HubVaultApi,
    PathNotFoundError,
    RevisionNotFoundError,
)


@pytest.mark.unittest
class TestRepoSemantics:
    def test_download_views_are_detached_and_rebuildable(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd.from_bytes("models/core/model.safetensors", b"payload-v1")],
            commit_message="seed",
        )

        view_path = Path(api.hf_hub_download("demo", "models/core/model.safetensors"))
        assert view_path.as_posix().endswith("models/core/model.safetensors")
        assert view_path.read_bytes() == b"payload-v1"

        view_path.write_bytes(b"tampered")
        report = api.quick_verify()
        assert report.ok is True
        assert any("stale file view" in warning for warning in report.warnings)
        assert api.read_bytes("models/core/model.safetensors") == b"payload-v1"

        rebuilt_path = Path(api.hf_hub_download("demo", "models/core/model.safetensors"))
        assert rebuilt_path == view_path
        assert rebuilt_path.read_bytes() == b"payload-v1"

        rebuilt_path.unlink()
        restored_path = Path(api.hf_hub_download("demo", "models/core/model.safetensors"))
        assert restored_path == view_path
        assert restored_path.read_bytes() == b"payload-v1"

        external_path = Path(
            api.hf_hub_download(
                "demo",
                "models/core/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        external_path.write_bytes(b"tampered-external")
        refreshed_external_path = Path(
            api.hf_hub_download(
                "demo",
                "models/core/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        assert refreshed_external_path == external_path
        assert refreshed_external_path.read_bytes() == b"payload-v1"

    def test_copy_delete_reset_and_repo_move_keep_working(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd.from_bytes("src/a.txt", b"A"),
                CommitOperationAdd.from_bytes("src/sub/b.txt", b"B"),
            ],
            commit_message="seed repo",
        )
        second_commit = api.create_commit(
            operations=[
                CommitOperationCopy("src", "mirror"),
                CommitOperationDelete("src/sub"),
            ],
            parent_commit=first_commit.commit_id,
            commit_message="copy and prune",
        )

        assert second_commit.parents == [first_commit.commit_id]
        assert api.list_repo_files() == [
            "mirror/a.txt",
            "mirror/sub/b.txt",
            "src/a.txt",
        ]

        reset = api.reset_ref("main", first_commit.commit_id)
        assert reset.commit_id == first_commit.commit_id
        assert api.list_repo_files() == ["src/a.txt", "src/sub/b.txt"]
        assert api.quick_verify().ok is True

        moved_repo_dir = tmp_path / "moved-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        moved_api = HubVaultApi(moved_repo_dir)

        assert moved_api.repo_info().head == first_commit.commit_id
        assert moved_api.read_bytes("src/sub/b.txt") == b"B"
        report = moved_api.quick_verify()
        assert report.ok is True
        assert "refs/heads/main" in report.checked_refs

    def test_repo_conflict_and_missing_path_cases(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo()

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[
                    CommitOperationAdd.from_bytes("dup.txt", b"a"),
                    CommitOperationAdd.from_bytes("dup.txt/child.txt", b"b"),
                ],
                commit_message="invalid hierarchy",
            )

        with pytest.raises(ConflictError):
            api.create_commit(
                operations=[
                    CommitOperationAdd.from_bytes("Case.txt", b"a"),
                    CommitOperationAdd.from_bytes("case.txt", b"b"),
                ],
                commit_message="case clash",
            )

        baseline = api.create_commit(
            operations=[CommitOperationAdd.from_bytes("data/file.txt", b"v1")],
            commit_message="seed",
        )

        with pytest.raises(PathNotFoundError):
            api.create_commit(
                operations=[CommitOperationDelete("missing.txt")],
                parent_commit=baseline.commit_id,
                commit_message="missing delete",
            )

        with pytest.raises(PathNotFoundError):
            api.create_commit(
                operations=[CommitOperationCopy("missing.txt", "copied.txt")],
                parent_commit=baseline.commit_id,
                commit_message="missing copy",
            )

        with pytest.raises(RevisionNotFoundError):
            api.reset_ref("main", "missing")
