import pytest

from hubvault.server.config import DEFAULT_SERVER_PORT, SERVER_MODE_API, SERVER_MODE_FRONTEND, ServerConfig


@pytest.mark.unittest
class TestServerConfig:
    def test_normalizes_mode_tokens_and_paths(self, tmp_path):
        config = ServerConfig(
            repo_path=tmp_path / "repo",
            mode="FRONTEND",
            token_ro=("ro", "rw", "ro"),
            token_rw=("rw", "rw"),
            port=DEFAULT_SERVER_PORT,
        )

        assert config.repo_path == tmp_path / "repo"
        assert config.mode == SERVER_MODE_FRONTEND
        assert config.token_ro == ("ro",)
        assert config.token_rw == ("rw",)
        assert config.ui_enabled is True
        assert config.browser_url == "http://127.0.0.1:%d/" % (DEFAULT_SERVER_PORT,)

    def test_from_env_reads_values_and_flags(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HUBVAULT_REPO_PATH", str(tmp_path / "repo"))
        monkeypatch.setenv("HUBVAULT_SERVE_MODE", "api")
        monkeypatch.setenv("HUBVAULT_HOST", "0.0.0.0")
        monkeypatch.setenv("HUBVAULT_PORT", "9000")
        monkeypatch.setenv("HUBVAULT_TOKEN_RO", "ro-a,ro-b")
        monkeypatch.setenv("HUBVAULT_TOKEN_RW", "rw-a")
        monkeypatch.setenv("HUBVAULT_OPEN_BROWSER", "true")
        monkeypatch.setenv("HUBVAULT_INIT", "1")
        monkeypatch.setenv("HUBVAULT_INITIAL_BRANCH", "dev")
        monkeypatch.setenv("HUBVAULT_LARGE_FILE_THRESHOLD", "123")

        config = ServerConfig.from_env()

        assert config.mode == SERVER_MODE_API
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.token_ro == ("ro-a", "ro-b")
        assert config.token_rw == ("rw-a",)
        assert config.open_browser is True
        assert config.init is True
        assert config.initial_branch == "dev"
        assert config.large_file_threshold == 123
        assert config.browser_url == "http://127.0.0.1:9000/"

    def test_requires_at_least_one_token(self, tmp_path):
        with pytest.raises(ValueError, match="At least one"):
            ServerConfig(repo_path=tmp_path / "repo")

    def test_rejects_invalid_modes_and_ports(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported server mode"):
            ServerConfig(repo_path=tmp_path / "repo", mode="broken", token_rw=("rw",))

        with pytest.raises(ValueError, match="between 1 and 65535"):
            ServerConfig(repo_path=tmp_path / "repo", port=0, token_rw=("rw",))
