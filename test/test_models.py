from datetime import datetime, timezone
from dataclasses import FrozenInstanceError

import pytest

from hubvault.models import (
    BlobLfsInfo,
    BlobSecurityInfo,
    CommitInfo,
    GcReport,
    GitCommitInfo,
    GitRefInfo,
    GitRefs,
    LastCommitInfo,
    MergeConflict,
    MergeResult,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    RepoInfo,
    SquashReport,
    StorageOverview,
    StorageSectionInfo,
    VerifyReport,
)


@pytest.mark.unittest
class TestModels:
    def test_repo_info_defaults_and_is_frozen(self):
        info = RepoInfo(
            repo_path="/tmp/repo",
            format_version=1,
            default_branch="main",
            head=None,
        )

        assert info.refs == []
        with pytest.raises(FrozenInstanceError):
            info.default_branch = "dev"

    def test_public_models_align_with_hf_style_fields(self):
        commit = CommitInfo(
            commit_url="file:///tmp/repo#commit=sha256:c1",
            commit_message="hello",
            commit_description="world",
            oid="sha256:c1",
        )
        lfs = BlobLfsInfo(size=1024, sha256="def", pointer_size=128)
        last_commit = LastCommitInfo(
            oid="sha256:c1",
            title="seed",
            date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        security = BlobSecurityInfo(
            safe=True,
            status="safe",
            av_scan=None,
            pickle_import_scan=None,
        )
        repo_file = RepoFile(
            path="model.bin",
            size=3,
            blob_id="blob",
            lfs=lfs,
            last_commit=last_commit,
            security=security,
            oid="blob",
            sha256="abc",
            etag="etag",
        )
        repo_folder = RepoFolder(
            path="folder",
            tree_id="tree",
            last_commit=last_commit,
        )
        git_commit = GitCommitInfo(
            commit_id="sha256:c2",
            authors=["tester"],
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            title="seed",
            message="body",
            formatted_title="<p>seed</p>",
            formatted_message="<p>body</p>",
        )
        git_ref = GitRefInfo(
            name="main",
            ref="refs/heads/main",
            target_commit=None,
        )
        git_refs = GitRefs(
            branches=[git_ref],
            converts=[],
            tags=[],
            pull_requests=[],
        )
        merge_conflict = MergeConflict(
            path="demo.txt",
            conflict_type="modify/modify",
            message="Both sides changed demo.txt differently.",
            base_oid="base-oid",
            target_oid="target-oid",
            source_oid="source-oid",
            related_path=None,
        )
        reflog_entry = ReflogEntry(
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            ref_name="refs/heads/main",
            old_head=None,
            new_head="sha256:c1",
            message="seed",
            checksum="sha256:deadbeef",
        )
        report = VerifyReport(ok=True)
        section = StorageSectionInfo(
            name="cache",
            path="cache/",
            total_size=1024,
            file_count=3,
            reclaimable_size=1024,
            reclaim_strategy="prune-cache",
            notes="Detached views can be rebuilt.",
        )
        overview = StorageOverview(
            total_size=4096,
            reachable_size=2048,
            historical_retained_size=1024,
            reclaimable_gc_size=512,
            reclaimable_cache_size=256,
            reclaimable_temporary_size=128,
            sections=[section],
            recommendations=["Run gc()."],
        )
        gc_report = GcReport(
            dry_run=True,
            checked_refs=["refs/heads/main"],
            reclaimed_size=768,
            reclaimed_object_size=512,
            reclaimed_chunk_size=128,
            reclaimed_cache_size=64,
            reclaimed_temporary_size=64,
            removed_file_count=4,
            notes=["dry-run"],
        )
        squash_report = SquashReport(
            ref_name="refs/heads/main",
            old_head="sha256:c1",
            new_head="sha256:c2",
            root_commit_before="sha256:c1",
            rewritten_commit_count=1,
            dropped_ancestor_count=2,
            blocking_refs=["refs/tags/v1"],
            gc_report=gc_report,
        )
        merge_result = MergeResult(
            status="merged",
            target_revision="main",
            source_revision="feature",
            base_commit="sha256:b0",
            target_head_before="sha256:t0",
            source_head="sha256:s0",
            head_after="sha256:m1",
            commit=commit,
            conflicts=[merge_conflict],
            fast_forward=False,
            created_commit=True,
        )

        assert commit.oid == "sha256:c1"
        assert commit.commit_message == "hello"
        assert commit.commit_description == "world"
        assert commit.repo_url == "file:///tmp/repo"
        assert commit.pr_num is None
        assert str(commit) == commit.commit_url
        assert git_commit.authors == ["tester"]
        assert git_ref.target_commit is None
        assert git_refs.branches[0].ref == "refs/heads/main"
        assert git_refs.pull_requests == []
        assert merge_conflict.source_oid == "source-oid"
        assert merge_result.status == "merged"
        assert merge_result.commit == commit
        assert merge_result.conflicts == [merge_conflict]
        assert merge_result.created_commit is True
        assert reflog_entry.message == "seed"
        assert reflog_entry.ref_name == "refs/heads/main"
        assert lfs.pointer_size == 128
        assert repo_file.rfilename == "model.bin"
        assert repo_file.lastCommit == last_commit
        assert repo_folder.tree_id == "tree"
        assert repo_folder.lastCommit == last_commit
        assert report.checked_refs == []
        assert report.warnings == []
        assert report.errors == []
        assert section.reclaim_strategy == "prune-cache"
        assert overview.sections[0] == section
        assert overview.historical_retained_size == 1024
        assert gc_report.dry_run is True
        assert gc_report.checked_refs == ["refs/heads/main"]
        assert squash_report.blocking_refs == ["refs/tags/v1"]
        assert squash_report.gc_report == gc_report
