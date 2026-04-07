"""
Public configuration exports for the :mod:`hubvault.config` package.

This package keeps thin package-level exports for stable project metadata used
by packaging code and CLI presentation helpers.

The package contains:

* :data:`__TITLE__` - Canonical package title
* :data:`__VERSION__` - Package version string
* :data:`__DESCRIPTION__` - Short package description
* :data:`__AUTHOR__` - Comma-separated author list
* :data:`__AUTHOR_EMAIL__` - Comma-separated author email list

Example::

    >>> from hubvault.config import __TITLE__, __VERSION__
    >>> __TITLE__
    'hubvault'
    >>> isinstance(__VERSION__, str)
    True
"""

from .meta import __AUTHOR__, __AUTHOR_EMAIL__, __DESCRIPTION__, __TITLE__, __VERSION__

__all__ = [
    "__AUTHOR__",
    "__AUTHOR_EMAIL__",
    "__DESCRIPTION__",
    "__TITLE__",
    "__VERSION__",
]
