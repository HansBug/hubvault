from datetime import datetime

import pytest

from hubvault.models import (
    BlobLfsInfo,
    BlobSecurityInfo,
    CommitInfo,
    GcReport,
    LastCommitInfo,
    MergeConflict,
    MergeResult,
    SquashReport,
    StorageOverview,
    StorageSectionInfo,
    VerifyReport,
)
from hubvault.server.serde import (
    encode_blob_lfs_info,
    encode_blob_security_info,
    encode_commit_info,
    encode_gc_report,
    encode_last_commit_info,
    encode_merge_result,
    encode_repo_entry,
    encode_squash_report,
    encode_storage_overview,
    encode_verify_report,
)


@pytest.mark.unittest
class TestServerSerde:
    def test_optional_encoders_serialize_full_payloads(self):
        timestamp = datetime(2026, 4, 11, 12, 0, 0)

        assert encode_last_commit_info(LastCommitInfo("oid-1", "seed", timestamp)) == {
            "oid": "oid-1",
            "title": "seed",
            "date": timestamp.isoformat(),
        }
        assert encode_blob_security_info(
            BlobSecurityInfo(
                safe=True,
                status="ok",
                av_scan={"status": "clean"},
                pickle_import_scan=None,
            )
        ) == {
            "safe": True,
            "status": "ok",
            "av_scan": {"status": "clean"},
            "pickle_import_scan": None,
        }
        assert encode_blob_lfs_info(BlobLfsInfo(size=10, sha256="abc", pointer_size=12)) == {
            "size": 10,
            "sha256": "abc",
            "pointer_size": 12,
        }

    def test_encode_repo_entry_rejects_unsupported_models(self):
        with pytest.raises(TypeError, match="Unsupported repository entry model"):
            encode_repo_entry(object())

    def test_encode_verify_report_and_storage_overview(self):
        report = VerifyReport(
            ok=False,
            checked_refs=["refs/heads/main"],
            warnings=["stale view"],
            errors=["missing blob"],
        )
        overview = StorageOverview(
            total_size=100,
            reachable_size=60,
            historical_retained_size=20,
            reclaimable_gc_size=10,
            reclaimable_cache_size=5,
            reclaimable_temporary_size=5,
            sections=[
                StorageSectionInfo(
                    name="cache",
                    path="cache/",
                    total_size=5,
                    file_count=1,
                    reclaimable_size=5,
                    reclaim_strategy="prune-cache",
                    notes="Detached cache files.",
                )
            ],
            recommendations=["Run gc()."],
        )

        assert encode_verify_report(report) == {
            "ok": False,
            "checked_refs": ["refs/heads/main"],
            "warnings": ["stale view"],
            "errors": ["missing blob"],
        }
        assert encode_storage_overview(overview) == {
            "total_size": 100,
            "reachable_size": 60,
            "historical_retained_size": 20,
            "reclaimable_gc_size": 10,
            "reclaimable_cache_size": 5,
            "reclaimable_temporary_size": 5,
            "sections": [
                {
                    "name": "cache",
                    "path": "cache/",
                    "total_size": 5,
                    "file_count": 1,
                    "reclaimable_size": 5,
                    "reclaim_strategy": "prune-cache",
                    "notes": "Detached cache files.",
                }
            ],
            "recommendations": ["Run gc()."],
        }

    def test_encode_commit_merge_gc_and_squash_reports(self):
        commit = CommitInfo(
            commit_url="file:///tmp/repo#commit=abc",
            commit_message="seed",
            commit_description="body",
            oid="abc",
            _url="file:///tmp/repo#blob=main:demo.txt",
        )
        merge = MergeResult(
            status="conflict",
            target_revision="main",
            source_revision="feature",
            base_commit="base",
            target_head_before="target",
            source_head="source",
            head_after="target",
            commit=None,
            conflicts=[
                MergeConflict(
                    path="demo.txt",
                    conflict_type="modify/modify",
                    message="Both sides changed demo.txt differently.",
                    base_oid="base-oid",
                    target_oid="target-oid",
                    source_oid="source-oid",
                )
            ],
            fast_forward=False,
            created_commit=False,
        )
        gc_report = GcReport(
            dry_run=True,
            checked_refs=["refs/heads/main"],
            reclaimed_size=10,
            reclaimed_object_size=3,
            reclaimed_chunk_size=2,
            reclaimed_cache_size=4,
            reclaimed_temporary_size=1,
            removed_file_count=2,
            notes=["dry-run"],
        )
        squash_report = SquashReport(
            ref_name="refs/heads/main",
            old_head="old",
            new_head="new",
            root_commit_before="root",
            rewritten_commit_count=2,
            dropped_ancestor_count=1,
            blocking_refs=["refs/tags/v1"],
            gc_report=gc_report,
        )

        assert encode_commit_info(commit)["oid"] == "abc"
        assert encode_commit_info(commit)["_url"] == "file:///tmp/repo#blob=main:demo.txt"
        assert encode_merge_result(merge)["conflicts"][0]["conflict_type"] == "modify/modify"
        assert encode_gc_report(gc_report)["reclaimed_cache_size"] == 4
        assert encode_squash_report(squash_report)["gc_report"]["removed_file_count"] == 2
