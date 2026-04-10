"""Cache-layout placeholders for the future remote client."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteCacheLayout:
    """Describe the cache roots reserved for remote client artifacts."""

    download_root: str
    snapshot_root: str
