"""
Public commit operations for the :mod:`hubvault` repository API.

This module mirrors the high-level commit operation shape used by
``huggingface_hub`` so callers can describe write intent with familiar objects
before passing them to :class:`hubvault.api.HubVaultApi.create_commit`.

The module contains:

* :class:`CommitOperationAdd` - Add or replace file content from bytes, a path, or a file object
* :class:`CommitOperationDelete` - Delete a file or folder path
* :class:`CommitOperationCopy` - Copy a file or subtree from another repo path
"""

import io
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Union

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal


@dataclass
class CommitOperationAdd:
    """
    Add or replace a file in the repository.

    The constructor follows the ``huggingface_hub`` public API shape by taking
    a single ``path_or_fileobj`` argument that may be local file bytes, a local
    filesystem path, or a binary file object.

    :param path_in_repo: Target repo-relative path
    :type path_in_repo: str
    :param path_or_fileobj: File source expressed as a local path, bytes, or a
        binary file object
    :type path_or_fileobj: Union[str, pathlib.Path, bytes, BinaryIO]
    :raises ValueError: Raised when ``path_or_fileobj`` is not a supported
        source type or refers to a missing file.

    Example::

        >>> op = CommitOperationAdd("demo.txt", b"hello")
        >>> op.path_in_repo
        'demo.txt'
    """

    path_in_repo: str
    path_or_fileobj: Union[str, Path, bytes, BinaryIO]

    def __post_init__(self) -> None:
        """
        Validate the add-operation source.

        :return: ``None``.
        :rtype: None
        :raises ValueError: Raised when ``path_or_fileobj`` is not a supported
            upload source or points to a missing local file.

        Example::

            >>> CommitOperationAdd("demo.txt", b"hello")
            CommitOperationAdd(path_in_repo='demo.txt', path_or_fileobj=b'hello')
        """

        if isinstance(self.path_or_fileobj, Path):
            self.path_or_fileobj = str(self.path_or_fileobj)

        if isinstance(self.path_or_fileobj, str):
            path_or_fileobj = os.path.normpath(os.path.expanduser(self.path_or_fileobj))
            if not os.path.isfile(path_or_fileobj):
                raise ValueError(
                    "Provided path: %r is not a file on the local file system" % path_or_fileobj
                )
            self.path_or_fileobj = path_or_fileobj
        elif isinstance(self.path_or_fileobj, bytes):
            return
        elif isinstance(self.path_or_fileobj, io.BufferedIOBase):
            try:
                self.path_or_fileobj.tell()
                self.path_or_fileobj.seek(0, os.SEEK_CUR)
            except (OSError, AttributeError) as err:
                raise ValueError(
                    "path_or_fileobj is a file-like object but does not implement seek() and tell()"
                ) from err
            self.path_or_fileobj.seek(0, os.SEEK_SET)
        else:
            raise ValueError(
                "path_or_fileobj must be an instance of str, pathlib.Path, bytes, or io.BufferedIOBase"
            )

    @contextmanager
    def as_file(self) -> Iterator[BinaryIO]:
        """
        Yield a readable binary file object for the operation payload.

        :return: Iterator yielding a binary file object
        :rtype: Iterator[BinaryIO]

        Example::

            >>> op = CommitOperationAdd("demo.txt", b"hello")
            >>> with op.as_file() as fileobj:
            ...     fileobj.read()
            b'hello'
        """

        if isinstance(self.path_or_fileobj, str):
            with open(self.path_or_fileobj, "rb") as fileobj:
                yield fileobj
            return

        if isinstance(self.path_or_fileobj, bytes):
            yield io.BytesIO(self.path_or_fileobj)
            return

        previous_position = self.path_or_fileobj.tell()
        try:
            yield self.path_or_fileobj
        finally:
            self.path_or_fileobj.seek(previous_position, os.SEEK_SET)


@dataclass
class CommitOperationDelete:
    """
    Delete a file or folder from the repository.

    :param path_in_repo: Repo-relative file or folder path
    :type path_in_repo: str
    :param is_folder: Whether the delete targets a folder. When set to
        ``"auto"``, the operation treats a trailing ``"/"`` as a folder hint.
    :type is_folder: Union[bool, Literal["auto"]], optional
    :raises ValueError: Raised when ``is_folder`` is not ``True``, ``False``,
        or ``"auto"``.

    Example::

        >>> CommitOperationDelete("folder/")
        CommitOperationDelete(path_in_repo='folder/', is_folder=True)
    """

    path_in_repo: str
    is_folder: Union[bool, Literal["auto"]] = "auto"

    def __post_init__(self) -> None:
        """
        Normalize the folder-delete mode.

        :return: ``None``.
        :rtype: None
        :raises ValueError: Raised when ``is_folder`` has an unsupported value.

        Example::

            >>> CommitOperationDelete("folder/", is_folder="auto").is_folder
            True
        """

        if self.is_folder == "auto":
            self.is_folder = self.path_in_repo.endswith("/")
        if not isinstance(self.is_folder, bool):
            raise ValueError("is_folder must be one of True, False, or 'auto'")


@dataclass
class CommitOperationCopy:
    """
    Copy a file or subtree from another repo path.

    :param src_path_in_repo: Source repo-relative path
    :type src_path_in_repo: str
    :param path_in_repo: Destination repo-relative path
    :type path_in_repo: str
    :param src_revision: Optional source revision. When omitted, the current
        target revision head is used as the source snapshot.
    :type src_revision: Optional[str], optional

    .. note::
       Private HF-internal constructor fields such as ``_src_oid`` and
       ``_dest_oid`` are intentionally not exposed here because they would be
       no-op compatibility placeholders in the local repository design.

    Example::

        >>> op = CommitOperationCopy("src/file.txt", "dst/file.txt", src_revision="main")
        >>> op.src_revision
        'main'
    """

    src_path_in_repo: str
    path_in_repo: str
    src_revision: Optional[str] = None
