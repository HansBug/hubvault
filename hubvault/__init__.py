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
* :class:`CommitInfo` - HF-style commit creation result model
* :class:`GitCommitInfo` - HF-style commit listing model
* :class:`GitRefInfo` - HF-style git reference model
* :class:`GitRefs` - HF-style git reference collection model
* :class:`ReflogEntry` - Local reflog entry model
* :class:`RepoFile` - HF-style file metadata model
* :class:`RepoFolder` - HF-style folder metadata model
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
from .models import (
    BlobLfsInfo,
    BlobSecurityInfo,
    CommitInfo,
    GitCommitInfo,
    GitRefInfo,
    GitRefs,
    LastCommitInfo,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    RepoInfo,
    VerifyReport,
)
from .operations import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete

__all__ = [
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
    "HubVaultApi",
    "HubVaultError",
    "HubVaultValidationError",
    "IntegrityError",
    "LastCommitInfo",
    "LockTimeoutError",
    "ReflogEntry",
    "RepoFile",
    "RepoFolder",
    "RepoInfo",
    "RepositoryAlreadyExistsError",
    "RepositoryNotFoundError",
    "RevisionNotFoundError",
    "UnsupportedPathError",
    "VerificationError",
    "VerifyReport",
]
