"""
Public remote-client exports for :mod:`hubvault.remote`.

This package keeps the public remote surface thin. The real HTTP transport and
optional-dependency handling live in sibling modules, while this package root
only re-exports the supported client names.
"""

from .api import HubVaultRemoteAPI, HubVaultRemoteApi

__all__ = [
    "HubVaultRemoteAPI",
    "HubVaultRemoteApi",
]
