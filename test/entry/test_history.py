import pytest
import sqlite3
from click.testing import CliRunner

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.entry.cli import cli
from hubvault.repo.sqlite import SQLITE_METADATA_FILENAME


@pytest.mark.unittest
class TestEntryHistoryCommands:
    def test_log_command_outputs_full_and_oneline_history(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("demo.txt", b"v1")],
            commit_message="seed title\n\nseed body",
        )
        api.create_commit(
            operations=[CommitOperationAdd("demo.txt", b"v2")],
            commit_message="update title",
        )

        runner = CliRunner()

        oneline_result = runner.invoke(cli, ["-C", str(repo_dir), "log", "--oneline", "-n", "1"])
        full_result = runner.invoke(cli, ["-C", str(repo_dir), "log"])

        assert oneline_result.exit_code == 0
        assert len([line for line in oneline_result.output.splitlines() if line.strip()]) == 1
        assert "update title" in oneline_result.output

        assert full_result.exit_code == 0
        assert any(line.startswith("commit ") and len(line.split()[-1]) == 40 for line in full_result.output.splitlines())
        assert "Author:" in full_result.output
        assert "Date:" in full_result.output
        assert "seed title" in full_result.output
        assert "seed body" in full_result.output

    def test_log_command_outputs_initial_history_after_init(self, tmp_path):
        repo_dir = tmp_path / "repo"
        HubVaultApi(repo_dir).create_repo()

        runner = CliRunner()
        result = runner.invoke(cli, ["-C", str(repo_dir), "log"])

        assert result.exit_code == 0
        assert "Initial commit" in result.output

    def test_log_command_rejects_empty_branch_without_commits(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_branch(branch="empty")
        with sqlite3.connect(str(repo_dir / SQLITE_METADATA_FILENAME)) as conn:
            conn.execute(
                "UPDATE refs SET commit_id = NULL WHERE ref_kind = ? AND ref_name = ?",
                ("branch", "empty"),
            )
            conn.commit()

        runner = CliRunner()
        result = runner.invoke(cli, ["-C", str(repo_dir), "log", "empty"])

        assert result.exit_code != 0
        assert "does not have any commits yet" in result.output
