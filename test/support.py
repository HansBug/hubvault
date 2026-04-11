from pathlib import Path

import pytest

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.server import ServerConfig, create_app


TEST_DEFAULT_BRANCH = "release/v1"
TEST_RO_TOKEN = "ro-token"
TEST_RW_TOKEN = "rw-token"


def get_fastapi_test_client():
    testclient = pytest.importorskip("fastapi.testclient")
    return testclient.TestClient


def ro_headers():
    return {"Authorization": "Bearer %s" % (TEST_RO_TOKEN,)}


def rw_headers():
    return {"Authorization": "Bearer %s" % (TEST_RW_TOKEN,)}


def seed_phase45_repo(repo_dir: Path):
    api = HubVaultApi(repo_dir, revision=TEST_DEFAULT_BRANCH)
    api.create_repo(default_branch=TEST_DEFAULT_BRANCH)

    seed_commit = api.create_commit(
        operations=[
            CommitOperationAdd("README.md", b"# hubvault\n"),
            CommitOperationAdd("artifacts/model.bin", b"phase45-model-v1\n"),
            CommitOperationAdd("artifacts/weights.tmp", b"temporary\n"),
            CommitOperationAdd("configs/config.json", b'{\"version\": 1}\n'),
        ],
        commit_message="seed release",
    )
    api.create_branch(branch="dev", revision=seed_commit.oid)
    api.create_tag(tag="v1", revision=seed_commit.oid)

    head_commit = api.create_commit(
        operations=[
            CommitOperationAdd("artifacts/model.bin", b"phase45-model-v2\n"),
            CommitOperationAdd("docs/guide.md", b"phase45-guide\n"),
        ],
        commit_message="update release artifacts",
    )
    return {
        "api": api,
        "repo_info": api.repo_info(),
        "seed_commit": seed_commit,
        "head_commit": head_commit,
        "model_bytes": b"phase45-model-v2\n",
        "guide_bytes": b"phase45-guide\n",
    }


def seed_phase78_repo(repo_dir: Path):
    chunk_unit = bytes(range(256)) * 4096
    large_base = (chunk_unit * 20) + (b"shared-phase78-block\n" * 8192)
    large_update = large_base + b"phase78-tail\n"

    api = HubVaultApi(repo_dir, revision=TEST_DEFAULT_BRANCH)
    api.create_repo(default_branch=TEST_DEFAULT_BRANCH, large_file_threshold=1024 * 1024)
    seed_commit = api.create_commit(
        operations=[
            CommitOperationAdd("README.md", b"# phase78\n"),
            CommitOperationAdd("docs/source.txt", b"shared-document\n"),
            CommitOperationAdd("artifacts/large.bin", large_base),
        ],
        commit_message="seed phase78",
    )
    api.create_branch(branch="feature", revision=seed_commit.oid)
    api.create_commit(
        revision="feature",
        operations=[CommitOperationAdd("docs/source.txt", b"feature-change\n")],
        commit_message="diverge feature",
    )
    return {
        "api": api,
        "seed_commit": seed_commit,
        "large_base": large_base,
        "large_update": large_update,
        "shared_text": b"shared-document\n",
    }


def create_phase45_app(repo_dir: Path):
    return create_app(
        ServerConfig(
            repo_path=repo_dir,
            mode="api",
            token_ro=(TEST_RO_TOKEN,),
            token_rw=(TEST_RW_TOKEN,),
        )
    )


def patch_remote_test_client(monkeypatch, app):
    TestClient = get_fastapi_test_client()

    def _build_client(**kwargs):
        return TestClient(
            app,
            base_url=kwargs.get("base_url", "http://testserver"),
            headers=kwargs.get("headers") or {},
        )

    monkeypatch.setattr("hubvault.remote.api.build_http_client", _build_client)
