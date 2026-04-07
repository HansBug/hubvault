"""
Public package exports for :mod:`hubvault`.

This package exposes the MVP local repository API together with its stable
models, operations, and exception types. The implementation is intentionally
embedded and file-based so a repository remains self-contained on disk.

The package contains:

* :class:`HubVaultApi` - Public local repository API
* :class:`CommitOperationAdd` - Add-file commit operation
* :class:`CommitOperationDelete` - Delete-path commit operation
* :class:`CommitOperationCopy` - Copy-path commit operation
* :class:`RepoInfo` - Repository metadata model
* :class:`CommitInfo` - Commit metadata model
* :class:`PathInfo` - Public path metadata model
* :class:`VerifyReport` - Verification result model

Example::

    >>> from hubvault import CommitOperationAdd, HubVaultApi
    >>> api = HubVaultApi("/tmp/demo-repo")
    >>> _ = api.create_repo(exist_ok=True)
    >>> _ = api.create_commit(
    ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
    ...     commit_message="seed",
    ... )
"""

from .api import HubVaultApi
from .errors import (
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
from .models import BlobLfsInfo, CommitInfo, PathInfo, RepoInfo, VerifyReport
from .operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete

__all__ = [
    "BlobLfsInfo",
    "CommitInfo",
    "CommitOperationAdd",
    "CommitOperationCopy",
    "CommitOperationDelete",
    "ConflictError",
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
