import pytest

from hubvault.errors import (
    ConflictError,
    HubVaultError,
    IntegrityError,
    LockTimeoutError,
    PathNotFoundError,
    RepoAlreadyExistsError,
    RepoNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
    VerificationError,
)


@pytest.mark.unittest
class TestErrors:
    def test_public_error_hierarchy_and_messages(self):
        errors = [
            RepoNotFoundError("repo"),
            RepoAlreadyExistsError("exists"),
            RevisionNotFoundError("revision"),
            PathNotFoundError("path"),
            ConflictError("conflict"),
            IntegrityError("integrity"),
            VerificationError("verify"),
            LockTimeoutError("lock"),
            UnsupportedPathError("path-format"),
        ]

        for err in errors:
            assert isinstance(err, HubVaultError)
            assert str(err)

