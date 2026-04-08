import hubvault.repo as repo_module
import pytest


@pytest.mark.unittest
class TestRepoPackageInit:
    def test_repo_package_reexports_public_constants_only(self):
        assert repo_module.DEFAULT_BRANCH == "main"
        assert repo_module.FORMAT_MARKER == "hubvault-repo/v1"
        assert repo_module.FORMAT_VERSION == 1
        assert repo_module.OBJECT_HASH == "sha256"
        assert repo_module.LARGE_FILE_THRESHOLD > 0
        assert repo_module.__all__ == [
            "DEFAULT_BRANCH",
            "FORMAT_MARKER",
            "FORMAT_VERSION",
            "LARGE_FILE_THRESHOLD",
            "OBJECT_HASH",
        ]
