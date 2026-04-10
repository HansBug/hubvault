"""
Cache-layout helpers for :mod:`hubvault.remote`.

This module defines the minimal cache-root container used by the early remote
client skeleton.

The module contains:

* :class:`RemoteCacheLayout` - Cache-root description for remote artifacts
"""

from dataclasses import dataclass


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
