"""Launch a real hubvault frontend server for Playwright checks."""

import tempfile
from pathlib import Path

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.optional import import_optional_dependency
from hubvault.server import ServerConfig, create_app


HOST = "127.0.0.1"
PORT = 9613


def _build_fixture_repo(repo_dir: Path) -> None:
    api = HubVaultApi(repo_dir, revision="release/v1")
    api.create_repo(default_branch="release/v1")

    first_commit = api.create_commit(
        operations=[
            CommitOperationAdd(
                "README.md",
                (
                    b"# HubVault Fixture\n\n"
                    b"This repository exists for the Phase 6 frontend smoke tests.\n\n"
                    b"- README rendering\n"
                    b"- file browsing\n"
                    b"- revision switching\n"
                ),
            ),
            CommitOperationAdd("docs/guide.md", b"# Guide\n\nVersion 1 guide.\n"),
            CommitOperationAdd("configs/config.json", b"{\"version\": 1}\n"),
        ],
        commit_message="seed frontend fixture",
    )
    api.create_branch(branch="dev", revision=first_commit.oid)
    api.create_tag(tag="v1.0", revision=first_commit.oid)
    api.create_commit(
        operations=[
            CommitOperationAdd("docs/guide.md", b"# Guide\n\nVersion 2 guide.\n"),
            CommitOperationAdd("artifacts/model.bin", b"fixture-model-v2\n"),
        ],
        commit_message="update guide and model",
    )
    api.hf_hub_download("artifacts/model.bin")


def main() -> int:
    uvicorn = import_optional_dependency(
        "uvicorn",
        extra="api",
        feature="webui e2e fixture server",
        missing_names={"click", "h11", "httptools"},
    )

    with tempfile.TemporaryDirectory(prefix="hubvault-webui-e2e-") as tmpdir:
        repo_dir = Path(tmpdir) / "repo"
        _build_fixture_repo(repo_dir)
        config = ServerConfig(
            repo_path=repo_dir,
            mode="frontend",
            host=HOST,
            port=PORT,
            token_ro=("ro-token",),
            token_rw=("rw-token",),
        )
        uvicorn.run(create_app(config), host=HOST, port=PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
