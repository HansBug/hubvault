"""
Metadata constants for the :mod:`hubvault` package.

This module centralizes the package metadata shared by packaging logic, the
command-line entry points, and documentation-facing version reporting.

The summary values here should reflect the current shipped product surface
rather than only the original local-repository MVP. In the current PR1 state,
``hubvault`` ships:

* the embedded versioned repository runtime for local ML artifacts
* the local Python API and CLI
* an optional embedded FastAPI service with a bundled browser UI
* an optional Python remote client aligned with that HTTP service

The module contains:

* :data:`__TITLE__` - Canonical package title
* :data:`__VERSION__` - Package version string
* :data:`__DESCRIPTION__` - Short PyPI/package summary
* :data:`__AUTHOR__` - Comma-separated author list
* :data:`__AUTHOR_EMAIL__` - Comma-separated author email list

Example::

    >>> from hubvault.config.meta import __DESCRIPTION__, __TITLE__, __VERSION__
    >>> __TITLE__
    'hubvault'
    >>> 'web UI' in __DESCRIPTION__
    True
    >>> isinstance(__VERSION__, str)
    True
"""

#: Title of this project (should be `hubvault`).
__TITLE__ = 'hubvault'

#: Version of this project.
__VERSION__ = '0.0.2'

#: Short package summary used by ``setup.py`` and packaging metadata.
__DESCRIPTION__ = (
    'Embedded versioned repository for ML artifacts with Python API, '
    'HTTP service, remote client, and bundled web UI'
)

#: Author of this project.
__AUTHOR__ = 'HansBug, narugo1992'

#: Email of the authors'.
__AUTHOR_EMAIL__ = 'hansbug@buaa.edu.cn, narugo1992@deepghs.org'
