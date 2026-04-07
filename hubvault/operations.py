"""
Public commit operations for the :mod:`hubvault` repository API.

The MVP API models write requests as immutable operation objects that are later
consumed by :class:`hubvault.api.HubVaultApi`. These operations only describe
user intent; repository mutation still happens through explicit commit APIs.

The module contains:

* :class:`CommitOperationAdd` - Add or replace file content
* :class:`CommitOperationDelete` - Delete a file or subtree
* :class:`CommitOperationCopy` - Copy a file or subtree from the current revision
"""

from dataclasses import dataclass
from io import BytesIO
from typing import BinaryIO, Optional, Union


@dataclass(frozen=True)
class CommitOperationAdd:
    """
    Add or replace a file in the repository.

    :param path_in_repo: Target repo-relative path
    :type path_in_repo: str
    :param data: File content bytes
    :type data: bytes
    :param content_type: Optional content type hint
    :type content_type: Optional[str]
    """

    path_in_repo: str
    data: bytes
    content_type: Optional[str] = None

    @classmethod
    def from_bytes(
        cls,
        path_in_repo: str,
        data: bytes,
        content_type: Optional[str] = None,
    ) -> "CommitOperationAdd":
        """
        Build an add operation from in-memory bytes.

        :param path_in_repo: Target repo-relative path
        :type path_in_repo: str
        :param data: File content bytes
        :type data: bytes
        :param content_type: Optional content type hint
        :type content_type: Optional[str]
        :return: A new add operation
        :rtype: CommitOperationAdd
        """

        return cls(path_in_repo=path_in_repo, data=data, content_type=content_type)

    @classmethod
    def from_file(
        cls,
        path_in_repo: str,
        path: str,
        content_type: Optional[str] = None,
    ) -> "CommitOperationAdd":
        """
        Build an add operation from a filesystem path.

        The source file path is read eagerly and is not persisted as repository
        metadata.

        :param path_in_repo: Target repo-relative path
        :type path_in_repo: str
        :param path: Source filesystem path
        :type path: str
        :param content_type: Optional content type hint
        :type content_type: Optional[str]
        :return: A new add operation
        :rtype: CommitOperationAdd
        """

        with open(path, "rb") as file_:
            data = file_.read()
        return cls(path_in_repo=path_in_repo, data=data, content_type=content_type)

    @classmethod
    def from_fileobj(
        cls,
        path_in_repo: str,
        fileobj: Union[BinaryIO, BytesIO],
        content_type: Optional[str] = None,
    ) -> "CommitOperationAdd":
        """
        Build an add operation from a file-like object.

        :param path_in_repo: Target repo-relative path
        :type path_in_repo: str
        :param fileobj: Binary file-like object to read
        :type fileobj: BinaryIO
        :param content_type: Optional content type hint
        :type content_type: Optional[str]
        :return: A new add operation
        :rtype: CommitOperationAdd
        """

        data = fileobj.read()
        return cls(path_in_repo=path_in_repo, data=data, content_type=content_type)


@dataclass(frozen=True)
class CommitOperationDelete:
    """
    Delete a file or subtree from the repository.

    :param path_in_repo: Repo-relative path to delete
    :type path_in_repo: str
    """

    path_in_repo: str


@dataclass(frozen=True)
class CommitOperationCopy:
    """
    Copy a file or subtree from the current revision.

    :param src_path_in_repo: Source repo-relative path
    :type src_path_in_repo: str
    :param path_in_repo: Destination repo-relative path
    :type path_in_repo: str
    """

    src_path_in_repo: str
    path_in_repo: str
