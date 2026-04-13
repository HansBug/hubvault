import pytest

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.server import ServerConfig
from hubvault.server.deps import build_repo_api_getter, get_repo_api_factory, get_token_authorizer


@pytest.mark.unittest
class TestServerDeps:
    def test_build_repo_api_getter_accepts_api_or_factory_and_rejects_invalid_combinations(self):
        api = object()

        getter = build_repo_api_getter(api=api)
        assert getter() is api

        created = []

        def _factory():
            marker = object()
            created.append(marker)
            return marker

        factory_getter = build_repo_api_getter(api_factory=_factory)
        assert factory_getter() is created[0]

        with pytest.raises(TypeError, match="either a concrete api instance or an api_factory, not both"):
            build_repo_api_getter(api=api, api_factory=_factory)

        with pytest.raises(TypeError, match="api instance or api_factory is required"):
            build_repo_api_getter()

    def test_get_repo_api_factory_returns_fresh_apis_bound_to_current_default_branch(self, tmp_path):
        repo_dir = tmp_path / "repo"
        seed_api = HubVaultApi(repo_dir, revision="release/v1")
        seed_api.create_repo(default_branch="release/v1")
        seed_api.create_branch(branch="main")
        seed_api.create_commit(
            revision="main",
            operations=[CommitOperationAdd("main-only.txt", b"main branch payload")],
            commit_message="advance main only",
        )

        config = ServerConfig(repo_path=repo_dir, token_ro=("ro-token",), token_rw=("rw-token",))
        factory = get_repo_api_factory(config)

        api_one = factory()
        api_two = factory()

        assert isinstance(api_one, HubVaultApi)
        assert isinstance(api_two, HubVaultApi)
        assert api_one is not api_two
        assert api_one.list_repo_files() == []
        assert api_two.list_repo_files(revision="main") == ["main-only.txt"]

    def test_get_token_authorizer_uses_server_config_tokens(self, tmp_path):
        config = ServerConfig(repo_path=tmp_path / "repo", token_ro=("ro-token",), token_rw=("rw-token",))

        authorizer = get_token_authorizer(config)

        assert authorizer.resolve("ro-token").access == "ro"
        assert authorizer.resolve("rw-token").can_write is True
