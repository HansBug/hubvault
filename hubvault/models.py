"""
Public data models for the :mod:`hubvault` package.

This module defines the stable dataclasses returned by the public API. The
models intentionally expose repository-facing metadata without leaking the
layout of internal storage objects.

The module contains:

* :class:`RepoInfo` - Basic information about a local repository
* :class:`CommitInfo` - HF-style commit creation result metadata
* :class:`MergeConflict` - Structured merge-conflict description
* :class:`MergeResult` - Result of a branch merge attempt
* :class:`GitCommitInfo` - HF-style commit listing metadata
* :class:`GitRefInfo` - HF-style git reference metadata
* :class:`GitRefs` - HF-style git reference collection
* :class:`ReflogEntry` - Local reflog entry metadata
* :class:`LastCommitInfo` - Last-commit metadata compatible with HF path listings
* :class:`BlobSecurityInfo` - Security metadata compatible with HF path listings
* :class:`RepoFile` - HF-style file metadata entry
* :class:`RepoFolder` - HF-style folder metadata entry
* :class:`BlobLfsInfo` - Future-facing large-file metadata container
* :class:`VerifyReport` - Result of repository verification
* :class:`StorageSectionInfo` - Disk-usage breakdown entry for one storage section
* :class:`StorageOverview` - Repository-wide storage analysis and reclaim guidance
* :class:`GcReport` - Result of a storage reclamation pass
* :class:`SquashReport` - Result of a history-squash maintenance operation
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
        only for malformed or recovery-era empty refs
    :type head: Optional[str]
    :param refs: Visible refs in the repository
    :type refs: List[str]

    Example::

        >>> info = RepoInfo("/tmp/repo", 1, "main", "sha256:c1")
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
    :vartype pr_num: Optional[str]

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
    pr_num: Optional[str] = field(init=False)
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
class MergeConflict:
    """
    Describe one structured conflict detected during a merge attempt.

    :param path: Primary repo-relative path involved in the conflict
    :type path: str
    :param conflict_type: Stable conflict kind such as ``"modify/modify"``,
        ``"add/add"``, ``"delete/modify"``, ``"file/directory"``, or
        ``"case-fold"``
    :type conflict_type: str
    :param message: Human-readable conflict summary
    :type message: str
    :param base_oid: Base-side logical file OID, if a file version exists
    :type base_oid: Optional[str]
    :param target_oid: Target-branch logical file OID, if a file version exists
    :type target_oid: Optional[str]
    :param source_oid: Source-side logical file OID, if a file version exists
    :type source_oid: Optional[str]
    :param related_path: Secondary repo-relative path for structural conflicts,
        or ``None`` when the conflict concerns only ``path``
    :type related_path: Optional[str]

    Example::

        >>> conflict = MergeConflict(
        ...     path="demo.txt",
        ...     conflict_type="modify/modify",
        ...     message="Both sides changed demo.txt differently.",
        ...     base_oid="abc",
        ...     target_oid="def",
        ...     source_oid="ghi",
        ... )
        >>> conflict.conflict_type
        'modify/modify'
    """

    path: str
    conflict_type: str
    message: str
    base_oid: Optional[str]
    target_oid: Optional[str]
    source_oid: Optional[str]
    related_path: Optional[str] = None


@dataclass(frozen=True)
class MergeResult:
    """
    Describe the result of a public branch merge operation.

    :param status: Stable merge status string. Current values are
        ``"merged"``, ``"fast-forward"``, ``"already-up-to-date"``, and
        ``"conflict"``
    :type status: str
    :param target_revision: Target branch that received or would receive the merge
    :type target_revision: str
    :param source_revision: Source revision requested by the caller
    :type source_revision: str
    :param base_commit: Resolved merge base commit, or ``None`` when no common
        ancestor exists
    :type base_commit: Optional[str]
    :param target_head_before: Target branch head before the merge attempt
    :type target_head_before: Optional[str]
    :param source_head: Resolved source commit
    :type source_head: Optional[str]
    :param head_after: Target branch head after the merge attempt
    :type head_after: Optional[str]
    :param commit: Commit metadata for the resulting head when the merge did
        not conflict, or ``None`` for conflict results
    :type commit: Optional[CommitInfo]
    :param conflicts: Structured conflicts detected during the merge attempt
    :type conflicts: List[MergeConflict]
    :param fast_forward: Whether the merge resolved as a fast-forward ref move
    :type fast_forward: bool
    :param created_commit: Whether the merge created a brand-new merge commit
    :type created_commit: bool

    Example::

        >>> commit = CommitInfo(
        ...     commit_url="file:///tmp/repo#commit=sha256:c1",
        ...     commit_message="seed",
        ...     commit_description="",
        ...     oid="sha256:c1",
        ... )
        >>> result = MergeResult(
        ...     status="fast-forward",
        ...     target_revision="main",
        ...     source_revision="feature",
        ...     base_commit="sha256:b0",
        ...     target_head_before="sha256:b0",
        ...     source_head="sha256:c1",
        ...     head_after="sha256:c1",
        ...     commit=commit,
        ...     conflicts=[],
        ...     fast_forward=True,
        ...     created_commit=False,
        ... )
        >>> result.fast_forward
        True
    """

    status: str
    target_revision: str
    source_revision: str
    base_commit: Optional[str]
    target_head_before: Optional[str]
    source_head: Optional[str]
    head_after: Optional[str]
    commit: Optional[CommitInfo]
    conflicts: List[MergeConflict] = field(default_factory=list)
    fast_forward: bool = False
    created_commit: bool = False


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
class GitRefInfo:
    """
    Describe a git reference in HF-style form.

    This model follows the public role of
    ``huggingface_hub.hf_api.GitRefInfo``. Normal repositories now create an
    initial empty-tree commit during :meth:`hubvault.api.HubVaultApi.create_repo`,
    but ``target_commit`` remains optional so recovery tooling can still report
    malformed or legacy empty refs.

    :param name: Short branch or tag name
    :type name: str
    :param ref: Full ref name such as ``refs/heads/main``
    :type ref: str
    :param target_commit: Target commit ID, or ``None`` for a malformed or
        legacy empty local ref
    :type target_commit: Optional[str]

    Example::

        >>> info = GitRefInfo("main", "refs/heads/main", "sha256:c1")
        >>> info.ref
        'refs/heads/main'
    """

    name: str
    ref: str
    target_commit: Optional[str]


@dataclass(frozen=True)
class GitRefs:
    """
    Describe the visible git references for a repository.

    This model follows the public role of ``huggingface_hub.hf_api.GitRefs``.
    The local repository does not support convert refs or pull requests, but
    keeps the same top-level structure for compatibility.

    :param branches: Visible branch references
    :type branches: List[GitRefInfo]
    :param converts: Convert refs. Always empty for the local repository.
    :type converts: List[GitRefInfo]
    :param tags: Visible tag references
    :type tags: List[GitRefInfo]
    :param pull_requests: Pull-request refs when explicitly requested. The
        local repository returns ``[]`` if requested and ``None`` otherwise.
    :type pull_requests: Optional[List[GitRefInfo]]

    Example::

        >>> refs = GitRefs(branches=[], converts=[], tags=[], pull_requests=None)
        >>> refs.tags
        []
    """

    branches: List[GitRefInfo]
    converts: List[GitRefInfo]
    tags: List[GitRefInfo]
    pull_requests: Optional[List[GitRefInfo]] = None


@dataclass(frozen=True)
class ReflogEntry:
    """
    Describe a single reflog record for a branch or tag.

    :param timestamp: UTC time recorded for the reflog entry
    :type timestamp: datetime.datetime
    :param ref_name: Full ref name such as ``refs/heads/main``
    :type ref_name: str
    :param old_head: Previous target commit, if any
    :type old_head: Optional[str]
    :param new_head: New target commit, if any
    :type new_head: Optional[str]
    :param message: Short reflog message
    :type message: str
    :param checksum: Integrity checksum for the reflog record
    :type checksum: str

    Example::

        >>> entry = ReflogEntry(datetime(2024, 1, 1), "refs/heads/main", None, "sha256:c1", "seed", "sha256:x")
        >>> entry.message
        'seed'
    """

    timestamp: datetime
    ref_name: str
    old_head: Optional[str]
    new_head: Optional[str]
    message: str
    checksum: str


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


@dataclass(frozen=True)
class StorageSectionInfo:
    """
    Describe disk usage for one repository storage section.

    :param name: Stable section name such as ``"objects.blobs.data"``
    :type name: str
    :param path: Repo-relative path or descriptive label for the section
    :type path: str
    :param total_size: Current bytes occupied by the section
    :type total_size: int
    :param file_count: Number of files currently present in the section
    :type file_count: int
    :param reclaimable_size: Bytes that can be safely reclaimed now through the
        recommended action
    :type reclaimable_size: int
    :param reclaim_strategy: Recommended safe action such as ``"gc"``,
        ``"prune-cache"``, ``"keep"``, or ``"manual-review"``
    :type reclaim_strategy: str
    :param notes: Practical explanation of what the section stores and how to
        release its space safely
    :type notes: str

    Example::

        >>> section = StorageSectionInfo(
        ...     name="cache",
        ...     path="cache/",
        ...     total_size=1024,
        ...     file_count=3,
        ...     reclaimable_size=1024,
        ...     reclaim_strategy="prune-cache",
        ...     notes="Detached views can be rebuilt.",
        ... )
        >>> section.reclaim_strategy
        'prune-cache'
    """

    name: str
    path: str
    total_size: int
    file_count: int
    reclaimable_size: int
    reclaim_strategy: str
    notes: str


@dataclass(frozen=True)
class StorageOverview:
    """
    Describe repository-wide storage usage and safe reclamation options.

    :param total_size: Total bytes currently occupied by the repository root
    :type total_size: int
    :param reachable_size: Bytes currently required to preserve all live refs
        and their reachable storage after a normal GC pass
    :type reachable_size: int
    :param historical_retained_size: Bytes currently kept only for rollback or
        historical retention and therefore releasable after explicit history
        rewriting such as :meth:`hubvault.api.HubVaultApi.squash_history`
    :type historical_retained_size: int
    :param reclaimable_gc_size: Bytes that :meth:`hubvault.api.HubVaultApi.gc`
        can safely reclaim immediately without rewriting history
    :type reclaimable_gc_size: int
    :param reclaimable_cache_size: Bytes in rebuildable detached caches
    :type reclaimable_cache_size: int
    :param reclaimable_temporary_size: Bytes in temporary or quarantine areas
        that can be cleaned without changing visible repository history
    :type reclaimable_temporary_size: int
    :param sections: Per-section usage breakdown
    :type sections: List[StorageSectionInfo]
    :param recommendations: Ordered safe-action recommendations for operators
    :type recommendations: List[str]

    Example::

        >>> overview = StorageOverview(
        ...     total_size=4096,
        ...     reachable_size=2048,
        ...     historical_retained_size=1024,
        ...     reclaimable_gc_size=256,
        ...     reclaimable_cache_size=512,
        ...     reclaimable_temporary_size=256,
        ...     sections=[],
        ...     recommendations=["Run gc()."],
        ... )
        >>> overview.reclaimable_gc_size
        256
    """

    total_size: int
    reachable_size: int
    historical_retained_size: int
    reclaimable_gc_size: int
    reclaimable_cache_size: int
    reclaimable_temporary_size: int
    sections: List[StorageSectionInfo] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GcReport:
    """
    Describe the result of one storage reclamation pass.

    :param dry_run: Whether the operation only computed the result without
        mutating repository storage
    :type dry_run: bool
    :param checked_refs: Refs treated as GC roots during the pass
    :type checked_refs: List[str]
    :param reclaimed_size: Total bytes reclaimed or reclaimable in dry-run mode
    :type reclaimed_size: int
    :param reclaimed_object_size: Bytes reclaimed from JSON/blob object stores
    :type reclaimed_object_size: int
    :param reclaimed_chunk_size: Bytes reclaimed from pack/index storage
    :type reclaimed_chunk_size: int
    :param reclaimed_cache_size: Bytes reclaimed from rebuildable cache areas
    :type reclaimed_cache_size: int
    :param reclaimed_temporary_size: Bytes reclaimed from quarantine or other
        temporary maintenance areas
    :type reclaimed_temporary_size: int
    :param removed_file_count: Number of files deleted or deletable in dry-run
        mode
    :type removed_file_count: int
    :param notes: Additional human-readable notes about blockers or actions
    :type notes: List[str]

    Example::

        >>> report = GcReport(
        ...     dry_run=True,
        ...     checked_refs=["refs/heads/main"],
        ...     reclaimed_size=1024,
        ...     reclaimed_object_size=512,
        ...     reclaimed_chunk_size=256,
        ...     reclaimed_cache_size=128,
        ...     reclaimed_temporary_size=128,
        ...     removed_file_count=4,
        ...     notes=["dry-run"],
        ... )
        >>> report.dry_run
        True
    """

    dry_run: bool
    checked_refs: List[str]
    reclaimed_size: int
    reclaimed_object_size: int
    reclaimed_chunk_size: int
    reclaimed_cache_size: int
    reclaimed_temporary_size: int
    removed_file_count: int
    notes: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SquashReport:
    """
    Describe the result of a history-squash operation.

    :param ref_name: Full ref name updated by the squash operation
    :type ref_name: str
    :param old_head: Previous ref target before the rewrite
    :type old_head: str
    :param new_head: New ref target after the rewrite
    :type new_head: str
    :param root_commit_before: Commit selected as the oldest preserved commit
        before rewriting, or the previous head when the whole branch history
        was collapsed into one new root commit
    :type root_commit_before: str
    :param rewritten_commit_count: Number of commits rewritten onto the new
        synthetic history chain
    :type rewritten_commit_count: int
    :param dropped_ancestor_count: Number of older ancestor commits made
        unreachable from the rewritten ref
    :type dropped_ancestor_count: int
    :param blocking_refs: Other refs whose retained history still points into
        the pre-squash lineage and may therefore limit immediate reclamation
    :type blocking_refs: List[str]
    :param gc_report: Optional GC result when the squash operation also ran a
        reclamation pass
    :type gc_report: Optional[GcReport]

    Example::

        >>> report = SquashReport(
        ...     ref_name="refs/heads/main",
        ...     old_head="sha256:old",
        ...     new_head="sha256:new",
        ...     root_commit_before="sha256:root",
        ...     rewritten_commit_count=2,
        ...     dropped_ancestor_count=3,
        ...     blocking_refs=[],
        ...     gc_report=None,
        ... )
        >>> report.new_head
        'sha256:new'
    """

    ref_name: str
    old_head: str
    new_head: str
    root_commit_before: str
    rewritten_commit_count: int
    dropped_ancestor_count: int
    blocking_refs: List[str] = field(default_factory=list)
    gc_report: Optional[GcReport] = None
