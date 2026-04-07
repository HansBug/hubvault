"""
Public data models for the :mod:`hubvault` package.

This module defines the stable dataclasses returned by the public API. The
models intentionally expose repository-facing metadata without leaking the
layout of internal storage objects.

The module contains:

* :class:`RepoInfo` - Basic information about a local repository
* :class:`CommitInfo` - HF-style commit creation result metadata
* :class:`GitCommitInfo` - HF-style commit listing metadata
* :class:`LastCommitInfo` - Last-commit metadata compatible with HF path listings
* :class:`BlobSecurityInfo` - Security metadata compatible with HF path listings
* :class:`RepoFile` - HF-style file metadata entry
* :class:`RepoFolder` - HF-style folder metadata entry
* :class:`BlobLfsInfo` - Future-facing large-file metadata container
* :class:`VerifyReport` - Result of repository verification
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


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


@dataclass
class CommitInfo(str):
    """
    Describe the result of a commit-creating operation.

    This model intentionally follows the public shape of
    ``huggingface_hub.hf_api.CommitInfo``. It is returned by write-like public
    APIs such as :meth:`hubvault.api.HubVaultApi.create_commit` and
    :meth:`hubvault.api.HubVaultApi.reset_ref`, while
    :class:`GitCommitInfo` remains the public model for history listings.

    :param commit_url: Local commit URL string aligned with HF naming
    :type commit_url: str
    :param commit_message: Commit summary aligned with HF naming
    :type commit_message: str
    :param commit_description: Commit description/body aligned with HF naming
    :type commit_description: str
    :param oid: Commit object ID aligned with HF naming
    :type oid: str
    :param pr_url: Pull-request URL placeholder. Always ``None`` for the local
        repository flow.
    :type pr_url: Optional[str]
    :param _url: Legacy string payload used for HF-style ``str`` compatibility.
        Defaults to ``commit_url``.
    :type _url: Optional[str]

    :ivar repo_url: Local repository URL string aligned with HF naming
    :vartype repo_url: str
    :ivar pr_revision: Pull-request revision placeholder. Always ``None`` for
        the local repository flow.
    :vartype pr_revision: Optional[str]
    :ivar pr_num: Pull-request number placeholder. Always ``None`` for the
        local repository flow.
    :vartype pr_num: Optional[int]

    Example::

        >>> info = CommitInfo(
        ...     commit_url="file:///tmp/repo#commit=sha256:c1",
        ...     commit_message="seed",
        ...     commit_description="body",
        ...     oid="sha256:c1",
        ... )
        >>> info.oid
        'sha256:c1'
    """

    commit_url: str
    commit_message: str
    commit_description: str
    oid: str
    pr_url: Optional[str] = None
    repo_url: str = field(init=False)
    pr_revision: Optional[str] = field(init=False)
    pr_num: Optional[int] = field(init=False)
    _url: Optional[str] = field(repr=False, default=None)

    def __new__(cls, *args, commit_url: str, _url: Optional[str] = None, **kwargs):
        """
        Build the legacy string payload used by HF-style commit info objects.

        :param commit_url: Public commit URL
        :type commit_url: str
        :param _url: Optional legacy URL override
        :type _url: Optional[str]
        :return: String-compatible commit info instance
        :rtype: CommitInfo
        """

        return str.__new__(cls, _url or commit_url)

    def __post_init__(self) -> None:
        """
        Populate computed HF-style attributes after initialization.

        :return: ``None``.
        :rtype: None
        """

        repo_url = self.commit_url.split("#commit=", 1)[0]
        object.__setattr__(self, "repo_url", repo_url)
        object.__setattr__(self, "pr_revision", None)
        object.__setattr__(self, "pr_num", None)
        if self._url is None:
            object.__setattr__(self, "_url", self.commit_url)


@dataclass(frozen=True)
class GitCommitInfo:
    """
    Describe a commit entry returned by :meth:`hubvault.api.HubVaultApi.list_repo_commits`.

    This model follows the main public shape of
    ``huggingface_hub.hf_api.GitCommitInfo`` while staying grounded in the
    local repository semantics of :mod:`hubvault`.

    :param commit_id: Commit object ID
    :type commit_id: str
    :param authors: Authors associated with the commit
    :type authors: List[str]
    :param created_at: Commit creation time in UTC
    :type created_at: datetime.datetime
    :param title: Commit title
    :type title: str
    :param message: Commit body message
    :type message: str
    :param formatted_title: HTML-formatted commit title, or ``None`` when not
        requested
    :type formatted_title: Optional[str]
    :param formatted_message: HTML-formatted commit message, or ``None`` when
        not requested
    :type formatted_message: Optional[str]

    Example::

        >>> info = GitCommitInfo(
        ...     commit_id="sha256:c1",
        ...     authors=[],
        ...     created_at=datetime(2024, 1, 1, 0, 0, 0),
        ...     title="seed",
        ...     message="",
        ...     formatted_title=None,
        ...     formatted_message=None,
        ... )
        >>> info.title
        'seed'
    """

    commit_id: str
    authors: List[str]
    created_at: datetime
    title: str
    message: str
    formatted_title: Optional[str]
    formatted_message: Optional[str]


@dataclass(frozen=True)
class LastCommitInfo:
    """
    Describe last-commit metadata for a repo path.

    :param oid: Commit object ID
    :type oid: str
    :param title: Commit title
    :type title: str
    :param date: Commit creation time in UTC
    :type date: datetime.datetime

    Example::

        >>> info = LastCommitInfo("oid", "seed", datetime(2024, 1, 1, 0, 0, 0))
        >>> info.title
        'seed'
    """

    oid: str
    title: str
    date: datetime


@dataclass(frozen=True)
class BlobSecurityInfo:
    """
    Describe security metadata for a repo file.

    :param safe: Whether the file is considered safe
    :type safe: bool
    :param status: Security scan status string
    :type status: str
    :param av_scan: Antivirus scan metadata, if any
    :type av_scan: Optional[Dict[str, object]]
    :param pickle_import_scan: Pickle-import scan metadata, if any
    :type pickle_import_scan: Optional[Dict[str, object]]

    Example::

        >>> info = BlobSecurityInfo(True, "safe", None, None)
        >>> info.safe
        True
    """

    safe: bool
    status: str
    av_scan: Optional[Dict[str, object]]
    pickle_import_scan: Optional[Dict[str, object]]


@dataclass(frozen=True)
class RepoFile:
    """
    Describe a file entry in HF-style repo listings.

    This model follows the main public field layout of
    ``huggingface_hub.hf_api.RepoFile``. Local-only convenience fields
    ``oid``, ``sha256``, and ``etag`` are retained because the local-path
    design exposes them directly to callers.

    :param path: Repo-relative path
    :type path: str
    :param size: File size in bytes
    :type size: int
    :param blob_id: Git blob OID
    :type blob_id: str
    :param lfs: LFS-style checksum metadata, if available
    :type lfs: Optional[BlobLfsInfo]
    :param last_commit: Last-commit metadata, if available
    :type last_commit: Optional[LastCommitInfo]
    :param security: Security metadata, if available
    :type security: Optional[BlobSecurityInfo]
    :param oid: Local convenience alias for the blob OID
    :type oid: Optional[str]
    :param sha256: Raw hexadecimal SHA-256 digest of the logical file content
    :type sha256: Optional[str]
    :param etag: Public ETag value for download-facing APIs
    :type etag: Optional[str]

    Example::

        >>> info = RepoFile("demo.txt", 4, "oid", None)
        >>> info.blob_id
        'oid'
    """

    path: str
    size: int
    blob_id: str
    lfs: Optional["BlobLfsInfo"] = None
    last_commit: Optional[LastCommitInfo] = None
    security: Optional[BlobSecurityInfo] = None
    oid: Optional[str] = None
    sha256: Optional[str] = None
    etag: Optional[str] = None

    @property
    def rfilename(self) -> str:
        """
        Return the backward-compatible HF filename alias.

        :return: Repo-relative path
        :rtype: str
        """

        return self.path

    @property
    def lastCommit(self) -> Optional[LastCommitInfo]:
        """
        Return the backward-compatible HF camelCase alias.

        :return: Last-commit metadata, if available
        :rtype: Optional[LastCommitInfo]
        """

        return self.last_commit


@dataclass(frozen=True)
class RepoFolder:
    """
    Describe a folder entry in HF-style repo listings.

    :param path: Repo-relative folder path
    :type path: str
    :param tree_id: Tree object ID
    :type tree_id: str
    :param last_commit: Last-commit metadata, if available
    :type last_commit: Optional[LastCommitInfo]

    Example::

        >>> info = RepoFolder("configs", "tree-oid")
        >>> info.tree_id
        'tree-oid'
    """

    path: str
    tree_id: str
    last_commit: Optional[LastCommitInfo] = None

    @property
    def lastCommit(self) -> Optional[LastCommitInfo]:
        """
        Return the backward-compatible HF camelCase alias.

        :return: Last-commit metadata, if available
        :rtype: Optional[LastCommitInfo]
        """

        return self.last_commit

@dataclass(frozen=True)
class BlobLfsInfo:
    """
    Describe large-file metadata for future LFS-compatible modes.

    :param size: Logical file size in bytes
    :type size: int
    :param sha256: Raw hexadecimal SHA-256 digest of the file content, matching
        the public ``huggingface_hub`` ``lfs.sha256`` style without an
        algorithm prefix
    :type sha256: str
    :param pointer_size: Size of the canonical pointer content
    :type pointer_size: int

    Example::

        >>> info = BlobLfsInfo(1024, "abc", 128)
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
