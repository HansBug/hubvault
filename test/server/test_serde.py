from datetime import datetime

import pytest

from hubvault.models import BlobLfsInfo, BlobSecurityInfo, LastCommitInfo
from hubvault.server.serde import (
    encode_blob_lfs_info,
    encode_blob_security_info,
    encode_last_commit_info,
    encode_repo_entry,
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

