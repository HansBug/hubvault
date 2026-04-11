from datetime import datetime

import pytest

from hubvault.models import BlobLfsInfo, BlobSecurityInfo, LastCommitInfo, StorageOverview, StorageSectionInfo, VerifyReport
from hubvault.server.serde import (
    encode_blob_lfs_info,
    encode_blob_security_info,
    encode_last_commit_info,
    encode_repo_entry,
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
