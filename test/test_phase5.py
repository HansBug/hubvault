"""
Phase 5 merge workflow tests for :mod:`hubvault`.

This module simulates realistic merge-centric user flows built on the Phase 5
public surface: branching, tagging, chunked large-file edits, merge execution,
history traversal, reflog inspection, and repository reopening after the merge.
"""

import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, HubVaultApi, MergeResult, RepoFile
from hubvault.storage.chunk import canonical_lfs_pointer, git_blob_oid as lfs_pointer_oid


def _sha256_value(data):
    return sha256(data).hexdigest()


@pytest.mark.unittest
class TestPhase5IntegratedMergeWorkflow:
    """
    Exercise the Phase 5 public merge workflow as a realistic lifecycle.

    The covered scenario initializes a repository with chunked storage, creates
    diverging main/feature histories, tags the feature tip, merges the tagged
    feature snapshot back into main, verifies the merge result and history
    shape, and finally reopens the moved repository to prove that the merge
    result remains portable and readable.
    """

    def test_phase5_merge_workflow_with_tagged_chunked_source_branch(self, tmp_path):
        """
        Simulate a realistic Phase 5 merge workflow with a tagged chunked source.

        The simulated user story is:

        1. Initialize a repository with a small chunk threshold.
        2. Create a shared base commit on ``main`` and branch ``feature`` from it.
        3. Advance ``feature`` with a chunked large-file update and a feature note.
        4. Advance ``main`` independently with its own file change.
        5. Tag the feature tip and merge the tag into ``main``.
        6. Verify merged files, file metadata, reachable commit history, reflog,
           repository verification, and reopen-after-move portability.
        """

        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=64)

        base_model = b"A" * 128
        merged_model = b"B" * 512
        feature_note = b"feature-note\n"
        main_note = b"main-note\n"

        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("artifacts/model.bin", base_model)],
            commit_message="seed phase5 base",
        )
        api.create_branch(branch="feature")

        feature_commit = api.create_commit(
            revision="feature",
            operations=[
                CommitOperationAdd("artifacts/model.bin", merged_model),
                CommitOperationAdd("notes/feature.txt", feature_note),
            ],
            commit_message="feature phase5 chunked update",
        )
        main_commit = api.create_commit(
            operations=[CommitOperationAdd("notes/main.txt", main_note)],
            commit_message="main phase5 note",
        )
        api.create_tag(tag="feature-ready", revision="feature")

        merge_result = api.merge("feature-ready")

        assert isinstance(merge_result, MergeResult)
        assert merge_result.status == "merged"
        assert merge_result.fast_forward is False
        assert merge_result.created_commit is True
        assert merge_result.base_commit == seed_commit.oid
        assert merge_result.target_head_before == main_commit.oid
        assert merge_result.source_head == feature_commit.oid
        assert merge_result.head_after == merge_result.commit.oid
        assert merge_result.commit.commit_message == "Merge feature-ready into main"
        assert merge_result.conflicts == []

        assert api.read_bytes("artifacts/model.bin") == merged_model
        assert api.read_bytes("notes/feature.txt") == feature_note
        assert api.read_bytes("notes/main.txt") == main_note

        model_info = api.get_paths_info(["artifacts/model.bin"])[0]
        assert isinstance(model_info, RepoFile)
        assert model_info.size == len(merged_model)
        assert model_info.blob_id == lfs_pointer_oid(canonical_lfs_pointer(_sha256_value(merged_model), len(merged_model)))
        assert model_info.sha256 == _sha256_value(merged_model)
        assert model_info.lfs is not None
        assert model_info.lfs.size == len(merged_model)
        assert model_info.lfs.sha256 == _sha256_value(merged_model)

        history_ids = [item.commit_id for item in api.list_repo_commits()]
        assert history_ids[0] == merge_result.commit.oid
        assert main_commit.oid in history_ids
        assert feature_commit.oid in history_ids
        assert seed_commit.oid in history_ids

        reflog = api.list_repo_reflog("main")
        assert reflog[0].new_head == merge_result.commit.oid
        assert reflog[0].message == "Merge feature-ready into main"

        assert api.quick_verify().ok is True
        assert api.full_verify().ok is True

        moved_repo_dir = tmp_path / "moved-portable-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        assert reopened_api.read_bytes("artifacts/model.bin") == merged_model
        assert reopened_api.read_bytes("notes/feature.txt") == feature_note
        assert reopened_api.read_bytes("notes/main.txt") == main_note
        assert reopened_api.repo_info().head == merge_result.commit.oid
        assert reopened_api.full_verify().ok is True
        assert Path(reopened_api.hf_hub_download("artifacts/model.bin")).read_bytes() == merged_model
