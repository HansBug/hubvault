"""
Public data models for the :mod:`hubvault` package.

This module defines the stable dataclasses returned by the public API. The
models intentionally expose repository-facing metadata without leaking the
layout of internal storage objects.

The module contains:

* :class:`RepoInfo` - Basic information about a local repository
* :class:`CommitInfo` - Metadata for an immutable commit snapshot
* :class:`PathInfo` - Public file or directory metadata within a revision
* :class:`BlobLfsInfo` - Future-facing large-file metadata container
* :class:`VerifyReport` - Result of repository verification
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class RepoInfo:
    """
    Describe the current state of a local repository.

    :param repo_path: Filesystem path to the repository root
    :type repo_path: str
    :param format_version: Repository format version
    :type format_version: int
    :param default_branch: Name of the default branch
    :type default_branch: str
    :param head: Resolved head commit ID for the selected revision, or ``None``
        when the revision has no commit yet
    :type head: Optional[str]
    :param refs: Visible refs in the repository
    :type refs: List[str]

    Example::

        >>> info = RepoInfo("/tmp/repo", 1, "main", None)
        >>> info.default_branch
        'main'
    """

    repo_path: str
    format_version: int
    default_branch: str
    head: Optional[str]
    refs: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommitInfo:
    """
    Describe an immutable commit snapshot.

    :param commit_id: Commit object ID
    :type commit_id: str
    :param revision: Revision name used to resolve or create the commit
    :type revision: str
    :param tree_id: Root tree object ID for the snapshot
    :type tree_id: str
    :param parents: Parent commit IDs
    :type parents: List[str]
    :param message: Commit message
    :type message: str

    Example::

        >>> info = CommitInfo("sha256:c1", "main", "sha256:t1")
        >>> info.revision
        'main'
    """

    commit_id: str
    revision: str
    tree_id: str
    parents: List[str] = field(default_factory=list)
    message: str = ""


@dataclass(frozen=True)
class PathInfo:
    """
    Describe a public path inside a repository revision.

    :param path: Repo-relative POSIX path
    :type path: str
    :param path_type: Path type, usually ``"file"`` or ``"directory"``
    :type path_type: str
    :param size: Logical file size in bytes, or ``0`` for directories
    :type size: int
    :param oid: Public file OID compatible with Hugging Face style metadata
    :type oid: Optional[str]
    :param blob_id: Public blob identifier. For the MVP whole-file mode this is
        the same value as :attr:`oid`
    :type blob_id: Optional[str]
    :param sha256: SHA-256 digest of the logical file content
    :type sha256: Optional[str]
    :param etag: Public ETag value for download-facing APIs
    :type etag: Optional[str]

    Example::

        >>> info = PathInfo("demo.txt", "file", 4, "oid", "blob", "sha256:abc", "etag")
        >>> info.path
        'demo.txt'
    """

    path: str
    path_type: str
    size: int
    oid: Optional[str]
    blob_id: Optional[str]
    sha256: Optional[str]
    etag: Optional[str]


@dataclass(frozen=True)
class BlobLfsInfo:
    """
    Describe large-file metadata for future LFS-compatible modes.

    :param size: Logical file size in bytes
    :type size: int
    :param sha256: SHA-256 digest of the file content
    :type sha256: str
    :param pointer_size: Size of the canonical pointer content
    :type pointer_size: int

    Example::

        >>> info = BlobLfsInfo(1024, "sha256:abc", 128)
        >>> info.pointer_size
        128
    """

    size: int
    sha256: str
    pointer_size: int


@dataclass(frozen=True)
class VerifyReport:
    """
    Report the result of repository verification.

    :param ok: Whether verification completed without errors
    :type ok: bool
    :param checked_refs: Refs inspected during verification
    :type checked_refs: List[str]
    :param warnings: Non-fatal diagnostics
    :type warnings: List[str]
    :param errors: Fatal verification errors
    :type errors: List[str]

    Example::

        >>> report = VerifyReport(True)
        >>> report.ok
        True
    """

    ok: bool
    checked_refs: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
