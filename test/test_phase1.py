"""
Phase 1 end-to-end workflow tests for :mod:`hubvault`.

This module simulates realistic local ML artifact repository usage through the
current public API surface. The covered workflow starts from repository
initialization, publishes multiple commits from different input forms, reads
historical revisions, exports detached file views, performs copy/delete based
changes, resets a branch head, and finally reopens the moved repository from a
new filesystem location.
"""

import io
import shutil
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete, HubVaultApi


@pytest.mark.unittest
class TestPhase1IntegratedLifecycle:
    """
    Exercise the current Phase 1 public workflow as a realistic user journey.

    The scenario in this class is intentionally integration-like while still
    staying inside the public package API. It verifies that a user can manage a
    self-contained local model repository end to end without depending on
    private helpers, mocks, or out-of-band mutation paths.
    """

    def test_phase1_model_artifact_workflow_from_repo_bootstrap_to_reopen(self, tmp_path):
        """
        Simulate a model-team artifact workflow from init to rollback and reopen.

        The simulated user story is:

        1. Initialize a portable local repository for model assets.
        2. Publish the first artifact set from bytes, a filesystem file, and a
           file-like object.
        3. Read repository metadata, tree listings, path metadata, binary file
           streams, and detached download views.
        4. Publish follow-up commits that copy released files, delete obsolete
           paths, and record a fresh manifest.
        5. Roll the branch back to a validated commit and reopen the moved repo
           at a different absolute path to prove portability.
        """

        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir)

        created = api.create_repo(metadata={"project": "vision-demo", "owner": "qa"})
        assert created.default_branch == "main"
        assert created.head is None
        assert created.refs == ["refs/heads/main"]

        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        config_source = staging_dir / "model.json"
        config_source.write_text('{"hidden_size":4096,"dtype":"float16"}\n', encoding="utf-8")
        tokenizer_stream = io.BytesIO(b'{"bos_token":"<s>","eos_token":"</s>"}\n')
        training_note = b"training-run-0001\n"
        weights_v1 = b"weights-v1"
        weights_v2 = b"weights-v2"
        manifest_v2 = b'{"current":"epoch-0002","stable":"v1"}\n'

        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd.from_file("configs/model.json", str(config_source)),
                CommitOperationAdd.from_fileobj("tokenizer/tokenizer.json", tokenizer_stream),
                CommitOperationAdd.from_bytes("runs/run-0001/notes.txt", training_note),
                CommitOperationAdd.from_bytes("checkpoints/epoch-0001/model.safetensors", weights_v1),
            ],
            commit_message="seed phase1 assets",
            metadata={"stage": "bootstrap"},
        )

        current_info = api.repo_info()
        assert current_info.head == first_commit.commit_id
        assert api.list_repo_files() == [
            "checkpoints/epoch-0001/model.safetensors",
            "configs/model.json",
            "runs/run-0001/notes.txt",
            "tokenizer/tokenizer.json",
        ]

        root_items = [item.path for item in api.list_repo_tree()]
        assert root_items == ["checkpoints", "configs", "runs", "tokenizer"]

        checkpoint_items = [item.path for item in api.list_repo_tree("checkpoints")]
        assert checkpoint_items == ["checkpoints/epoch-0001"]

        path_infos = api.get_paths_info(
            [
                "checkpoints",
                "checkpoints/epoch-0001/model.safetensors",
                "configs/model.json",
            ]
        )
        assert [item.path_type for item in path_infos] == ["directory", "file", "file"]
        assert path_infos[1].size == len(weights_v1)
        assert path_infos[1].oid == path_infos[1].blob_id
        assert len(path_infos[1].sha256) == 64

        assert api.read_bytes("runs/run-0001/notes.txt", revision=first_commit.commit_id) == training_note
        assert api.read_bytes("checkpoints/epoch-0001/model.safetensors") == weights_v1

        with api.open_file("configs/model.json") as fileobj:
            assert fileobj.read() == config_source.read_bytes()
            assert fileobj.writable() is False

        cached_download = Path(api.hf_hub_download("checkpoints/epoch-0001/model.safetensors"))
        assert cached_download.as_posix().endswith("checkpoints/epoch-0001/model.safetensors")
        assert cached_download.read_bytes() == weights_v1

        cached_download.write_bytes(b"tampered-cache-view")
        assert api.read_bytes("checkpoints/epoch-0001/model.safetensors") == weights_v1
        stale_report = api.quick_verify()
        assert stale_report.ok is True
        assert any("stale file view" in warning for warning in stale_report.warnings)

        rebuilt_cached_download = Path(api.hf_hub_download("checkpoints/epoch-0001/model.safetensors"))
        assert rebuilt_cached_download == cached_download
        assert rebuilt_cached_download.read_bytes() == weights_v1

        exported_download = Path(
            api.hf_hub_download(
                "checkpoints/epoch-0001/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        assert exported_download == tmp_path / "exports" / "checkpoints" / "epoch-0001" / "model.safetensors"
        assert exported_download.read_bytes() == weights_v1
        exported_download.write_bytes(b"tampered-export")
        refreshed_export = Path(
            api.hf_hub_download(
                "checkpoints/epoch-0001/model.safetensors",
                local_dir=tmp_path / "exports",
            )
        )
        assert refreshed_export == exported_download
        assert refreshed_export.read_bytes() == weights_v1

        second_commit = api.create_commit(
            operations=[
                CommitOperationCopy("configs", "releases/v1/configs"),
                CommitOperationCopy(
                    "checkpoints/epoch-0001/model.safetensors",
                    "releases/v1/model.safetensors",
                ),
                CommitOperationDelete("runs/run-0001"),
                CommitOperationAdd.from_bytes("checkpoints/epoch-0002/model.safetensors", weights_v2),
            ],
            parent_commit=first_commit.commit_id,
            commit_message="publish v1 and advance checkpoint",
            metadata={"stage": "publish"},
        )
        assert second_commit.parents == [first_commit.commit_id]

        third_commit = api.create_commit(
            operations=[CommitOperationAdd.from_bytes("manifests/latest.json", manifest_v2)],
            expected_head=second_commit.commit_id,
            commit_message="record latest manifest",
            metadata={"stage": "manifest"},
        )
        assert api.repo_info().head == third_commit.commit_id

        assert api.list_repo_files(revision=first_commit.commit_id) == [
            "checkpoints/epoch-0001/model.safetensors",
            "configs/model.json",
            "runs/run-0001/notes.txt",
            "tokenizer/tokenizer.json",
        ]
        assert api.list_repo_files() == [
            "checkpoints/epoch-0001/model.safetensors",
            "checkpoints/epoch-0002/model.safetensors",
            "configs/model.json",
            "manifests/latest.json",
            "releases/v1/configs/model.json",
            "releases/v1/model.safetensors",
            "tokenizer/tokenizer.json",
        ]

        release_items = [item.path for item in api.list_repo_tree("releases/v1")]
        assert release_items == ["releases/v1/configs", "releases/v1/model.safetensors"]
        release_infos = api.get_paths_info(["releases/v1", "releases/v1/model.safetensors"])
        assert [item.path_type for item in release_infos] == ["directory", "file"]
        assert api.read_bytes("releases/v1/model.safetensors", revision=third_commit.commit_id) == weights_v1
        assert api.read_bytes("checkpoints/epoch-0002/model.safetensors") == weights_v2

        reset_commit = api.reset_ref("main", second_commit.commit_id)
        assert reset_commit.commit_id == second_commit.commit_id
        assert api.repo_info().head == second_commit.commit_id
        assert api.list_repo_files() == [
            "checkpoints/epoch-0001/model.safetensors",
            "checkpoints/epoch-0002/model.safetensors",
            "configs/model.json",
            "releases/v1/configs/model.json",
            "releases/v1/model.safetensors",
            "tokenizer/tokenizer.json",
        ]

        final_report = api.quick_verify()
        assert final_report.ok is True
        assert final_report.errors == []
        assert "refs/heads/main" in final_report.checked_refs

        moved_repo_dir = tmp_path / "moved-portable-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        reopened_info = reopened_api.repo_info()
        assert reopened_info.head == second_commit.commit_id
        assert reopened_api.read_bytes("releases/v1/model.safetensors") == weights_v1
        assert reopened_api.read_bytes("checkpoints/epoch-0002/model.safetensors") == weights_v2

        reopened_download = Path(
            reopened_api.hf_hub_download(
                "releases/v1/model.safetensors",
                revision=second_commit.commit_id,
            )
        )
        assert reopened_download.as_posix().endswith("releases/v1/model.safetensors")
        assert reopened_download.read_bytes() == weights_v1
        assert reopened_api.quick_verify().ok is True
