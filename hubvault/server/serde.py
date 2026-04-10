"""
Minimal response-serialization helpers for :mod:`hubvault.server`.

This module holds small payload builders that keep route functions readable
without introducing heavier schema machinery in the early server phases.
"""


def build_meta_service_payload(*, service, version, mode, repo_path, ui_enabled, default_branch, head, auth) -> dict:
    """
    Build the ``/api/v1/meta/service`` response body.

    :param service: Service title
    :type service: str
    :param version: Service version string
    :type version: str
    :param mode: Active server mode
    :type mode: str
    :param repo_path: Repository root path
    :type repo_path: str
    :param ui_enabled: Whether the frontend UI is enabled
    :type ui_enabled: bool
    :param default_branch: Repository default branch
    :type default_branch: str
    :param head: Current repository head OID
    :type head: Optional[str]
    :param auth: Authentication summary payload
    :type auth: dict
    :return: JSON-compatible service payload
    :rtype: dict
    """

    return {
        "service": service,
        "version": version,
        "mode": mode,
        "ui_enabled": ui_enabled,
        "repo": {
            "path": repo_path,
            "default_branch": default_branch,
            "head": head,
        },
        "auth": auth,
    }


def build_whoami_payload(*, access, can_write) -> dict:
    """
    Build the ``/api/v1/meta/whoami`` response body.

    :param access: Resolved access level
    :type access: str
    :param can_write: Whether the caller may mutate repository state
    :type can_write: bool
    :return: JSON-compatible caller summary
    :rtype: dict
    """

    return {
        "access": access,
        "can_write": can_write,
    }
