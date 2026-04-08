from pathlib import Path

import pytest
import click
from click.testing import CliRunner

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.entry.cli import cli
from hubvault.entry.context import load_cli_repo_context, set_cli_repo_path


@pytest.mark.unittest
class TestEntryContext:
    def test_global_c_option_runs_status_outside_repo_directory(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo(default_branch="dev")
        api.create_commit(
            revision="dev",
            operations=[CommitOperationAdd("demo.txt", b"hello")],
            commit_message="seed",
        )

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=str(tmp_path)):
            result = runner.invoke(cli, ["-C", str(repo_dir), "status"])

        assert result.exit_code == 0
        assert "On branch dev" in result.output
        assert "repository clean" in result.output

    def test_global_c_option_allows_init_without_explicit_path(self, tmp_path):
        repo_dir = tmp_path / "repo"
        runner = CliRunner()

        result = runner.invoke(cli, ["-C", str(repo_dir), "init"])

        assert result.exit_code == 0
        assert "Initialized empty HubVault repository" in result.output
        assert HubVaultApi(repo_dir).repo_info(revision="main").default_branch == "main"

    def test_load_cli_repo_context_reuses_cached_public_context(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("demo.txt", b"hello")],
            commit_message="seed",
        )

        ctx = click.Context(cli)
        with ctx:
            set_cli_repo_path(ctx, str(repo_dir))
            first = load_cli_repo_context(ctx)
            second = load_cli_repo_context(ctx)

        assert first.default_branch == "main"
        assert second is first
