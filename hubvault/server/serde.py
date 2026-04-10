"""Minimal serialization helpers for server responses."""


def build_meta_service_payload(*, service, version, mode, repo_path, ui_enabled, default_branch, head, auth) -> dict:
    """Build the `/api/v1/meta/service` response body."""

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
    """Build the `/api/v1/meta/whoami` response body."""

    return {
        "access": access,
        "can_write": can_write,
    }
