import hubvault
import pytest


@pytest.mark.unittest
class TestPackageInit:
    def test_all_exports_are_available(self):
        expected = [
            "BlobLfsInfo",
            "BlobSecurityInfo",
            "CommitInfo",
            "CommitOperationAdd",
            "CommitOperationCopy",
            "CommitOperationDelete",
            "ConflictError",
            "EntryNotFoundError",
            "GitCommitInfo",
            "GitRefInfo",
            "GitRefs",
            "GcReport",
            "HubVaultApi",
            "HubVaultError",
            "HubVaultValidationError",
            "IntegrityError",
            "LastCommitInfo",
            "MergeConflict",
            "MergeResult",
            "ReflogEntry",
            "RepoFile",
            "RepoFolder",
            "RepoInfo",
            "RepositoryAlreadyExistsError",
            "RepositoryNotFoundError",
            "RevisionNotFoundError",
            "SquashReport",
            "StorageOverview",
            "StorageSectionInfo",
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
