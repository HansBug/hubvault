"""
Cache-layout helpers for :mod:`hubvault.remote`.

This module computes stable cache locations for remote downloads and snapshots.
The cache remains a client-local convenience layer rather than repository
truth.

The module contains:

* :class:`RemoteCacheLayout` - Cache-root description for remote artifacts
* :func:`get_remote_cache_layout` - Resolve the cache roots for one client
* :func:`build_download_target` - Build the cached path for one downloaded file
* :func:`build_snapshot_target` - Build the cached path for one downloaded snapshot
"""

from dataclasses import dataclass
from hashlib import sha256
import os
import re
from pathlib import Path
from typing import Iterable, Optional, Union


_CACHE_ENV_VAR = "HUBVAULT_REMOTE_CACHE_DIR"
_SAFE_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class RemoteCacheLayout:
    """
    Describe the cache roots reserved for remote client artifacts.

    :param download_root: Root directory for downloaded individual files
    :type download_root: str
    :param snapshot_root: Root directory for snapshot-style downloads
    :type snapshot_root: str
    """

    download_root: str
    snapshot_root: str


def _default_cache_root() -> Path:
    """
    Return the default remote-cache root for the current platform.

    :return: Default remote-cache root directory
    :rtype: pathlib.Path
    """

    override = os.environ.get(_CACHE_ENV_VAR)
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "hubvault" / "remote"
        return Path.home() / "AppData" / "Local" / "hubvault" / "remote"

    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache_home:
        return Path(xdg_cache_home).expanduser() / "hubvault" / "remote"
    return Path.home() / ".cache" / "hubvault" / "remote"


def _endpoint_key(base_url: str) -> str:
    """
    Build a stable filesystem key for one remote base URL.

    :param base_url: Remote base URL
    :type base_url: str
    :return: Stable endpoint key
    :rtype: str
    """

    return sha256(base_url.rstrip("/").encode("utf-8")).hexdigest()[:16]


def _safe_component(value: str) -> str:
    """
    Normalize one cache-path component for filesystem use.

    :param value: Raw path component
    :type value: str
    :return: Filesystem-safe component
    :rtype: str
    """

    normalized = _SAFE_COMPONENT_PATTERN.sub("_", str(value)).strip("._")
    return normalized or "default"


def get_remote_cache_layout(cache_dir: Optional[Union[str, os.PathLike]] = None) -> RemoteCacheLayout:
    """
    Resolve the cache roots for one remote client.

    :param cache_dir: Optional explicit cache root override
    :type cache_dir: Optional[Union[str, os.PathLike]]
    :return: Cache-root layout for downloads and snapshots
    :rtype: RemoteCacheLayout
    """

    root = Path(cache_dir).expanduser() if cache_dir is not None else _default_cache_root()
    return RemoteCacheLayout(
        download_root=str(root / "downloads"),
        snapshot_root=str(root / "snapshots"),
    )


def build_download_target(
    layout: RemoteCacheLayout,
    *,
    base_url: str,
    path_in_repo: str,
    etag: Optional[str],
    revision: Optional[str] = None,
    local_dir: Optional[Union[str, os.PathLike]] = None,
) -> Path:
    """
    Build the target path for one remote file download.

    :param layout: Cache layout for the current client
    :type layout: RemoteCacheLayout
    :param base_url: Remote base URL
    :type base_url: str
    :param path_in_repo: Repo-relative file path
    :type path_in_repo: str
    :param etag: Download identity used for cache reuse
    :type etag: Optional[str]
    :param revision: Optional selected revision string
    :type revision: Optional[str]
    :param local_dir: Optional explicit export directory
    :type local_dir: Optional[Union[str, os.PathLike]]
    :return: Filesystem path where the file should be materialized
    :rtype: pathlib.Path
    """

    relative_path = Path(path_in_repo)
    if local_dir is not None:
        return Path(local_dir).expanduser() / relative_path

    identity = etag or sha256(("%s:%s" % (revision or "default", path_in_repo)).encode("utf-8")).hexdigest()[:16]
    return Path(layout.download_root) / _endpoint_key(base_url) / _safe_component(identity) / relative_path


def build_snapshot_target(
    layout: RemoteCacheLayout,
    *,
    base_url: str,
    snapshot_id: str,
    local_dir: Optional[Union[str, os.PathLike]] = None,
) -> Path:
    """
    Build the target directory for one remote snapshot download.

    :param layout: Cache layout for the current client
    :type layout: RemoteCacheLayout
    :param base_url: Remote base URL
    :type base_url: str
    :param snapshot_id: Stable snapshot identity, typically a commit OID
    :type snapshot_id: str
    :param local_dir: Optional explicit export directory
    :type local_dir: Optional[Union[str, os.PathLike]]
    :return: Filesystem path where the snapshot should be materialized
    :rtype: pathlib.Path
    """

    if local_dir is not None:
        return Path(local_dir).expanduser()
    return Path(layout.snapshot_root) / _endpoint_key(base_url) / _safe_component(snapshot_id)


def snapshot_is_complete(target_dir: Path, repo_paths: Iterable[str]) -> bool:
    """
    Return whether a snapshot directory already contains all requested files.

    :param target_dir: Candidate snapshot root
    :type target_dir: pathlib.Path
    :param repo_paths: Repo-relative file paths expected in the snapshot
    :type repo_paths: Iterable[str]
    :return: Whether every requested file exists under ``target_dir``
    :rtype: bool
    """

    for item in repo_paths:
        if not (target_dir / item).is_file():
            return False
    return True
