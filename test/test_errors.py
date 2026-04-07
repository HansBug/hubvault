import pytest

from hubvault.errors import (
    ConflictError,
    EntryNotFoundError,
    HubVaultError,
    HubVaultValidationError,
    IntegrityError,
    LockTimeoutError,
    RepositoryAlreadyExistsError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
    UnsupportedPathError,
    VerificationError,
)


@pytest.mark.unittest
class TestErrors:
    def test_public_error_hierarchy_and_messages(self):
        errors = [
            RepositoryNotFoundError("repo"),
            RepositoryAlreadyExistsError("exists"),
            RevisionNotFoundError("revision"),
            EntryNotFoundError("path"),
            ConflictError("conflict"),
            IntegrityError("integrity"),
            VerificationError("verify"),
            LockTimeoutError("lock"),
            UnsupportedPathError("path-format"),
        ]

        for err in errors:
            assert isinstance(err, HubVaultError)
            assert str(err)

    def test_validation_error_hierarchy(self):
        assert issubclass(UnsupportedPathError, HubVaultValidationError)
        assert issubclass(HubVaultValidationError, ValueError)
