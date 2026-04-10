"""
Metadata constants for the :mod:`hubvault` package.

This module centralizes the small set of package metadata values that are
shared by packaging logic and the command-line interface.

The module contains:

* :data:`__TITLE__` - Canonical package title
* :data:`__VERSION__` - Package version string
* :data:`__DESCRIPTION__` - Short package description
* :data:`__AUTHOR__` - Comma-separated author list
* :data:`__AUTHOR_EMAIL__` - Comma-separated author email list

Example::

    >>> from hubvault.config.meta import __TITLE__, __VERSION__
    >>> __TITLE__
    'hubvault'
    >>> isinstance(__VERSION__, str)
    True
"""

#: Title of this project (should be `hubvault`).
__TITLE__ = 'hubvault'

#: Version of this project.
__VERSION__ = '0.0.2'

#: Short description of the project, will be included in ``setup.py``.
__DESCRIPTION__ = 'API-first embedded versioned storage for local ML artifacts'

#: Author of this project.
__AUTHOR__ = 'HansBug, narugo1992'

#: Email of the authors'.
__AUTHOR_EMAIL__ = 'hansbug@buaa.edu.cn, narugo1992@deepghs.org'
