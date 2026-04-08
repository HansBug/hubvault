"""
Repository package exports for :mod:`hubvault`.

This package keeps :mod:`hubvault.repo` as the stable import path for the local
repository backend while allowing the implementation to be split into smaller
submodules.

The package contains:

* :data:`FORMAT_MARKER` - Repository format marker string
* :data:`FORMAT_VERSION` - Repository format version integer
* :data:`DEFAULT_BRANCH` - Default branch name
* :data:`OBJECT_HASH` - Internal object-hash algorithm name
* :data:`LARGE_FILE_THRESHOLD` - Default threshold for chunked storage

Example::

    >>> from hubvault.repo import DEFAULT_BRANCH, LARGE_FILE_THRESHOLD
    >>> DEFAULT_BRANCH
    'main'
    >>> LARGE_FILE_THRESHOLD > 0
    True
"""

from .constants import DEFAULT_BRANCH, FORMAT_MARKER, FORMAT_VERSION, LARGE_FILE_THRESHOLD, OBJECT_HASH

__all__ = [
    "DEFAULT_BRANCH",
    "FORMAT_MARKER",
    "FORMAT_VERSION",
    "LARGE_FILE_THRESHOLD",
    "OBJECT_HASH",
]
