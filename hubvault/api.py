"""
Public repository API for the :mod:`hubvault` package.

This module exposes :class:`HubVaultApi`, a local embedded repository interface
with method names intentionally aligned with the broad calling style of
``huggingface_hub`` where it makes sense for an on-disk repository.

The module contains:

* :class:`HubVaultApi` - Public entry point for local embedded repositories

Example::

    >>> import tempfile
    >>> from pathlib import Path
    >>> from hubvault import CommitOperationAdd, HubVaultApi
    >>> with tempfile.TemporaryDirectory() as tmpdir:
    ...     repo_dir = Path(tmpdir) / "repo"
    ...     api = HubVaultApi(repo_dir)
    ...     _ = api.create_repo()
    ...     _ = api.create_commit(
    ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
    ...         commit_message="seed",
    ...     )
    ...     api.read_bytes("demo.txt")
    b'hello'
"""

from os import PathLike
from pathlib import Path
from typing import BinaryIO, List, Optional, Sequence, Union

from .models import (
    CommitInfo,
    GcReport,
    GitCommitInfo,
    GitRefs,
    ReflogEntry,
    RepoFile,
    RepoFolder,
    RepoInfo,
    SquashReport,
    StorageOverview,
    VerifyReport,
)
from .repo import LARGE_FILE_THRESHOLD
from .repo.backend import RepositoryBackend


