"""
Public repository API for the :mod:`hubvault` package.

This module exposes :class:`HubVaultApi`, a local embedded repository interface
with method names intentionally aligned with the broad calling style of
``huggingface_hub`` where it makes sense for an on-disk repository.

The module contains:

* :class:`HubVaultApi` - Public entry point for local embedded repositories

Example::

    >>> from hubvault import CommitOperationAdd, HubVaultApi
    >>> api = HubVaultApi("/tmp/demo-repo")
    >>> _ = api.create_repo(exist_ok=True)
    >>> commit = api.create_commit(
    ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
    ...     commit_message="seed",
    ... )
    >>> commit.revision
    'main'
"""

from os import PathLike
from pathlib import Path
from typing import BinaryIO, Dict, Optional, Sequence, Union

from .models import CommitInfo, GitCommitInfo, PathInfo, RepoInfo, VerifyReport
from .repo import _RepositoryBackend


class HubVaultApi:
    """
    Public entry point for a local ``hubvault`` repository.

    :param repo_path: Filesystem path to the local repository root
    :type repo_path: Union[str, os.PathLike[str]]
    :param revision: Default revision used by read APIs
    :type revision: str

    Example::

        >>> from hubvault import HubVaultApi, CommitOperationAdd
        >>> api = HubVaultApi("/tmp/demo-repo")
        >>> _ = api.create_repo(exist_ok=True)
        >>> commit = api.create_commit(
        ...     revision="main",
        ...     operations=[
        ...         CommitOperationAdd("example.txt", b"hello"),
        ...     ],
        ...     commit_message="add example",
        ... )
        >>> commit.revision
        'main'
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

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> api._default_revision
            'main'
        """

        self._repo_path = Path(repo_path)
        self._default_revision = revision
        self._backend = _RepositoryBackend(self._repo_path)

    def create_repo(
        self,
        default_branch: str = "main",
        exist_ok: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> RepoInfo:
        """
        Create a local repository.

        :param default_branch: Default branch name, defaults to ``"main"``
        :type default_branch: str
        :param exist_ok: Whether an existing repository may be reused
        :type exist_ok: bool
        :param metadata: Optional repository metadata
        :type metadata: Optional[Dict[str, str]]
        :return: Information about the created repository
        :rtype: RepoInfo
        :raises hubvault.errors.RepoAlreadyExistsError: Raised when the target
            path already contains a repository or non-empty directory.
        :raises hubvault.errors.UnsupportedPathError: Raised when the default
            branch name is invalid.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> info = api.create_repo(exist_ok=True)
            >>> info.default_branch
            'main'
        """

        return self._backend.create_repo(default_branch=default_branch, exist_ok=exist_ok, metadata=metadata)

    def repo_info(self, revision: Optional[str] = None) -> RepoInfo:
        """
        Return metadata about the repository.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Repository metadata
        :rtype: RepoInfo
        :raises hubvault.errors.RepoNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the selected
            revision does not exist.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> isinstance(api.repo_info().repo_path, str)
            True
        """

        return self._backend.repo_info(revision=revision or self._default_revision)

    def create_commit(
        self,
        revision: str = "main",
        operations: Sequence[object] = (),
        parent_commit: Optional[str] = None,
        expected_head: Optional[str] = None,
        commit_message: str = "",
        metadata: Optional[Dict[str, str]] = None,
    ) -> CommitInfo:
        """
        Create a new commit on a branch.

        :param revision: Target branch name
        :type revision: str
        :param operations: Commit operations to apply
        :type operations: Sequence[object]
        :param parent_commit: Expected parent commit for optimistic concurrency
        :type parent_commit: Optional[str]
        :param expected_head: Explicit expected branch head
        :type expected_head: Optional[str]
        :param commit_message: Commit message
        :type commit_message: str
        :param metadata: Optional commit metadata
        :type metadata: Optional[Dict[str, str]]
        :return: Metadata for the created commit
        :rtype: CommitInfo
        :raises hubvault.errors.ConflictError: Raised when the operation set is
            empty, unsupported, or optimistic concurrency checks fail.
        :raises hubvault.errors.PathNotFoundError: Raised when delete/copy
            operations refer to missing paths.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the target
            revision cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when revision or
            path inputs are invalid.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> commit = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> commit.revision
            'main'
        """

        return self._backend.create_commit(
            revision=revision,
            operations=operations,
            parent_commit=parent_commit,
            expected_head=expected_head,
            commit_message=commit_message,
            metadata=metadata,
        )

    def get_paths_info(
        self,
        paths: Sequence[str],
        revision: Optional[str] = None,
    ) -> Sequence[PathInfo]:
        """
        Return public metadata for selected paths.

        :param paths: Repo-relative paths to inspect
        :type paths: Sequence[str]
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Path metadata in input order
        :rtype: Sequence[PathInfo]
        :raises hubvault.errors.PathNotFoundError: Raised when any requested
            path is absent from the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when a requested
            path is invalid.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> _ = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> api.get_paths_info(["demo.txt"])[0].path
            'demo.txt'
        """

        return self._backend.get_paths_info(paths=paths, revision=revision or self._default_revision)

    def list_repo_tree(self, path_in_repo: str = "", revision: Optional[str] = None) -> Sequence[PathInfo]:
        """
        List direct children under a repository directory.

        :param path_in_repo: Repo-relative directory path, defaults to the root
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Direct child path metadata
        :rtype: Sequence[PathInfo]
        :raises hubvault.errors.PathNotFoundError: Raised when the directory is
            missing from the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when
            ``path_in_repo`` refers to a file or is invalid.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> api.list_repo_tree()
            []
        """

        return self._backend.list_repo_tree(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def list_repo_files(self, revision: Optional[str] = None) -> Sequence[str]:
        """
        List all file paths in a revision.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Sorted repo-relative file paths
        :rtype: Sequence[str]
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> api.list_repo_files()
            []
        """

        return self._backend.list_repo_files(revision=revision or self._default_revision)

    def list_repo_commits(
        self,
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
        :raises hubvault.errors.RepoNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> _ = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> api.list_repo_commits()[0].title
            'seed'
        """

        return self._backend.list_repo_commits(
            revision=revision or self._default_revision,
            formatted=formatted,
        )

    def open_file(self, path_in_repo: str, revision: Optional[str] = None) -> BinaryIO:
        """
        Open a file as a read-only binary stream.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Read-only binary stream
        :rtype: BinaryIO
        :raises hubvault.errors.PathNotFoundError: Raised when the file is not
            present in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> _ = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> with api.open_file("demo.txt") as fileobj:
            ...     fileobj.read()
            b'hello'
        """

        return self._backend.open_file(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def read_bytes(self, path_in_repo: str, revision: Optional[str] = None) -> bytes:
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
        :raises hubvault.errors.PathNotFoundError: Raised when the file is not
            present in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> _ = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> api.read_bytes("demo.txt")
            b'hello'
        """

        return self._backend.read_bytes(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def hf_hub_download(
        self,
        filename: str,
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
        :raises hubvault.errors.PathNotFoundError: Raised when the requested
            file does not exist in the selected revision.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the revision
            cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when ``filename``
            is invalid.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> _ = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> api.hf_hub_download("demo.txt").endswith("demo.txt")
            True
        """

        local_dir_str = None if local_dir is None else str(local_dir)
        return self._backend.hf_hub_download(
            filename=filename,
            revision=revision or self._default_revision,
            local_dir=local_dir_str,
        )

    def reset_ref(self, ref_name: str, to_revision: str) -> CommitInfo:
        """
        Reset a branch to another revision.

        :param ref_name: Branch name to update
        :type ref_name: str
        :param to_revision: Revision to resolve as the new head
        :type to_revision: str
        :return: Commit metadata for the target head
        :rtype: CommitInfo
        :raises hubvault.errors.LockTimeoutError: Raised when another writer is
            currently holding the repository lock.
        :raises hubvault.errors.RevisionNotFoundError: Raised when the target
            revision or branch cannot be resolved.
        :raises hubvault.errors.UnsupportedPathError: Raised when the branch
            name is invalid.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> commit = api.create_commit(
            ...     operations=[CommitOperationAdd("demo.txt", b"hello")],
            ...     commit_message="seed",
            ... )
            >>> api.reset_ref("main", commit.commit_id).commit_id == commit.commit_id
            True
        """

        return self._backend.reset_ref(ref_name=ref_name, to_revision=to_revision)

    def quick_verify(self) -> VerifyReport:
        """
        Perform a minimal repository verification pass.

        :return: Verification result
        :rtype: VerifyReport
        :raises hubvault.errors.RepoNotFoundError: Raised when the repository
            root does not contain a valid ``hubvault`` repository.

        Example::

            >>> api = HubVaultApi("/tmp/demo-repo")
            >>> _ = api.create_repo(exist_ok=True)
            >>> api.quick_verify().ok
            True
        """

        return self._backend.quick_verify()
