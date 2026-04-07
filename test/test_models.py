from datetime import datetime, timezone
from dataclasses import FrozenInstanceError

import pytest

from hubvault.models import (
    BlobLfsInfo,
    BlobSecurityInfo,
    CommitInfo,
    GitCommitInfo,
    LastCommitInfo,
    RepoFile,
    RepoFolder,
    RepoInfo,
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
        report = VerifyReport(ok=True)

        assert commit.oid == "sha256:c1"
        assert commit.commit_message == "hello"
        assert commit.commit_description == "world"
        assert commit.repo_url == "file:///tmp/repo"
        assert str(commit) == commit.commit_url
        assert git_commit.authors == ["tester"]
        assert lfs.pointer_size == 128
        assert repo_file.rfilename == "model.bin"
        assert repo_file.lastCommit == last_commit
        assert repo_folder.tree_id == "tree"
        assert report.checked_refs == []
        assert report.warnings == []
        assert report.errors == []