class HubVaultApi:
    """
    Public entry point for a local ``hubvault`` repository.

    :param repo_path: Filesystem path to the local repository root
    :type repo_path: Union[str, os.PathLike[str]]
    :param revision: Default revision used by read APIs
    :type revision: str

    Example::

        >>> import tempfile
        >>> from pathlib import Path
        >>> from hubvault import CommitOperationAdd, HubVaultApi
        >>> with tempfile.TemporaryDirectory() as tmpdir:
        ...     api = HubVaultApi(Path(tmpdir) / "repo")
        ...     _ = api.create_repo()
        ...     _ = api.create_commit(
        ...         revision="main",
        ...         operations=[
        ...             CommitOperationAdd("example.txt", b"hello"),
        ...         ],
        ...         commit_message="add example",
        ...     )
        ...     api.list_repo_files()
        ['example.txt']
    """

    def __init__(self, repo_path: Union[str, PathLike], revision: str = "main") -> None:
        """
        Initialize the public API wrapper.

        :param repo_path: Filesystem path to the local repository root
        :type repo_path: Union[str, os.PathLike[str]]
        :param revision: Default revision used by read APIs, defaults to ``"main"``
        :type revision: str, optional
        :return: ``None``.
        :rtype: None

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo", revision="main")
            ...     api.create_repo().default_branch
            'main'
        """

        self._repo_path = Path(repo_path)
        self._default_revision = revision
        self._backend = RepositoryBackend(self._repo_path)

    def create_repo(
        self,
        *,
        default_branch: str = "main",
        exist_ok: bool = False,
        large_file_threshold: int = LARGE_FILE_THRESHOLD,
    ) -> RepoInfo:
        """
        Create a local repository.

        :param default_branch: Default branch name, defaults to ``"main"``
        :type default_branch: str
        :param exist_ok: Whether an existing repository may be reused
        :type exist_ok: bool
        :param large_file_threshold: File size threshold in bytes at or above
            which newly added files switch to chunked storage, defaults to
            :data:`hubvault.repo.LARGE_FILE_THRESHOLD`
        :type large_file_threshold: int
        :return: Information about the created repository
        :rtype: RepoInfo
        :raises hubvault.errors.RepositoryAlreadyExistsError: Raised when the target
            path already contains a repository or non-empty directory.
        :raises hubvault.errors.UnsupportedPathError: Raised when the default
            branch name is invalid.
        :raises ValueError: Raised when ``large_file_threshold`` is not
            positive.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     info = api.create_repo(default_branch="main")
            ...     (info.default_branch, info.head is None)
            ('main', True)
        """

        return self._backend.create_repo(
            default_branch=default_branch,
            exist_ok=exist_ok,
            large_file_threshold=large_file_threshold,
        )

    def repo_info(self, *, revision: Optional[str] = None) -> RepoInfo:
        """
        Return metadata about the repository.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Repository metadata
        :rtype: RepoInfo
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     commit = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     api.repo_info().head == commit.oid
            True
        """

        return self._backend.repo_info(revision=revision or self._default_revision)

    def create_commit(
        self,
        operations: Sequence[object] = (),
        *,
        commit_message: str,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Create a new commit on a branch.

        :param operations: Commit operations to apply
        :type operations: Sequence[object]
        :param commit_message: Commit summary/title. When
            ``commit_description`` is omitted, embedded body text after a blank
            line is preserved and split the same way Git and HF commit listings
            interpret commit text.
        :type commit_message: str
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param revision: Target branch name, defaults to the API default revision
        :type revision: Optional[str]
        :param parent_commit: Expected parent commit for optimistic concurrency.
            When omitted, the commit is applied against the current branch head.
        :type parent_commit: Optional[str]
        :return: Metadata for the created commit
        :rtype: CommitInfo
        :raises hubvault.errors.ConflictError: Raised when the operation set is
            empty, unsupported, or optimistic concurrency checks fail.
        :raises hubvault.errors.EntryNotFoundError: Raised when delete/copy
            operations refer to missing paths.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the target
            revision cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when revision or
            path inputs are invalid.
        :raises ValueError: Raised when ``commit_message`` is empty.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     commit = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     (commit.commit_message, api.read_bytes("demo.txt"))
            ('seed', b'hello')
        """

        return self._backend.create_commit(
            operations=operations,
            commit_message=commit_message,
            commit_description=commit_description,
            revision=revision or self._default_revision,
            parent_commit=parent_commit,
        )

    def get_paths_info(
        self,
        paths: Union[Sequence[str], str],
        *,
        revision: Optional[str] = None,
    ) -> List[Union[RepoFile, RepoFolder]]:
        """
        Return public metadata for selected paths.

        :param paths: Repo-relative path or paths to inspect
        :type paths: Union[Sequence[str], str]
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Metadata for the existing requested paths
        :rtype: List[Union[RepoFile, RepoFolder]]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when a requested
            path is invalid.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[
            ...             CommitOperationAdd("demo.txt", b"hello"),
            ...             CommitOperationAdd("nested/config.json", b"{}"),
            ...         ],
            ...         commit_message="seed",
            ...     )
            ...     sorted(item.path for item in api.get_paths_info(["demo.txt", "nested", "missing.txt"]))
            ['demo.txt', 'nested']
        """

        return self._backend.get_paths_info(paths=paths, revision=revision or self._default_revision)

    def list_repo_tree(
        self,
        path_in_repo: Optional[str] = None,
        *,
        recursive: bool = False,
        revision: Optional[str] = None,
    ) -> List[Union[RepoFile, RepoFolder]]:
        """
        List direct children under a repository directory.

        :param path_in_repo: Repo-relative directory path, defaults to the root
        :type path_in_repo: Optional[str]
        :param recursive: Whether to include descendant entries recursively
        :type recursive: bool, optional
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Direct child path metadata
        :rtype: List[Union[RepoFile, RepoFolder]]
        :raises hubvault.errors.EntryNotFoundError: Raised when the directory is
            missing from the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when
            ``path_in_repo`` refers to a file or is invalid.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[
            ...             CommitOperationAdd("demo.txt", b"hello"),
            ...             CommitOperationAdd("nested/config.json", b"{}"),
            ...         ],
            ...         commit_message="seed",
            ...     )
            ...     [item.path for item in api.list_repo_tree()]
            ['demo.txt', 'nested']
        """

        return self._backend.list_repo_tree(
            path_in_repo=path_in_repo,
            recursive=recursive,
            revision=revision or self._default_revision,
        )

    def list_repo_files(self, *, revision: Optional[str] = None) -> Sequence[str]:
        """
        List all file paths in a revision.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Sorted repo-relative file paths
        :rtype: Sequence[str]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[
            ...             CommitOperationAdd("demo.txt", b"hello"),
            ...             CommitOperationAdd("nested/config.json", b"{}"),
            ...         ],
            ...         commit_message="seed",
            ...     )
            ...     api.list_repo_files()
            ['demo.txt', 'nested/config.json']
        """

        return self._backend.list_repo_files(revision=revision or self._default_revision)

    def list_repo_commits(
        self,
        *,
        revision: Optional[str] = None,
        formatted: bool = False,
    ) -> Sequence[GitCommitInfo]:
        """
        List commits reachable from a revision in HF-style order.

        The local repository keeps the public method name and the meaningful
        parameters from ``huggingface_hub.HfApi.list_repo_commits`` while
        intentionally dropping remote-only parameters such as ``repo_id``,
        ``repo_type``, and ``token``.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :param formatted: Whether HTML-formatted title/message fields should be
            populated
        :type formatted: bool, optional
        :return: Commit entries ordered from newest to oldest
        :rtype: Sequence[GitCommitInfo]
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed\\n\\nbody",
            ...     )
            ...     [(item.title, item.message) for item in api.list_repo_commits()]
            [('seed', 'body')]
        """

        return self._backend.list_repo_commits(
            revision=revision or self._default_revision,
            formatted=formatted,
        )

    def list_repo_refs(self, *, include_pull_requests: bool = False) -> GitRefs:
        """
        List visible branch and tag refs in HF-style form.

        :param include_pull_requests: Whether pull-request refs should be
            included. The local repository returns ``[]`` when requested and
            ``None`` otherwise.
        :type include_pull_requests: bool, optional
        :return: Visible repository refs
        :rtype: GitRefs
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     api.create_branch(branch="dev")
            ...     api.create_tag(tag="v1")
            ...     refs = api.list_repo_refs()
            ...     ([ref.name for ref in refs.branches], [ref.name for ref in refs.tags])
            (['dev', 'main'], ['v1'])
        """

        return self._backend.list_repo_refs(include_pull_requests=include_pull_requests)

    def create_branch(
        self,
        *,
        branch: str,
        revision: Optional[str] = None,
        exist_ok: bool = False,
    ) -> None:
        """
        Create a branch from an existing revision.

        :param branch: Branch name to create
        :type branch: str
        :param revision: Starting revision, defaults to the API default revision
        :type revision: Optional[str]
        :param exist_ok: Whether an existing branch may be reused
        :type exist_ok: bool, optional
        :return: ``None``.
        :rtype: None
        :raises hubvault.errors.ConflictError: Raised when the branch already
            exists and ``exist_ok`` is ``False``.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when ``branch`` is
            invalid.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     api.create_branch(branch="dev")
            ...     [ref.name for ref in api.list_repo_refs().branches]
            ['dev', 'main']
        """

        self._backend.create_branch(
            branch=branch,
            revision=revision or self._default_revision,
            exist_ok=exist_ok,
        )

    def delete_branch(self, *, branch: str) -> None:
        """
        Delete a branch from the repository.

        :param branch: Branch name to delete
        :type branch: str
        :return: ``None``.
        :rtype: None
        :raises hubvault.errors.ConflictError: Raised when attempting to delete
            the default branch.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the branch
            does not exist.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     api.create_branch(branch="dev")
            ...     api.delete_branch(branch="dev")
            ...     [ref.name for ref in api.list_repo_refs().branches]
            ['main']
        """

        self._backend.delete_branch(branch=branch)

    def create_tag(
        self,
        *,
        tag: str,
        tag_message: Optional[str] = None,
        revision: Optional[str] = None,
        exist_ok: bool = False,
    ) -> None:
        """
        Create a lightweight tag from an existing revision.

        :param tag: Tag name to create
        :type tag: str
        :param tag_message: Optional tag message recorded in the reflog
        :type tag_message: Optional[str]
        :param revision: Starting revision, defaults to the API default revision
        :type revision: Optional[str]
        :param exist_ok: Whether an existing tag may be reused
        :type exist_ok: bool, optional
        :return: ``None``.
        :rtype: None
        :raises hubvault.errors.ConflictError: Raised when the tag already
            exists and ``exist_ok`` is ``False``.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision cannot be resolved to a commit.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     api.create_tag(tag="v1")
            ...     [ref.name for ref in api.list_repo_refs().tags]
            ['v1']
        """

        self._backend.create_tag(
            tag=tag,
            tag_message=tag_message,
            revision=revision or self._default_revision,
            exist_ok=exist_ok,
        )

    def delete_tag(self, *, tag: str) -> None:
        """
        Delete a tag from the repository.

        :param tag: Tag name to delete
        :type tag: str
        :return: ``None``.
        :rtype: None
        :raises hubvault.errors.RevisionNotFoundError: Raised when the tag does
            not exist.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     api.create_tag(tag="v1")
            ...     api.delete_tag(tag="v1")
            ...     api.list_repo_refs().tags
            []
        """

        self._backend.delete_tag(tag=tag)

    def list_repo_reflog(
        self,
        ref_name: str,
        *,
        limit: Optional[int] = None,
    ) -> Sequence[ReflogEntry]:
        """
        List reflog entries for a branch or tag.

        This is a local repository extension intended for audit and recovery
        workflows.

        :param ref_name: Full ref name or an unambiguous short ref name
        :type ref_name: str
        :param limit: Optional maximum number of newest entries to return
        :type limit: Optional[int]
        :return: Reflog entries ordered from newest to oldest
        :rtype: Sequence[ReflogEntry]
        :raises hubvault.errors.ConflictError: Raised when a short ref name is
            ambiguous across branches and tags.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the ref or
            reflog does not exist.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     [entry.message for entry in api.list_repo_reflog("main")]
            ['seed']
        """

        return self._backend.list_repo_reflog(ref_name=ref_name, limit=limit)

    def open_file(self, path_in_repo: str, *, revision: Optional[str] = None) -> BinaryIO:
        """
        Open a file as a read-only binary stream.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Read-only binary stream
        :rtype: BinaryIO
        :raises hubvault.errors.EntryNotFoundError: Raised when the file is not
            present in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     with api.open_file("demo.txt") as fileobj:
            ...         fileobj.read()
            b'hello'
        """

        return self._backend.open_file(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def read_bytes(self, path_in_repo: str, *, revision: Optional[str] = None) -> bytes:
        """
        Read the full content of a file.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: File content bytes
        :rtype: bytes
        :raises hubvault.errors.IntegrityError: Raised when stored blob content
            fails validation checks.
        :raises hubvault.errors.EntryNotFoundError: Raised when the file is not
            present in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     api.read_bytes("demo.txt")
            b'hello'
        """

        return self._backend.read_bytes(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def read_range(
        self,
        path_in_repo: str,
        *,
        start: int,
        length: int,
        revision: Optional[str] = None,
    ) -> bytes:
        """
        Read a byte range from a file.

        For whole-blob files the local backend slices the materialized file
        bytes. For chunked files it resolves only the overlapping chunks and
        avoids reconstructing unrelated file regions.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param start: Starting byte offset in the logical file
        :type start: int
        :param length: Number of bytes to read
        :type length: int
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Requested byte range, clamped to the file end
        :rtype: bytes
        :raises hubvault.errors.IntegrityError: Raised when chunk or blob
            storage fails verification checks.
        :raises hubvault.errors.EntryNotFoundError: Raised when the file is not
            present in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises ValueError: Raised when ``start`` or ``length`` is negative.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     api.read_range("demo.txt", start=1, length=3)
            b'ell'
        """

        return self._backend.read_range(
            path_in_repo=path_in_repo,
            start=start,
            length=length,
            revision=revision or self._default_revision,
        )

    def hf_hub_download(
        self,
        filename: str,
        *,
        revision: Optional[str] = None,
        local_dir: Optional[Union[str, PathLike]] = None,
    ) -> str:
        """
        Materialize a detached user-view path for a file.

        :param filename: Repo-relative file path
        :type filename: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :param local_dir: Optional export directory outside the repository
        :type local_dir: Optional[Union[str, os.PathLike[str]]]
        :return: A filesystem path that can be read safely without mutating repo truth
        :rtype: str
        :raises hubvault.errors.EntryNotFoundError: Raised when the requested
            file does not exist in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when ``filename``
            is invalid.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     download_path = Path(api.hf_hub_download("nested/demo.txt"))
            ...     (download_path.parts[-2:], download_path.read_bytes())
            (('nested', 'demo.txt'), b'hello')
        """

        local_dir_str = None if local_dir is None else str(local_dir)
        return self._backend.hf_hub_download(
            filename=filename,
            revision=revision or self._default_revision,
            local_dir=local_dir_str,
        )

    def snapshot_download(
        self,
        *,
        revision: Optional[str] = None,
        local_dir: Optional[Union[str, PathLike]] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> str:
        """
        Materialize a detached snapshot directory for a revision.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :param local_dir: Optional external export directory
        :type local_dir: Optional[Union[str, os.PathLike[str]]]
        :param allow_patterns: Optional allowlist for repo-relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]]
        :param ignore_patterns: Optional denylist for repo-relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]]
        :return: Filesystem path to the detached snapshot directory
        :rtype: str
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when ``local_dir``
            points into the repository root.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[
            ...             CommitOperationAdd("demo.txt", b"hello"),
            ...             CommitOperationAdd("nested/extra.txt", b"world"),
            ...         ],
            ...         commit_message="seed",
            ...     )
            ...     snapshot_dir = Path(api.snapshot_download(allow_patterns="nested/*"))
            ...     Path(snapshot_dir, "nested", "extra.txt").read_bytes()
            b'world'
        """

        local_dir_str = None if local_dir is None else str(local_dir)
        return self._backend.snapshot_download(
            revision=revision or self._default_revision,
            local_dir=local_dir_str,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
        )

    def upload_file(
        self,
        *,
        path_or_fileobj: Union[str, PathLike, bytes, BinaryIO],
        path_in_repo: str,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Upload a single file through the public commit API.

        :param path_or_fileobj: File content source
        :type path_or_fileobj: Union[str, os.PathLike[str], bytes, BinaryIO]
        :param path_in_repo: Target repo-relative path
        :type path_in_repo: str
        :param revision: Target branch name, defaults to the API default revision
        :type revision: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str]
        :return: Commit metadata for the created commit
        :rtype: CommitInfo

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     commit = api.upload_file(path_or_fileobj=b"hello", path_in_repo="demo.txt")
            ...     (commit.commit_message, api.read_bytes("demo.txt"))
            ('Upload demo.txt with hubvault', b'hello')
        """

        return self._backend.upload_file(
            path_or_fileobj=path_or_fileobj,
            path_in_repo=path_in_repo,
            revision=revision or self._default_revision,
            commit_message=commit_message,
            commit_description=commit_description,
            parent_commit=parent_commit,
        )

    def upload_folder(
        self,
        *,
        folder_path: Union[str, PathLike],
        path_in_repo: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        revision: Optional[str] = None,
        parent_commit: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
        delete_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> CommitInfo:
        """
        Upload a local folder while preserving its relative layout.

        :param folder_path: Local folder to upload
        :type folder_path: Union[str, os.PathLike[str]]
        :param path_in_repo: Optional target directory in the repo
        :type path_in_repo: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param revision: Target branch name, defaults to the API default revision
        :type revision: Optional[str]
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str]
        :param allow_patterns: Optional allowlist for local relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]]
        :param ignore_patterns: Optional denylist for local relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]]
        :param delete_patterns: Optional denylist applied to already uploaded
            repo files beneath ``path_in_repo``
        :type delete_patterns: Optional[Union[Sequence[str], str]]
        :return: Commit metadata for the created commit
        :rtype: CommitInfo

        .. note::
           The low-level staging, publish, and recovery sequence is implemented
           by :class:`hubvault.repo.backend.RepositoryBackend`. This API
           example focuses only on the public workflow.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     root = Path(tmpdir)
            ...     repo_dir = root / "repo"
            ...     source_dir = root / "source"
            ...     source_dir.mkdir()
            ...     _ = source_dir.joinpath("config.json").write_text(
            ...         '{"dtype":"float16"}',
            ...         encoding="utf-8",
            ...     )
            ...     api = HubVaultApi(repo_dir)
            ...     _ = api.create_repo()
            ...     commit = api.upload_folder(folder_path=source_dir, path_in_repo="bundle")
            ...     (commit.commit_message, api.list_repo_files())
            ('Upload folder using hubvault', ['bundle/config.json'])
        """

        return self._backend.upload_folder(
            folder_path=str(folder_path),
            path_in_repo=path_in_repo,
            commit_message=commit_message,
            commit_description=commit_description,
            revision=revision or self._default_revision,
            parent_commit=parent_commit,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
            delete_patterns=delete_patterns,
        )

    def upload_large_folder(
        self,
        *,
        folder_path: Union[str, PathLike],
        revision: Optional[str] = None,
        allow_patterns: Optional[Union[Sequence[str], str]] = None,
        ignore_patterns: Optional[Union[Sequence[str], str]] = None,
    ) -> CommitInfo:
        """
        Upload a large folder through a single atomic local commit.

        The method name follows :meth:`huggingface_hub.HfApi.upload_large_folder`.
        Unlike the remote API, the local backend keeps the whole operation
        atomic and therefore returns a single :class:`CommitInfo`.

        :param folder_path: Local folder to upload
        :type folder_path: Union[str, os.PathLike[str]]
        :param revision: Target branch name, defaults to the API default revision
        :type revision: Optional[str]
        :param allow_patterns: Optional allowlist for local relative paths
        :type allow_patterns: Optional[Union[Sequence[str], str]]
        :param ignore_patterns: Optional denylist for local relative paths
        :type ignore_patterns: Optional[Union[Sequence[str], str]]
        :return: Commit metadata for the created commit
        :rtype: CommitInfo
        :raises ValueError: Raised when ``folder_path`` is not a local
            directory.

        .. note::
           The underlying chunk planning and atomic publish logic lives in
           :class:`hubvault.repo.backend.RepositoryBackend`. The public example
           below shows the API-level behavior only.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     root = Path(tmpdir)
            ...     repo_dir = root / "repo"
            ...     source_dir = root / "source"
            ...     source_dir.mkdir()
            ...     _ = source_dir.joinpath("model.bin").write_bytes(b"A" * 64)
            ...     api = HubVaultApi(repo_dir)
            ...     _ = api.create_repo(large_file_threshold=32)
            ...     commit = api.upload_large_folder(folder_path=source_dir)
            ...     (commit.commit_message, api.read_range("model.bin", start=0, length=4))
            ('Upload large folder using hubvault', b'AAAA')
        """

        return self._backend.upload_large_folder(
            folder_path=str(folder_path),
            revision=revision or self._default_revision,
            allow_patterns=allow_patterns,
            ignore_patterns=ignore_patterns,
        )

    def delete_file(
        self,
        path_in_repo: str,
        *,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Delete a single file through the public commit API.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Target branch name, defaults to the API default revision
        :type revision: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str]
        :return: Commit metadata for the created commit
        :rtype: CommitInfo

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[
            ...             CommitOperationAdd("keep.txt", b"keep"),
            ...             CommitOperationAdd("remove.txt", b"gone"),
            ...         ],
            ...         commit_message="seed",
            ...     )
            ...     commit = api.delete_file("remove.txt")
            ...     (commit.commit_message, api.list_repo_files())
            ('Delete remove.txt with hubvault', ['keep.txt'])
        """

        return self._backend.delete_file(
            path_in_repo=path_in_repo,
            revision=revision or self._default_revision,
            commit_message=commit_message,
            commit_description=commit_description,
            parent_commit=parent_commit,
        )

    def delete_folder(
        self,
        path_in_repo: str,
        *,
        revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        parent_commit: Optional[str] = None,
    ) -> CommitInfo:
        """
        Delete a folder subtree through the public commit API.

        :param path_in_repo: Repo-relative folder path
        :type path_in_repo: str
        :param revision: Target branch name, defaults to the API default revision
        :type revision: Optional[str]
        :param commit_message: Optional commit summary
        :type commit_message: Optional[str]
        :param commit_description: Optional commit description/body
        :type commit_description: Optional[str]
        :param parent_commit: Optional optimistic-concurrency parent commit
        :type parent_commit: Optional[str]
        :return: Commit metadata for the created commit
        :rtype: CommitInfo

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[
            ...             CommitOperationAdd("bundle/model.bin", b"data"),
            ...             CommitOperationAdd("keep.txt", b"keep"),
            ...         ],
            ...         commit_message="seed",
            ...     )
            ...     commit = api.delete_folder("bundle")
            ...     (commit.commit_message, api.list_repo_files())
            ('Delete folder bundle with hubvault', ['keep.txt'])
        """

        return self._backend.delete_folder(
            path_in_repo=path_in_repo,
            revision=revision or self._default_revision,
            commit_message=commit_message,
            commit_description=commit_description,
            parent_commit=parent_commit,
        )

    def reset_ref(self, ref_name: str, *, to_revision: str) -> CommitInfo:
        """
        Reset a branch to another revision.

        :param ref_name: Branch name to update
        :type ref_name: str
        :param to_revision: Revision to resolve as the new head
        :type to_revision: str
        :return: Commit metadata for the target head
        :rtype: CommitInfo
        :raises hubvault.errors.RevisionNotFoundError: Raised when the target
            revision or branch cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when the branch
            name is invalid.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     first = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"v1")],
            ...         commit_message="seed v1",
            ...     )
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"v2")],
            ...         commit_message="seed v2",
            ...     )
            ...     _ = api.reset_ref("main", to_revision=first.oid)
            ...     api.read_bytes("demo.txt")
            b'v1'
        """

        return self._backend.reset_ref(ref_name=ref_name, to_revision=to_revision)

    def quick_verify(self) -> VerifyReport:
        """
        Perform a minimal repository verification pass.

        :return: Verification result
        :rtype: VerifyReport
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo()
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...         commit_message="seed",
            ...     )
            ...     report = api.quick_verify()
            ...     (report.ok, report.errors)
            (True, [])
        """

        return self._backend.quick_verify()

    def full_verify(self) -> VerifyReport:
        """
        Perform a complete repository verification pass.

        Unlike :meth:`quick_verify`, this method validates all live commit,
        tree, file, blob, chunk, pack, and manifest relationships reachable
        from the current refs and also scans the published storage layout for
        malformed persisted objects.

        :return: Verification result
        :rtype: VerifyReport
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo(large_file_threshold=32)
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("model.bin", b"A" * 64)],
            ...         commit_message="seed",
            ...     )
            ...     report = api.full_verify()
            ...     (report.ok, report.errors)
            (True, [])
        """

        return self._backend.full_verify()

    def get_storage_overview(self) -> StorageOverview:
        """
        Analyze repository disk usage and safe reclamation options.

        The returned model separates space that is immediately reclaimable via
        :meth:`gc`, space held only for detached caches, and space retained for
        rollback/history that would require an explicit rewrite such as
        :meth:`squash_history`.

        :return: Repository storage analysis report
        :rtype: StorageOverview
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.
        :raises hubvault.errors.IntegrityError: Raised when persisted storage is
            too inconsistent to analyze safely.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo(large_file_threshold=32)
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("model.bin", b"A" * 64)],
            ...         commit_message="seed",
            ...     )
            ...     _ = api.hf_hub_download("model.bin")
            ...     overview = api.get_storage_overview()
            ...     (overview.total_size > 0, overview.reclaimable_cache_size > 0)
            (True, True)
        """

        return self._backend.get_storage_overview()

    def gc(
        self,
        *,
        dry_run: bool = False,
        prune_cache: bool = True,
    ) -> GcReport:
        """
        Reclaim unreachable repository data and rebuild detachable caches.

        The local GC pass keeps all currently reachable refs intact, rewrites
        chunk storage into a compact live pack/index view, and optionally
        removes rebuildable detached caches under ``cache/``.

        :param dry_run: Whether to compute the result without mutating storage
        :type dry_run: bool, optional
        :param prune_cache: Whether rebuildable managed caches should also be
            removed
        :type prune_cache: bool, optional
        :return: Garbage-collection report
        :rtype: GcReport
        :raises hubvault.errors.RepositoryNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.
        :raises hubvault.errors.IntegrityError: Raised when persisted storage is
            inconsistent and cannot be reclaimed safely.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo(large_file_threshold=32)
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("model.bin", b"A" * 64)],
            ...         commit_message="seed",
            ...     )
            ...     _ = api.hf_hub_download("model.bin")
            ...     report = api.gc(dry_run=True, prune_cache=True)
            ...     (report.dry_run, report.reclaimed_cache_size > 0)
            (True, True)
        """

        return self._backend.gc(dry_run=dry_run, prune_cache=prune_cache)

    def squash_history(
        self,
        ref_name: str,
        *,
        root_revision: Optional[str] = None,
        commit_message: Optional[str] = None,
        commit_description: Optional[str] = None,
        run_gc: bool = True,
        prune_cache: bool = False,
    ) -> SquashReport:
        """
        Rewrite a branch so older history becomes reclaimable.

        The selected branch keeps the same visible file contents at its tip, but
        commits older than the rewritten root become unreachable from that ref.
        When ``run_gc`` is enabled, the method immediately follows the rewrite
        with a maintenance GC pass so now-unreachable data can be reclaimed.

        :param ref_name: Branch name or full branch ref to rewrite
        :type ref_name: str
        :param root_revision: Oldest commit to preserve on the rewritten branch.
            When omitted, the current branch head is collapsed into a single new
            root commit.
        :type root_revision: Optional[str]
        :param commit_message: Optional replacement title for the rewritten root
            commit
        :type commit_message: Optional[str]
        :param commit_description: Optional replacement description/body for the
            rewritten root commit
        :type commit_description: Optional[str]
        :param run_gc: Whether to run :meth:`gc` immediately after rewriting
        :type run_gc: bool, optional
        :param prune_cache: Whether the follow-up GC pass should also prune
            managed caches
        :type prune_cache: bool, optional
        :return: History-squash report
        :rtype: SquashReport
        :raises hubvault.errors.ConflictError: Raised when ``root_revision`` is
            not an ancestor of the selected branch head.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the branch or
            selected revision does not exist.
        :raises hubvault.errors.UnsupportedPathError: Raised when ``ref_name``
            is not a valid branch name.

        .. note::
           The object rewrite, ref update, and optional follow-up GC are
           implemented by :class:`hubvault.repo.backend.RepositoryBackend`.
           The example below stays at the public API level.

        Example::

            >>> import tempfile
            >>> from pathlib import Path
            >>> from hubvault import CommitOperationAdd
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            ...     api = HubVaultApi(Path(tmpdir) / "repo")
            ...     _ = api.create_repo(large_file_threshold=32)
            ...     _ = api.create_commit(
            ...         operations=[CommitOperationAdd("model.bin", b"A" * 64)],
            ...         commit_message="seed v1",
            ...     )
            ...     second = api.create_commit(
            ...         operations=[CommitOperationAdd("model.bin", b"B" * 64)],
            ...         commit_message="seed v2",
            ...     )
            ...     report = api.squash_history("main", root_revision=second.oid, run_gc=False)
            ...     (report.rewritten_commit_count, len(api.list_repo_commits()))
            (1, 1)
        """

        return self._backend.squash_history(
            ref_name=ref_name,
            root_revision=root_revision,
            commit_message=commit_message,
            commit_description=commit_description,
            run_gc=run_gc,
            prune_cache=prune_cache,
        )
