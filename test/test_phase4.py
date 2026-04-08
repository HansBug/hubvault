"""
Phase 4 maintenance workflow tests for :mod:`hubvault`.

This module simulates a realistic maintenance lifecycle built on the Phase 4
public surface: full verification, storage analysis, history squashing,
chunk-store compaction, cache pruning, and post-maintenance repository
reopening.
"""

import shutil
from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, GcReport, HubVaultApi, SquashReport, StorageOverview


@pytest.mark.unittest
class TestPhase4IntegratedLifecycle:
    """
    Exercise the Phase 4 public maintenance workflow as a realistic lifecycle.

    The covered scenario initializes a repository with chunked storage enabled,
    creates two generations of large and small files, inspects repository space
    usage, squashes the branch so rollback-only history becomes reclaimable,
    runs GC with cache pruning, and finally reopens the moved repository to
    prove that the compacted result remains portable and readable.
    """

    def test_phase4_maintenance_workflow_from_analysis_to_compaction(self, tmp_path):
        """
        Simulate a realistic Phase 4 maintenance workflow from analysis to reopen.

        The simulated user story is:

        1. Initialize a repository with a small chunk threshold.
        2. Create two generations of the same large artifact so rollback history
           retains both whole branch states.
        3. Materialize detached views to populate managed cache space.
        4. Inspect the public storage overview and confirm that history and
           cache both consume measurable space.
        5. Squash the branch at the latest commit and immediately run GC with
           cache pruning so old history becomes unreachable and reclaimable.
        6. Reopen the moved repository and verify that the compacted storage is
           still portable and correct.
        """

        repo_dir = tmp_path / "portable-repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=64)

        model_v1 = b"A" * 512
        model_v2 = b"B" * 768
        notes_v1 = b"notes-v1\n"
        notes_v2 = b"notes-v2\n"

        _ = api.create_commit(
            operations=[
                CommitOperationAdd("artifacts/model.bin", model_v1),
                CommitOperationAdd("notes/readme.txt", notes_v1),
            ],
            commit_message="seed phase4 v1",
        )
        second_commit = api.create_commit(
            operations=[
                CommitOperationAdd("artifacts/model.bin", model_v2),
                CommitOperationAdd("notes/readme.txt", notes_v2),
            ],
            commit_message="seed phase4 v2",
        )

        _ = api.hf_hub_download("artifacts/model.bin")
        _ = api.snapshot_download()

        overview_before = api.get_storage_overview()
        assert isinstance(overview_before, StorageOverview)
        assert overview_before.total_size > 0
        assert overview_before.historical_retained_size > 0
        assert overview_before.reclaimable_cache_size > 0
        assert any(section.name == "cache" and section.reclaimable_size > 0 for section in overview_before.sections)
        assert any("squash_history" in item for item in overview_before.recommendations)
        assert api.full_verify().ok is True

        squash_report = api.squash_history(
            "main",
            root_revision=second_commit.oid,
            run_gc=True,
            prune_cache=True,
        )

        assert isinstance(squash_report, SquashReport)
        assert squash_report.ref_name == "refs/heads/main"
        assert squash_report.old_head == second_commit.oid
        assert squash_report.new_head != second_commit.oid
        assert squash_report.root_commit_before == second_commit.oid
        assert squash_report.rewritten_commit_count == 1
        assert squash_report.dropped_ancestor_count == 2
        assert squash_report.blocking_refs == []
        assert isinstance(squash_report.gc_report, GcReport)
        assert squash_report.gc_report.dry_run is False
        assert squash_report.gc_report.reclaimed_size > 0

        assert api.list_repo_files() == [
            "artifacts/model.bin",
            "notes/readme.txt",
        ]
        assert api.read_bytes("artifacts/model.bin") == model_v2
        assert api.read_bytes("notes/readme.txt") == notes_v2
        assert len(api.list_repo_commits()) == 1

        overview_after = api.get_storage_overview()
        assert overview_after.historical_retained_size == 0
        assert overview_after.reclaimable_cache_size == 0
        assert overview_after.reclaimable_gc_size == 0
        assert overview_after.total_size < overview_before.total_size

        pack_files = sorted((repo_dir / "chunks" / "packs").glob("*.pack"))
        assert len(pack_files) == 1
        assert api.full_verify().ok is True

        moved_repo_dir = tmp_path / "moved-portable-repo"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        assert reopened_api.read_bytes("artifacts/model.bin") == model_v2
        assert reopened_api.read_bytes("notes/readme.txt") == notes_v2
        assert len(reopened_api.list_repo_commits()) == 1
        assert Path(reopened_api.hf_hub_download("artifacts/model.bin")).read_bytes() == model_v2
        assert reopened_api.full_verify().ok is True
