"""
Repository-wide constants for :mod:`hubvault.repo`.

This module centralizes the small stable constant set used by the repository
backend and the public API wrapper.

The module contains:

* :data:`FORMAT_MARKER` - Repository format marker string
* :data:`FORMAT_VERSION` - Repository format version integer
* :data:`DEFAULT_BRANCH` - Default branch name
* :data:`OBJECT_HASH` - Internal object-hash algorithm name
* :data:`LARGE_FILE_THRESHOLD` - Default threshold for chunked storage
* :data:`REPO_LOCK_FILENAME` - Repository lock filename

Example::

    >>> from hubvault.repo.constants import DEFAULT_BRANCH
    >>> DEFAULT_BRANCH
    'main'
"""

FORMAT_MARKER = "hubvault-repo/v1"
FORMAT_VERSION = 1
DEFAULT_BRANCH = "main"
OBJECT_HASH = "sha256"
LARGE_FILE_THRESHOLD = 16 * 1024 * 1024
REPO_LOCK_FILENAME = "repo.lock"
