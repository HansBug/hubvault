"""
Phase 8 interruption-safety tests for :mod:`hubvault`.

This module simulates realistic failure scenarios through the public API only.
The covered workflows inject controlled failures in subprocesses, verify that
interrupted writes are either fully committed or equivalent to never having
happened, and confirm that detached user views remain rebuildable after local
damage.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from hubvault import CommitOperationAdd, HubVaultApi


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_public_api_subprocess(script, *args, failpoint=None, action="raise-runtime", cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if failpoint is not None:
        env["HUBVAULT_FAILPOINT"] = failpoint
        env["HUBVAULT_FAIL_ACTION"] = action
    else:
        env.pop("HUBVAULT_FAILPOINT", None)
        env.pop("HUBVAULT_FAIL_ACTION", None)
    return subprocess.run(
        [sys.executable, "-c", dedent(script)] + [str(item) for item in args],
        cwd=str(cwd or PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


@pytest.mark.unittest
class TestPhase8InterruptionSafety:
    """
    Validate Phase 8 public interruption and recovery guarantees.

    The covered scenarios inject failures into commit, merge, ref-management,
    history-rewrite, and maintenance flows, then confirm through public API
    reads and verification calls that the visible repository state stays
    equivalent to a successful commit or to a state where the interrupted
    operation never happened at all.
    """

    def test_phase8_create_commit_runtime_failure_after_reflog_append_rolls_back_completely(self, tmp_path):
        """
        Simulate an interrupted commit after reflog append but before commit marker.

        The simulated user story creates a seed commit, injects a runtime
        failure into a later ``create_commit()`` exactly after the reflog entry
        has been appended, and verifies that the branch head, file tree,
        reflog length, and verification reports all match the pre-operation
        state as if the interrupted commit had never happened.
        """

        repo_dir = tmp_path / "phase8-create-rollback"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("keep.txt", b"seed\n")],
            commit_message="seed phase8 create rollback",
        )
        reflog_before = list(api.list_repo_reflog("main"))

        script = """
        import sys
        from hubvault import CommitOperationAdd, HubVaultApi

        repo_path = sys.argv[1]
        api = HubVaultApi(repo_path)
        api.create_commit(
            operations=[
                CommitOperationAdd("keep.txt", b"mutated\\n"),
                CommitOperationAdd("broken.txt", b"should-not-land\\n"),
            ],
            commit_message="phase8 interrupted create",
        )
        """
        completed = _run_public_api_subprocess(
            script,
            repo_dir,
            failpoint="create_commit.after_reflog_append",
            action="raise-runtime",
        )

        assert completed.returncode != 0
        assert api.repo_info().head == seed_commit.oid
        assert api.read_bytes("keep.txt") == b"seed\n"
        assert "broken.txt" not in api.list_repo_files()
        assert api.list_repo_commits()[0].commit_id == seed_commit.oid
        assert api.list_repo_reflog("main") == reflog_before
        assert api.quick_verify().ok is True
        assert api.full_verify().ok is True

    def test_phase8_create_commit_process_exit_after_ref_write_recovers_after_move(self, tmp_path):
        """
        Simulate a process crash after branch-head replacement during commit.

        The simulated user story crashes a subprocess during
        ``create_commit()`` immediately after the branch ref has been replaced,
        moves the repository directory before reopening it, and then verifies
        that recovery restores the old head, preserves the old file contents,
        and allows subsequent public writes to proceed normally.
        """

        repo_dir = tmp_path / "phase8-create-exit"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        seed_commit = api.create_commit(
            operations=[CommitOperationAdd("keep.txt", b"seed\n")],
            commit_message="seed phase8 exit",
        )

        script = """
        import sys
        from hubvault import CommitOperationAdd, HubVaultApi

        repo_path = sys.argv[1]
        api = HubVaultApi(repo_path)
        api.create_commit(
            operations=[CommitOperationAdd("after-exit.txt", b"nope\\n")],
            commit_message="phase8 crash create",
        )
        """
        completed = _run_public_api_subprocess(
            script,
            repo_dir,
            failpoint="create_commit.after_ref_write",
            action="exit",
        )

        assert completed.returncode != 0

        moved_repo_dir = tmp_path / "phase8-create-exit-moved"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        assert reopened_api.repo_info().head == seed_commit.oid
        assert reopened_api.read_bytes("keep.txt") == b"seed\n"
        assert "after-exit.txt" not in reopened_api.list_repo_files()
        assert reopened_api.quick_verify().ok is True
        assert reopened_api.full_verify().ok is True

        follow_up = reopened_api.create_commit(
            operations=[CommitOperationAdd("recovered.txt", b"ok\n")],
            commit_message="phase8 recovered create",
        )
        assert reopened_api.repo_info().head == follow_up.oid
        assert reopened_api.read_bytes("recovered.txt") == b"ok\n"

    def test_phase8_merge_and_ref_operations_roll_back_to_never_happened_state(self, tmp_path):
        """
        Simulate interrupted merge and ref-management operations through public APIs.

        The simulated user story creates a small branch/tag topology, injects
        runtime failures after reflog append for merge, branch creation,
        branch deletion, tag creation, tag deletion, and branch reset, and
        verifies after each subprocess that the visible refs, history, and file
        tree remain exactly as they were before the interrupted operation.
        """

        repo_dir = tmp_path / "phase8-refs"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        base_commit = api.create_commit(
            operations=[CommitOperationAdd("shared.txt", b"base\n")],
            commit_message="phase8 base",
        )
        api.create_branch(branch="feature")
        feature_commit = api.create_commit(
            revision="feature",
            operations=[CommitOperationAdd("feature.txt", b"feature\n")],
            commit_message="phase8 feature",
        )
        main_commit = api.create_commit(
            operations=[CommitOperationAdd("main.txt", b"main\n")],
            commit_message="phase8 main",
        )
        api.create_branch(branch="ephemeral")
        api.create_tag(tag="stable", revision="main")

        merge_reflog_before = list(api.list_repo_reflog("main"))
        merge_script = """
        import sys
        from hubvault import HubVaultApi

        repo_path = sys.argv[1]
        HubVaultApi(repo_path).merge("feature")
        """
        merge_completed = _run_public_api_subprocess(
            merge_script,
            repo_dir,
            failpoint="merge.after_reflog_append",
            action="raise-runtime",
        )

        assert merge_completed.returncode != 0
        assert api.repo_info().head == main_commit.oid
        assert "feature.txt" not in api.list_repo_files()
        assert api.list_repo_reflog("main") == merge_reflog_before

        scenarios = [
            (
                "create_branch.after_reflog_append",
                """
                import sys
                from hubvault import HubVaultApi

                repo_path = sys.argv[1]
                HubVaultApi(repo_path).create_branch(branch="broken-branch")
                """,
                lambda current_api: "broken-branch" not in [item.name for item in current_api.list_repo_refs().branches],
            ),
            (
                "delete_branch.after_reflog_append",
                """
                import sys
                from hubvault import HubVaultApi

                repo_path = sys.argv[1]
                HubVaultApi(repo_path).delete_branch(branch="ephemeral")
                """,
                lambda current_api: "ephemeral" in [item.name for item in current_api.list_repo_refs().branches],
            ),
            (
                "create_tag.after_reflog_append",
                """
                import sys
                from hubvault import HubVaultApi

                repo_path = sys.argv[1]
                HubVaultApi(repo_path).create_tag(tag="broken-tag", revision="main")
                """,
                lambda current_api: "broken-tag" not in [item.name for item in current_api.list_repo_refs().tags],
            ),
            (
                "delete_tag.after_reflog_append",
                """
                import sys
                from hubvault import HubVaultApi

                repo_path = sys.argv[1]
                HubVaultApi(repo_path).delete_tag(tag="stable")
                """,
                lambda current_api: "stable" in [item.name for item in current_api.list_repo_refs().tags],
            ),
            (
                "reset_ref.after_reflog_append",
                """
                import sys
                from hubvault import HubVaultApi

                repo_path, target_commit = sys.argv[1:3]
                HubVaultApi(repo_path).reset_ref("main", target_commit)
                """,
                lambda current_api: current_api.repo_info().head == main_commit.oid,
                base_commit.oid,
            ),
        ]

        for scenario in scenarios:
            failpoint = scenario[0]
            script = scenario[1]
            predicate = scenario[2]
            extra_args = scenario[3:] if len(scenario) > 3 else ()
            completed = _run_public_api_subprocess(
                script,
                repo_dir,
                *extra_args,
                failpoint=failpoint,
                action="raise-runtime",
            )
            assert completed.returncode != 0, failpoint + "\n" + completed.stdout + completed.stderr
            assert predicate(api), failpoint
            assert api.read_bytes("shared.txt") == b"base\n"
            assert api.repo_info().head == main_commit.oid
            assert api.quick_verify().ok is True
            assert api.full_verify().ok is True

        successful_merge = api.merge("feature")
        assert successful_merge.status == "merged"
        assert successful_merge.source_head == feature_commit.oid
        assert api.read_bytes("feature.txt") == b"feature\n"

    def test_phase8_squash_crash_gc_interruption_and_detached_view_damage_remain_safe(self, tmp_path):
        """
        Simulate interrupted maintenance and damaged detached views in one lifecycle.

        The simulated user story creates a chunked-history repository, crashes a
        subprocess during ``squash_history()`` after the branch ref has been
        replaced, moves and reopens the repository to trigger recovery, then
        damages detached download/snapshot outputs, confirms they rebuild
        cleanly, and finally interrupts ``gc()`` after new chunk state has been
        published while verifying that the repository remains readable and
        verifiable throughout.
        """

        repo_dir = tmp_path / "phase8-maintenance"
        api = HubVaultApi(repo_dir)
        api.create_repo(large_file_threshold=64)
        initial_commit = api.repo_info().head
        commit_v1 = api.create_commit(
            operations=[
                CommitOperationAdd("models/model.bin", b"A" * 160),
                CommitOperationAdd("notes/readme.txt", b"v1\n"),
            ],
            commit_message="phase8 v1",
        )
        commit_v2 = api.create_commit(
            operations=[
                CommitOperationAdd("models/model.bin", b"B" * 192),
                CommitOperationAdd("notes/readme.txt", b"v2\n"),
            ],
            commit_message="phase8 v2",
        )

        squash_script = """
        import sys
        from hubvault import HubVaultApi

        repo_path, root_commit = sys.argv[1:3]
        HubVaultApi(repo_path).squash_history("main", root_revision=root_commit, run_gc=False)
        """
        squash_completed = _run_public_api_subprocess(
            squash_script,
            repo_dir,
            commit_v2.oid,
            failpoint="squash_history.after_ref_write",
            action="exit",
        )
        assert squash_completed.returncode != 0

        moved_repo_dir = tmp_path / "phase8-maintenance-moved"
        shutil.move(str(repo_dir), str(moved_repo_dir))
        reopened_api = HubVaultApi(moved_repo_dir)

        assert reopened_api.repo_info().head == commit_v2.oid
        assert [item.commit_id for item in reopened_api.list_repo_commits()] == [commit_v2.oid, commit_v1.oid, initial_commit]
        assert reopened_api.read_bytes("models/model.bin") == b"B" * 192
        assert reopened_api.full_verify().ok is True

        download_path = Path(reopened_api.hf_hub_download("models/model.bin"))
        snapshot_root = Path(reopened_api.snapshot_download())
        download_path.unlink()
        download_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_file = snapshot_root / "notes" / "readme.txt"
        snapshot_file.unlink()
        snapshot_file.mkdir(parents=False)

        repaired_download = Path(reopened_api.hf_hub_download("models/model.bin"))
        repaired_snapshot = Path(reopened_api.snapshot_download())
        assert repaired_download.read_bytes() == b"B" * 192
        assert repaired_snapshot.joinpath("notes", "readme.txt").read_bytes() == b"v2\n"

        gc_script = """
        import sys
        from hubvault import HubVaultApi

        repo_path = sys.argv[1]
        HubVaultApi(repo_path).gc(dry_run=False, prune_cache=True)
        """
        gc_completed = _run_public_api_subprocess(
            gc_script,
            moved_repo_dir,
            failpoint="gc.after_publish",
            action="raise-runtime",
        )

        assert gc_completed.returncode != 0
        assert reopened_api.read_bytes("models/model.bin") == b"B" * 192
        assert reopened_api.read_bytes("notes/readme.txt") == b"v2\n"
        assert reopened_api.quick_verify().ok is True
        assert reopened_api.full_verify().ok is True
