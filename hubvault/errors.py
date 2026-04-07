"""
Public exception types for the :mod:`hubvault` package.

This module defines the stable error model exposed by the MVP repository API.
Callers are expected to catch these exceptions instead of depending on
implementation details from the storage backend.

The module contains:

* :class:`HubVaultError` - Base exception for all package-specific errors
* :class:`RepositoryNotFoundError` - Raised when a target repository does not exist
* :class:`RepositoryAlreadyExistsError` - Raised when creating an already existing repository
* :class:`RevisionNotFoundError` - Raised when a branch, tag, or commit cannot be resolved
* :class:`EntryNotFoundError` - Raised when a requested repo path does not exist
* :class:`ConflictError` - Raised when optimistic concurrency checks fail
* :class:`IntegrityError` - Raised when stored data does not match expected integrity checks
* :class:`VerificationError` - Raised when repository verification fails
* :class:`LockTimeoutError` - Raised when a write lock cannot be acquired
* :class:`HubVaultValidationError` - Raised when public inputs fail validation
* :class:`UnsupportedPathError` - Raised when a repo path or ref name is invalid

Example::

    >>> from hubvault.errors import RepositoryNotFoundError
    >>> err = RepositoryNotFoundError("missing")
    >>> str(err)
    'missing'
"""


class HubVaultError(Exception):
    """
    Base exception for all :mod:`hubvault` errors.

    Example::

        >>> err = HubVaultError("boom")
        >>> str(err)
        'boom'
    """


class RepositoryNotFoundError(HubVaultError):
    """
    Raised when a repository root does not contain a valid ``hubvault`` repo.

    Example::

        >>> str(RepositoryNotFoundError("missing"))
        'missing'
    """


class RepositoryAlreadyExistsError(HubVaultError):
    """
    Raised when repository creation targets an existing or non-empty location.

    Example::

        >>> str(RepositoryAlreadyExistsError("exists"))
        'exists'
    """


class RevisionNotFoundError(HubVaultError):
    """
    Raised when a branch, tag, or commit identifier cannot be resolved.

    Example::

        >>> str(RevisionNotFoundError("revision"))
        'revision'
    """


class EntryNotFoundError(HubVaultError):
    """
    Raised when a requested logical repo path does not exist in a revision.

    Example::

        >>> str(EntryNotFoundError("path"))
        'path'
    """


class ConflictError(HubVaultError):
    """
    Raised when optimistic concurrency checks fail during a write operation.

    Example::

        >>> str(ConflictError("conflict"))
        'conflict'
    """


class IntegrityError(HubVaultError):
    """
    Raised when persisted data does not match its recorded integrity metadata.

    Example::

        >>> str(IntegrityError("broken"))
        'broken'
    """


class VerificationError(HubVaultError):
    """
    Raised when a repository fails validation checks.

    Example::

        >>> str(VerificationError("verify"))
        'verify'
    """


class LockTimeoutError(HubVaultError):
    """
    Raised when a write lock cannot be acquired.

    Example::

        >>> str(LockTimeoutError("locked"))
        'locked'
    """


class HubVaultValidationError(HubVaultError, ValueError):
    """
    Raised when a public input fails local repository validation.

    This class is the local-name counterpart to the ``huggingface_hub``
    validation error family while remaining anchored in :mod:`hubvault`.

    Example::

        >>> isinstance(HubVaultValidationError("bad input"), ValueError)
        True
    """


class UnsupportedPathError(HubVaultValidationError):
    """
    Raised when a repo path or ref name violates repository constraints.

    Example::

        >>> str(UnsupportedPathError("bad path"))
        'bad path'
    """
