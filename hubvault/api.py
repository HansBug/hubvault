"""
Public repository API for the :mod:`hubvault` package.

This module exposes :class:`HubVaultApi`, a local embedded repository interface
with method names intentionally aligned with the broad calling style of
``huggingface_hub`` where it makes sense for an on-disk repository.
"""

from os import PathLike
from pathlib import Path
from typing import BinaryIO, Dict, Optional, Sequence, Union

from .models import CommitInfo, PathInfo, RepoInfo, VerifyReport
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
        ...         CommitOperationAdd.from_bytes("example.txt", b"hello"),
        ...     ],
        ...     commit_message="add example",
        ... )
        >>> commit.revision
        'main'
    """

    def __init__(self, repo_path: Union[str, PathLike], revision: str = "main") -> None:
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
        """

        return self._backend.create_repo(default_branch=default_branch, exist_ok=exist_ok, metadata=metadata)

    def repo_info(self, revision: Optional[str] = None) -> RepoInfo:
        """
        Return metadata about the repository.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Repository metadata
        :rtype: RepoInfo
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
        expand: bool = False,
    ) -> Sequence[PathInfo]:
        """
        Return public metadata for selected paths.

        :param paths: Repo-relative paths to inspect
        :type paths: Sequence[str]
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :param expand: Reserved compatibility flag for later phases
        :type expand: bool
        :return: Path metadata in input order
        :rtype: Sequence[PathInfo]
        """

        return self._backend.get_paths_info(paths=paths, revision=revision or self._default_revision, expand=expand)

    def list_repo_tree(self, path_in_repo: str = "", revision: Optional[str] = None) -> Sequence[PathInfo]:
        """
        List direct children under a repository directory.

        :param path_in_repo: Repo-relative directory path, defaults to the root
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Direct child path metadata
        :rtype: Sequence[PathInfo]
        """

        return self._backend.list_repo_tree(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def list_repo_files(self, revision: Optional[str] = None) -> Sequence[str]:
        """
        List all file paths in a revision.

        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Sorted repo-relative file paths
        :rtype: Sequence[str]
        """

        return self._backend.list_repo_files(revision=revision or self._default_revision)

    def open_file(self, path_in_repo: str, revision: Optional[str] = None) -> BinaryIO:
        """
        Open a file as a read-only binary stream.

        :param path_in_repo: Repo-relative file path
        :type path_in_repo: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :return: Read-only binary stream
        :rtype: BinaryIO
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
        """

        return self._backend.read_bytes(path_in_repo=path_in_repo, revision=revision or self._default_revision)

    def hf_hub_download(
        self,
        repo_id: str,
        filename: str,
        revision: Optional[str] = None,
        local_dir: Optional[Union[str, PathLike]] = None,
    ) -> str:
        """
        Materialize a detached user-view path for a file.

        :param repo_id: Compatibility placeholder for the repo identifier
        :type repo_id: str
        :param filename: Repo-relative file path
        :type filename: str
        :param revision: Revision to resolve, defaults to the API default revision
        :type revision: Optional[str]
        :param local_dir: Optional export directory outside the repository
        :type local_dir: Optional[Union[str, os.PathLike[str]]]
        :return: A filesystem path that can be read safely without mutating repo truth
        :rtype: str
        """

        local_dir_str = None if local_dir is None else str(local_dir)
        return self._backend.hf_hub_download(
            repo_id=repo_id,
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
        """

        return self._backend.reset_ref(ref_name=ref_name, to_revision=to_revision)

    def quick_verify(self) -> VerifyReport:
        """
        Perform a minimal repository verification pass.

        :return: Verification result
        :rtype: VerifyReport
        """

        return self._backend.quick_verify()
