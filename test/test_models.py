from dataclasses import FrozenInstanceError

import pytest

from hubvault.models import BlobLfsInfo, CommitInfo, PathInfo, RepoInfo, VerifyReport


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

    def test_commit_info_path_info_blob_lfs_and_verify_report(self):
        commit = CommitInfo(
            commit_id="sha256:c1",
            revision="main",
            tree_id="sha256:t1",
            parents=["sha256:p1"],
            message="hello",
        )
        path = PathInfo(
            path="model.bin",
            path_type="file",
            size=3,
            oid="oid",
            blob_id="blob",
            sha256="sha256:abc",
            etag="etag",
        )
        lfs = BlobLfsInfo(size=1024, sha256="sha256:def", pointer_size=128)
        report = VerifyReport(ok=True)

        assert commit.parents == ["sha256:p1"]
        assert path.path_type == "file"
        assert lfs.pointer_size == 128
        assert report.checked_refs == []
        assert report.warnings == []
        assert report.errors == []

