import pytest

from hubvault import CommitOperationAdd, HubVaultApi


@pytest.mark.unittest
class TestRepoBackendPackage:
    def test_repo_backend_split_preserves_public_api_behavior(self, tmp_path):
        api = HubVaultApi(tmp_path / "repo")
        api.create_repo(large_file_threshold=32)
        api.create_commit(
            operations=[CommitOperationAdd("folder/demo.txt", b"hello from backend package")],
            commit_message="seed backend package",
        )

        assert api.list_repo_files() == ["folder/demo.txt"]
        assert api.read_bytes("folder/demo.txt") == b"hello from backend package"
        assert api.quick_verify().ok is True
