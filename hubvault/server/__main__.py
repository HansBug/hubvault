"""
Module entry point for ``python -m hubvault.server``.

The actual parser and runtime behavior live in :mod:`hubvault.server.launch`.
This module only forwards process execution to that public entry point.
"""

from .launch import main

if __name__ == "__main__":
    raise SystemExit(main())
