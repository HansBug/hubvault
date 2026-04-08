"""
Phase 1 end-to-end workflow tests for :mod:`hubvault`.

This module simulates realistic local ML artifact repository usage through the
current public API surface. The covered workflow starts from repository
initialization, publishes multiple commits from different input forms, reads
historical revisions, validates file metadata and commit history, exports
detached file views, performs copy/delete based changes, resets a branch head,
and finally reopens the moved repository from a new filesystem location.
"""

import io
import shutil
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete, HubVaultApi, RepoFile, RepoFolder


def _git_blob_oid(data):
    header = ("blob %d\0" % len(data)).encode("utf-8")
    return sha1(header + data).hexdigest()


def _sha256_value(data):
    return sha256(data).hexdigest()


def _assert_file_metadata(path_infos, expected_payloads):
    by_path = {item.path: item for item in path_infos}

    assert sorted(by_path) == sorted(expected_payloads)
    for path, payload in expected_payloads.items():
        info = by_path[path]
        assert isinstance(info, RepoFile)
        assert info.size == len(payload)
        assert info.oid == _git_blob_oid(payload)
        assert info.blob_id == _git_blob_oid(payload)
        assert info.sha256 == _sha256_value(payload)
        assert info.etag == _git_blob_oid(payload)
        assert info.lfs is None


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
        3. Read repository metadata, commit history, tree listings, per-file
           size/hash metadata, binary file streams, and detached download views.
        4. Publish follow-up commits that copy released files, delete obsolete
           paths, and record a fresh manifest while preserving verifiable
           history.
        5. Roll the branch back to a validated commit, confirm the visible
           commit list changes as expected, and reopen the moved repo at a
           different absolute path to prove portability.
        """

        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir)

        created = api.create_repo()
        assert created.default_branch == "main"
        assert created.head is not None
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
        config_bytes = config_source.read_bytes()
        tokenizer_bytes = b'{"bos_token":"<s>","eos_token":"</s>"}\n'

        first_commit_files = {
            "checkpoints/epoch-0001/model.safetensors": weights_v1,
            "configs/model.json": config_bytes,
            "runs/run-0001/notes.txt": training_note,
            "tokenizer/tokenizer.json": tokenizer_bytes,
        }

        first_commit = api.create_commit(
            operations=[
                CommitOperationAdd("configs/model.json", str(config_source)),
                CommitOperationAdd("tokenizer/tokenizer.json", tokenizer_stream),
                CommitOperationAdd("runs/run-0001/notes.txt", training_note),
                CommitOperationAdd("checkpoints/epoch-0001/model.safetensors", weights_v1),
            ],
            commit_message="seed phase1 assets",
        )

        current_info = api.repo_info()
        assert current_info.head == first_commit.oid
        assert first_commit.commit_message == "seed phase1 assets"
        assert first_commit.commit_description == ""
        assert first_commit.repo_url.startswith("file:")
        assert first_commit.oid.startswith("sha256:")
        assert api.list_repo_files() == sorted(first_commit_files)
        first_history = api.list_repo_commits()
        assert [item.commit_id for item in first_history] == [first_commit.oid, created.head]
        assert first_history[0].authors == []
        assert first_history[0].title == "seed phase1 assets"
        assert first_history[0].message == ""
        assert first_history[0].formatted_title is None
        assert first_history[0].formatted_message is None
        assert first_history[0].created_at.tzinfo is not None
        assert first_history[1].title == "Initial commit"

        root_items = [item.path for item in api.list_repo_tree()]
        assert root_items == ["checkpoints", "configs", "runs", "tokenizer"]
        assert all(isinstance(item, RepoFolder) for item in api.list_repo_tree())

        checkpoint_items = [item.path for item in api.list_repo_tree("checkpoints")]
        assert checkpoint_items == ["checkpoints/epoch-0001"]
        recursive_checkpoint_items = api.list_repo_tree("checkpoints", recursive=True)
        assert [item.path for item in recursive_checkpoint_items] == [
            "checkpoints/epoch-0001",
            "checkpoints/epoch-0001/model.safetensors",
        ]

        first_path_infos = api.get_paths_info(api.list_repo_files())
        _assert_file_metadata(first_path_infos, first_commit_files)

        mixed_path_infos = api.get_paths_info(
            [
                "checkpoints",
                "checkpoints/epoch-0001/model.safetensors",
                "configs/model.json",
                "missing.file",
            ]
        )
        assert [type(item).__name__ for item in mixed_path_infos] == ["RepoFolder", "RepoFile", "RepoFile"]
        assert isinstance(mixed_path_infos[0], RepoFolder)
        assert mixed_path_infos[0].tree_id.startswith("sha256:")
        assert mixed_path_infos[1].size == len(weights_v1)
        assert mixed_path_infos[1].oid == _git_blob_oid(weights_v1)
        assert mixed_path_infos[1].blob_id == _git_blob_oid(weights_v1)
        assert mixed_path_infos[1].sha256 == _sha256_value(weights_v1)
        assert mixed_path_infos[2].size == len(config_bytes)
        assert mixed_path_infos[2].sha256 == _sha256_value(config_bytes)

        assert api.read_bytes("runs/run-0001/notes.txt", revision=first_commit.oid) == training_note
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
                CommitOperationCopy("configs", "releases/v1/configs", src_revision=first_commit.oid),
                CommitOperationCopy(
                    "checkpoints/epoch-0001/model.safetensors",
                    "releases/v1/model.safetensors",
                    src_revision=first_commit.oid,
                ),
                CommitOperationDelete("runs/run-0001/"),
                CommitOperationAdd("checkpoints/epoch-0002/model.safetensors", weights_v2),
            ],
            parent_commit=first_commit.oid,
            commit_message="publish v1 and advance checkpoint",
        )
        assert second_commit.commit_message == "publish v1 and advance checkpoint"
        assert second_commit.oid.startswith("sha256:")

        third_commit = api.create_commit(
            operations=[CommitOperationAdd("manifests/latest.json", manifest_v2)],
            commit_message="record latest manifest",
            parent_commit=second_commit.oid,
        )
        assert third_commit.commit_message == "record latest manifest"
        assert third_commit.oid.startswith("sha256:")
        assert api.repo_info().head == third_commit.oid

        full_history = api.list_repo_commits()
        assert [item.commit_id for item in full_history] == [
            third_commit.oid,
            second_commit.oid,
            first_commit.oid,
            created.head,
        ]
        assert [item.title for item in full_history] == [
            "record latest manifest",
            "publish v1 and advance checkpoint",
            "seed phase1 assets",
            "Initial commit",
        ]
        assert [item.commit_id for item in api.list_repo_commits(revision=second_commit.oid)] == [
            second_commit.oid,
            first_commit.oid,
            created.head,
        ]
        assert [item.commit_id for item in api.list_repo_commits(revision=first_commit.oid)] == [
            first_commit.oid,
            created.head,
        ]
        formatted_history = api.list_repo_commits(formatted=True)
        assert [item.commit_id for item in formatted_history] == [
            third_commit.oid,
            second_commit.oid,
            first_commit.oid,
            created.head,
        ]
        assert formatted_history[0].formatted_title == "record latest manifest"
        assert formatted_history[0].formatted_message == ""

        assert api.list_repo_files(revision=first_commit.oid) == sorted(first_commit_files)

        latest_files = {
            "checkpoints/epoch-0001/model.safetensors",
            "checkpoints/epoch-0002/model.safetensors",
            "configs/model.json",
            "manifests/latest.json",
            "releases/v1/configs/model.json",
            "releases/v1/model.safetensors",
            "tokenizer/tokenizer.json",
        }
        assert api.list_repo_files() == sorted(latest_files)

        latest_file_payloads = {
            "checkpoints/epoch-0001/model.safetensors": weights_v1,
            "checkpoints/epoch-0002/model.safetensors": weights_v2,
            "configs/model.json": config_bytes,
            "manifests/latest.json": manifest_v2,
            "releases/v1/configs/model.json": config_bytes,
            "releases/v1/model.safetensors": weights_v1,
            "tokenizer/tokenizer.json": tokenizer_bytes,
        }
        latest_path_infos = api.get_paths_info(api.list_repo_files())
        _assert_file_metadata(latest_path_infos, latest_file_payloads)

        release_items = [item.path for item in api.list_repo_tree("releases/v1")]
        assert release_items == ["releases/v1/configs", "releases/v1/model.safetensors"]
        release_infos = api.get_paths_info(["releases/v1", "releases/v1/model.safetensors"])
        assert [type(item).__name__ for item in release_infos] == ["RepoFolder", "RepoFile"]
        assert release_infos[1].size == len(weights_v1)
        assert release_infos[1].oid == _git_blob_oid(weights_v1)
        assert release_infos[1].sha256 == _sha256_value(weights_v1)
        assert api.read_bytes("releases/v1/model.safetensors", revision=third_commit.oid) == weights_v1
        assert api.read_bytes("checkpoints/epoch-0002/model.safetensors") == weights_v2

        reset_commit = api.reset_ref("main", to_revision=second_commit.oid)
        assert reset_commit.oid == second_commit.oid
        assert api.repo_info().head == second_commit.oid
        reset_history = api.list_repo_commits()
        assert [item.commit_id for item in reset_history] == [
            second_commit.oid,
            first_commit.oid,
            created.head,
        ]
        assert [item.title for item in reset_history] == [
            "publish v1 and advance checkpoint",
            "seed phase1 assets",
            "Initial commit",
        ]

        reset_file_payloads = {
            "checkpoints/epoch-0001/model.safetensors": weights_v1,
            "checkpoints/epoch-0002/model.safetensors": weights_v2,
            "configs/model.json": config_bytes,
            "releases/v1/configs/model.json": config_bytes,
            "releases/v1/model.safetensors": weights_v1,
            "tokenizer/tokenizer.json": tokenizer_bytes,
        }
        assert api.list_repo_files() == sorted(reset_file_payloads)
        reset_path_infos = api.get_paths_info(api.list_repo_files())
        _assert_file_metadata(reset_path_infos, reset_file_payloads)

        final_report = api.quick_verify()
        assert final_report.ok is True
        assert final_report.errors == []
        assert "refs/heads/main" in final_report.checked_refs

        moved_repo_dir = tmp_path / "moved-portable-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        reopened_info = reopened_api.repo_info()
        assert reopened_info.head == second_commit.oid
        reopened_history = reopened_api.list_repo_commits()
        assert [item.commit_id for item in reopened_history] == [
            second_commit.oid,
            first_commit.oid,
            created.head,
        ]
        assert reopened_api.read_bytes("releases/v1/model.safetensors") == weights_v1
        assert reopened_api.read_bytes("checkpoints/epoch-0002/model.safetensors") == weights_v2
        reopened_path_infos = reopened_api.get_paths_info(reopened_api.list_repo_files())
        _assert_file_metadata(reopened_path_infos, reset_file_payloads)

        reopened_download = Path(
            reopened_api.hf_hub_download(
                "releases/v1/model.safetensors",
                revision=second_commit.oid,
            )
        )
        assert reopened_download.as_posix().endswith("releases/v1/model.safetensors")
        assert reopened_download.read_bytes() == weights_v1
        assert reopened_api.quick_verify().ok is True
