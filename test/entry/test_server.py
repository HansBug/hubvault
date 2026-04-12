import pytest
from click.testing import CliRunner

import hubvault.server
from hubvault.optional import MissingOptionalDependencyError
from hubvault.entry.cli import cli


@pytest.mark.unittest
class TestEntryServer:
    def test_help_lists_serve_command_and_options(self):
        runner = CliRunner()

        result = runner.invoke(cli, ["serve", "--help"])

        assert result.exit_code == 0
        assert "--token-rw" in result.output
        assert "--mode" in result.output

    def test_serve_builds_server_config_and_calls_public_launcher(self, monkeypatch, tmp_path):
        seen = {}

        def _fake_launch(config):
            seen["config"] = config

        monkeypatch.setattr(hubvault.server, "launch", _fake_launch)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "serve",
                str(tmp_path / "repo"),
                "--host",
                "0.0.0.0",
                "--port",
                "9001",
                "--mode",
                "api",
                "--token-ro",
                "ro-token",
                "--token-rw",
                "rw-token",
                "--init",
                "--initial-branch",
                "dev",
                "--large-file-threshold",
                "1024",
            ],
        )

        assert result.exit_code == 0
        assert seen["config"].host == "0.0.0.0"
        assert seen["config"].port == 9001
        assert seen["config"].mode == "api"
        assert seen["config"].token_ro == ("ro-token",)
        assert seen["config"].token_rw == ("rw-token",)
        assert seen["config"].init is True
        assert seen["config"].initial_branch == "dev"
        assert seen["config"].large_file_threshold == 1024

    def test_serve_reports_missing_optional_dependency_as_click_error(self, monkeypatch, tmp_path):
        def _raise_missing(_config):
            raise MissingOptionalDependencyError(extra="api", feature="serve", missing_name="fastapi")

        monkeypatch.setattr(hubvault.server, "launch", _raise_missing)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "serve",
                str(tmp_path / "repo"),
                "--token-rw",
                "rw-token",
            ],
        )

        assert result.exit_code != 0
        assert "pip install hubvault[api]" in result.output
