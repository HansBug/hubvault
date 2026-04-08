import pytest

from hubvault.repo.constants import (
    DEFAULT_BRANCH,
    FORMAT_MARKER,
    FORMAT_VERSION,
    LARGE_FILE_THRESHOLD,
    OBJECT_HASH,
    REPO_LOCK_FILENAME,
)


@pytest.mark.unittest
class TestRepoConstants:
    def test_repo_constants_match_expected_public_values(self):
        assert FORMAT_MARKER == "hubvault-repo/v1"
        assert FORMAT_VERSION == 1
        assert DEFAULT_BRANCH == "main"
        assert OBJECT_HASH == "sha256"
        assert LARGE_FILE_THRESHOLD == 16 * 1024 * 1024
        assert REPO_LOCK_FILENAME == "repo.lock"
