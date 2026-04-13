import pytest
import sqlite3
from click.testing import CliRunner

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.entry.cli import cli
from hubvault.repo.sqlite import SQLITE_METADATA_FILENAME


@pytest.mark.unittest
class TestEntryRefCommands:
    def test_branch_command_lists_show_current_creates_and_deletes(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("demo.txt", b"hello")],
            commit_message="seed",
        )

        runner = CliRunner()

        create_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "feature"])
        current_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "--show-current"])
        list_result = runner.invoke(cli, ["-C", str(repo_dir), "branch"])
        delete_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "-d", "feature"])

        assert create_result.exit_code == 0
        assert current_result.exit_code == 0
        assert current_result.output.strip() == "main"

        assert list_result.exit_code == 0
        assert "* main" in list_result.output
        assert "feature" in list_result.output

        assert delete_result.exit_code == 0
        assert "Deleted branch feature" in delete_result.output

    def test_tag_command_lists_creates_and_deletes(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("demo.txt", b"hello")],
            commit_message="seed",
        )

        runner = CliRunner()

        create_result = runner.invoke(cli, ["-C", str(repo_dir), "tag", "v1"])
        list_result = runner.invoke(cli, ["-C", str(repo_dir), "tag"])
        delete_result = runner.invoke(cli, ["-C", str(repo_dir), "tag", "-d", "v1"])

        assert create_result.exit_code == 0
        assert list_result.exit_code == 0
        assert list_result.output.strip() == "v1"

        assert delete_result.exit_code == 0
        assert "Deleted tag 'v1'" in delete_result.output

    def test_branch_and_tag_delete_require_names_and_empty_branch_verbose_is_reported(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()

        runner = CliRunner()

        create_branch_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "feature"])
        verbose_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "-v"])
        delete_empty_branch_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "-d", "feature"])
        missing_branch_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "-d"])
        missing_tag_result = runner.invoke(cli, ["-C", str(repo_dir), "tag", "-d"])

        assert create_branch_result.exit_code == 0
        assert verbose_result.exit_code == 0
        assert "* main" in verbose_result.output
        assert "Initial commit" in verbose_result.output
        assert "  feature" in verbose_result.output

        assert delete_empty_branch_result.exit_code == 0
        assert "Deleted branch feature" in delete_empty_branch_result.output

        assert missing_branch_result.exit_code != 0
        assert "branch -d/-D requires a branch name." in missing_branch_result.output

        assert missing_tag_result.exit_code != 0
        assert "tag -d requires a tag name." in missing_tag_result.output

    def test_delete_commands_report_empty_branch_and_empty_tag_targets(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_branch(branch="empty-branch")
        api.create_tag(tag="empty-tag")

        with sqlite3.connect(str(repo_dir / SQLITE_METADATA_FILENAME)) as conn:
            conn.execute(
                "UPDATE refs SET commit_id = NULL WHERE ref_kind = ? AND ref_name = ?",
                ("branch", "empty-branch"),
            )
            conn.execute(
                "UPDATE refs SET commit_id = NULL WHERE ref_kind = ? AND ref_name = ?",
                ("tag", "empty-tag"),
            )
            conn.commit()

        runner = CliRunner()
        delete_branch_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "-d", "empty-branch"])
        delete_tag_result = runner.invoke(cli, ["-C", str(repo_dir), "tag", "-d", "empty-tag"])

        assert delete_branch_result.exit_code == 0
        assert "Deleted branch empty-branch." in delete_branch_result.output

        assert delete_tag_result.exit_code == 0
        assert "Deleted tag 'empty-tag'." in delete_tag_result.output
