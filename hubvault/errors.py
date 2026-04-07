"""
Public exception types for the :mod:`hubvault` package.

This module defines the stable error model exposed by the MVP repository API.
Callers are expected to catch these exceptions instead of depending on
implementation details from the storage backend.

The module contains:

* :class:`HubVaultError` - Base exception for all package-specific errors
* :class:`RepoNotFoundError` - Raised when a target repository does not exist
* :class:`RepoAlreadyExistsError` - Raised when creating an already existing repository
* :class:`RevisionNotFoundError` - Raised when a branch, tag, or commit cannot be resolved
* :class:`PathNotFoundError` - Raised when a requested repo path does not exist
* :class:`ConflictError` - Raised when optimistic concurrency checks fail
* :class:`IntegrityError` - Raised when stored data does not match expected integrity checks
* :class:`VerificationError` - Raised when repository verification fails
* :class:`LockTimeoutError` - Raised when a write lock cannot be acquired
* :class:`UnsupportedPathError` - Raised when a repo path or ref name is invalid
"""


class HubVaultError(Exception):
    """
    Base exception for all :mod:`hubvault` errors.
    """


class RepoNotFoundError(HubVaultError):
    """
    Raised when a repository root does not contain a valid ``hubvault`` repo.
    """


class RepoAlreadyExistsError(HubVaultError):
    """
    Raised when repository creation targets an existing or non-empty location.
    """


class RevisionNotFoundError(HubVaultError):
    """
    Raised when a branch, tag, or commit identifier cannot be resolved.
    """


class PathNotFoundError(HubVaultError):
    """
    Raised when a requested logical repo path does not exist in a revision.
    """


class ConflictError(HubVaultError):
    """
    Raised when optimistic concurrency checks fail during a write operation.
    """


class IntegrityError(HubVaultError):
    """
    Raised when persisted data does not match its recorded integrity metadata.
    """


class VerificationError(HubVaultError):
    """
    Raised when a repository fails validation checks.
    """


class LockTimeoutError(HubVaultError):
    """
    Raised when a write lock cannot be acquired.
    """


class UnsupportedPathError(HubVaultError):
    """
    Raised when a repo path or ref name violates repository constraints.
    """
