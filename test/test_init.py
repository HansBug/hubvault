import hubvault
import pytest


@pytest.mark.unittest
class TestPackageInit:
    def test_all_exports_are_available(self):
        expected = [
            "BlobLfsInfo",
            "CommitInfo",
            "CommitOperationAdd",
            "CommitOperationCopy",
            "CommitOperationDelete",
            "ConflictError",
            "GitCommitInfo",
            "HubVaultApi",
            "HubVaultError",
            "IntegrityError",
            "LockTimeoutError",
            "PathInfo",
            "PathNotFoundError",
            "RepoAlreadyExistsError",
            "RepoInfo",
            "RepoNotFoundError",
            "RevisionNotFoundError",
            "UnsupportedPathError",
            "VerificationError",
            "VerifyReport",
        ]

        assert hubvault.__all__ == expected
        for name in expected:
            assert getattr(hubvault, name) is not None

    def test_public_api_can_be_constructed_from_package_root(self, tmp_path):
        api = hubvault.HubVaultApi(tmp_path / "repo")

        assert isinstance(api, hubvault.HubVaultApi)
