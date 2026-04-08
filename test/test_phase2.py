"""
Phase 2 end-to-end workflow tests for :mod:`hubvault`.

This module simulates a realistic local release workflow built on the Phase 2
public surface: branch and tag lifecycle, convenience upload/delete APIs,
snapshot exports, reflog audit, detached single-file downloads, and repository
portability after moving the repo directory.
"""

import io
import shutil
from hashlib import sha1, sha256
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, HubVaultApi, RepoFile


def _git_blob_oid(data):
    header = ("blob %d\0" % len(data)).encode("utf-8")
    return sha1(header + data).hexdigest()


def _sha256_value(data):
    return sha256(data).hexdigest()


def _assert_repo_files(api, revision, expected_payloads):
    file_paths = api.list_repo_files(revision=revision)
    assert file_paths == sorted(expected_payloads)

    path_infos = api.get_paths_info(file_paths, revision=revision)
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


@pytest.mark.unittest
class TestPhase2IntegratedLifecycle:
    """
    Exercise the Phase 2 public workflow as a realistic local release process.

    The covered scenario starts from repository bootstrap, seeds the main
    branch, creates an isolated experiment branch and a release tag, publishes
    follow-up content with the Phase 2 convenience APIs, validates history,
    refs, reflogs, detached downloads and snapshot exports, deletes temporary
    branch content, removes temporary refs, and finally reopens the moved
    repository to prove portability.
    """

    def test_phase2_release_flow_from_branching_to_snapshot_and_reopen(self, tmp_path):
        """
        Simulate a realistic Phase 2 artifact promotion workflow end to end.

        The simulated user story is:

        1. Initialize a portable local repository and seed the main branch.
        2. Create an experiment branch and a release tag from the seeded commit.
        3. Upload one file and one filtered folder to the branch through the
           Phase 2 convenience APIs.
        4. Read metadata, commit history, refs, reflogs, detached snapshots,
           detached file downloads, and binary file streams entirely through the
           public API.
        5. Delete temporary branch content with the Phase 2 delete helpers,
           remove temporary refs, and confirm the main branch remains intact.
        6. Move the repository directory and reopen it at a new path without
           losing correctness.
        """

        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir)

        created = api.create_repo()
        assert created.default_branch == "main"
        assert created.head is not None
        assert created.refs == ["refs/heads/main"]

        config_stream = io.BytesIO(b'{"lr":1e-4,"epochs":3}\n')
        base_weights = b"base-weights-v1"

        seed_commit = api.create_commit(
            operations=[
                CommitOperationAdd("configs/train.json", config_stream),
                CommitOperationAdd("models/base/model.bin", base_weights),
            ],
            commit_message="seed main assets",
        )

        api.create_branch(branch="experiments/phase2", revision=seed_commit.oid)
        api.create_tag(tag="seed-release", revision=seed_commit.oid, tag_message="seed cut")

        refs = api.list_repo_refs(include_pull_requests=True)
        assert sorted(item.name for item in refs.branches) == ["experiments/phase2", "main"]
        assert [item.name for item in refs.tags] == ["seed-release"]
        assert refs.tags[0].target_commit == seed_commit.oid
        assert refs.pull_requests == []

        notes_commit = api.upload_file(
            path_or_fileobj=b"phase2-notes-v1\n",
            path_in_repo="runs/phase2/notes.txt",
            revision="experiments/phase2",
        )
        assert notes_commit.commit_message == "Upload runs/phase2/notes.txt with hubvault"
        assert str(notes_commit).endswith("#blob=experiments/phase2:runs/phase2/notes.txt")

        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        (staging_dir / "manifest.json").write_bytes(b'{"candidate":"rc1"}\n')
        (staging_dir / "model.bin").write_bytes(b"candidate-weights-v2")
        (staging_dir / "debug.log").write_bytes(b"ignore me\n")
        (staging_dir / ".git").mkdir()
        (staging_dir / ".git" / "ignored.txt").write_bytes(b"ignored\n")

        folder_commit = api.upload_folder(
            folder_path=staging_dir,
            path_in_repo="artifacts/release-candidate",
            revision="experiments/phase2",
            allow_patterns=["*.json", "*.bin"],
        )
        assert folder_commit.commit_message == "Upload folder using hubvault"
        assert str(folder_commit).endswith("#tree=experiments/phase2:artifacts/release-candidate")

        branch_payloads = {
            "artifacts/release-candidate/manifest.json": b'{"candidate":"rc1"}\n',
            "artifacts/release-candidate/model.bin": b"candidate-weights-v2",
            "configs/train.json": b'{"lr":1e-4,"epochs":3}\n',
            "models/base/model.bin": base_weights,
            "runs/phase2/notes.txt": b"phase2-notes-v1\n",
        }
        _assert_repo_files(api, "experiments/phase2", branch_payloads)

        history_titles = [item.title for item in api.list_repo_commits(revision="experiments/phase2")]
        assert history_titles == [
            "Upload folder using hubvault",
            "Upload runs/phase2/notes.txt with hubvault",
            "seed main assets",
            "Initial commit",
        ]

        root_items = [item.path for item in api.list_repo_tree(revision="experiments/phase2")]
        assert root_items == ["artifacts", "configs", "models", "runs"]
        release_items = [item.path for item in api.list_repo_tree("artifacts/release-candidate", revision="experiments/phase2")]
        assert release_items == [
            "artifacts/release-candidate/manifest.json",
            "artifacts/release-candidate/model.bin",
        ]

        with api.open_file("runs/phase2/notes.txt", revision="experiments/phase2") as fileobj:
            assert fileobj.read() == b"phase2-notes-v1\n"
            assert fileobj.writable() is False

        single_download = Path(
            api.hf_hub_download(
                "artifacts/release-candidate/model.bin",
                revision="experiments/phase2",
            )
        )
        assert single_download.as_posix().endswith("artifacts/release-candidate/model.bin")
        assert single_download.read_bytes() == b"candidate-weights-v2"

        internal_snapshot = Path(
            api.snapshot_download(
                revision="experiments/phase2",
                allow_patterns=["artifacts/*", "configs/*", "models/*", "runs/*"],
            )
        )
        assert (internal_snapshot / "artifacts" / "release-candidate" / "model.bin").read_bytes() == b"candidate-weights-v2"
        assert (internal_snapshot / "runs" / "phase2" / "notes.txt").read_bytes() == b"phase2-notes-v1\n"

        external_snapshot = Path(
            api.snapshot_download(
                revision="experiments/phase2",
                local_dir=tmp_path / "exported-snapshot",
            )
        )
        assert external_snapshot == Path((tmp_path / "exported-snapshot").resolve())
        assert (external_snapshot / ".cache" / "hubvault" / "snapshot.json").is_file()
        assert (external_snapshot / "artifacts" / "release-candidate" / "manifest.json").read_text(
            encoding="utf-8"
        ) == '{"candidate":"rc1"}\n'

        (external_snapshot / "runs" / "phase2" / "notes.txt").write_text("tampered\n", encoding="utf-8")
        rebuilt_snapshot = Path(
            api.snapshot_download(
                revision="experiments/phase2",
                local_dir=tmp_path / "exported-snapshot",
            )
        )
        assert rebuilt_snapshot == external_snapshot
        assert (rebuilt_snapshot / "runs" / "phase2" / "notes.txt").read_text(encoding="utf-8") == "phase2-notes-v1\n"

        delete_notes_commit = api.delete_file("runs/phase2/notes.txt", revision="experiments/phase2")
        delete_artifacts_commit = api.delete_folder("artifacts/release-candidate", revision="experiments/phase2")
        assert delete_notes_commit.commit_message == "Delete runs/phase2/notes.txt with hubvault"
        assert delete_artifacts_commit.commit_message == "Delete folder artifacts/release-candidate with hubvault"

        remaining_branch_payloads = {
            "configs/train.json": b'{"lr":1e-4,"epochs":3}\n',
            "models/base/model.bin": base_weights,
        }
        _assert_repo_files(api, "experiments/phase2", remaining_branch_payloads)

        branch_reflog = api.list_repo_reflog("refs/heads/experiments/phase2")
        assert [item.message for item in branch_reflog] == [
            "Delete folder artifacts/release-candidate with hubvault",
            "Delete runs/phase2/notes.txt with hubvault",
            "Upload folder using hubvault",
            "Upload runs/phase2/notes.txt with hubvault",
            "create branch",
        ]

        tag_reflog = api.list_repo_reflog("refs/tags/seed-release")
        assert [item.message for item in tag_reflog] == ["seed cut"]
        assert tag_reflog[0].new_head == seed_commit.oid

        api.delete_tag(tag="seed-release")
        api.delete_branch(branch="experiments/phase2")

        refs_after_cleanup = api.list_repo_refs()
        assert [item.name for item in refs_after_cleanup.branches] == ["main"]
        assert refs_after_cleanup.tags == []
        cleaned_tag_reflog = api.list_repo_reflog("refs/tags/seed-release")
        assert [item.message for item in cleaned_tag_reflog] == ["delete tag", "seed cut"]

        main_payloads = {
            "configs/train.json": b'{"lr":1e-4,"epochs":3}\n',
            "models/base/model.bin": base_weights,
        }
        _assert_repo_files(api, "main", main_payloads)
        assert api.quick_verify().ok is True

        moved_repo_dir = tmp_path / "moved-portable-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        _assert_repo_files(reopened_api, "main", main_payloads)
        reopened_refs = reopened_api.list_repo_refs()
        assert [item.name for item in reopened_refs.branches] == ["main"]
        assert reopened_refs.tags == []
        assert reopened_api.read_bytes("models/base/model.bin") == base_weights
        assert reopened_api.quick_verify().ok is True
