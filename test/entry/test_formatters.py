from datetime import datetime

import pytest
from click.testing import CliRunner

from hubvault import CommitOperationAdd, GitCommitInfo, HubVaultApi, MergeResult, VerifyReport
from hubvault.entry.cli import cli
from hubvault.entry.formatters import (
    format_branch_output,
    format_merge_output,
    format_status_output,
    format_verify_output,
    short_oid,
)


@pytest.mark.unittest
class TestEntryFormatters:
    def test_status_branch_log_and_ls_tree_outputs_follow_git_like_shapes(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("nested/demo.txt", b"hello")],
            commit_message="seed formatter output",
        )
        commit = api.list_repo_commits(revision="main")[0]

        runner = CliRunner()

        status_result = runner.invoke(cli, ["-C", str(repo_dir), "status", "--short", "--branch"])
        branch_result = runner.invoke(cli, ["-C", str(repo_dir), "branch", "-v"])
        log_result = runner.invoke(cli, ["-C", str(repo_dir), "log", "--oneline"])
        tree_result = runner.invoke(cli, ["-C", str(repo_dir), "ls-tree", "main", "-r"])

        assert status_result.exit_code == 0
        assert status_result.output.strip() == "## main"

        assert branch_result.exit_code == 0
        assert "* main" in branch_result.output
        assert commit.title in branch_result.output

        assert log_result.exit_code == 0
        assert "{oid} {title}".format(
            oid=commit.commit_id.split(":", 1)[-1][:7],
            title=commit.title,
        ) in log_result.output

        assert tree_result.exit_code == 0
        assert "100644 blob " in tree_result.output
        assert "\tnested/demo.txt" in tree_result.output

    def test_public_formatter_helpers_cover_empty_and_failure_shapes(self):
        commit = GitCommitInfo(
            commit_id="abcdef1234567890abcdef1234567890abcdef12",
            authors=[],
            created_at=datetime(2024, 1, 1, 0, 0, 0),
            title="seed",
            message="",
            formatted_title=None,
            formatted_message=None,
        )
        merge_result = MergeResult(
            status="already-up-to-date",
            target_revision="main",
            source_revision="feature",
            base_commit="0" * 40,
            target_head_before="1" * 40,
            source_head="1" * 40,
            head_after="1" * 40,
            commit=None,
            conflicts=[],
            fast_forward=False,
            created_commit=False,
        )
        verify_report = VerifyReport(
            ok=False,
            checked_refs=["refs/heads/main"],
            warnings=["view rebuilt"],
            errors=["file sha256 mismatch"],
        )

        assert short_oid(None) == "0000000"
        assert format_status_output("main", None, short=True, show_branch=True) == "## No commits on main"
        assert format_status_output("main", None, short=True, show_branch=False) == ""
        assert "No commits yet" in format_status_output("main", None, short=False, show_branch=False)
        assert "(empty)" in format_branch_output(["main"], "main", {"main": None}, verbose=True)
        assert "abcdef1 seed" in format_branch_output(["main"], "main", {"main": commit}, verbose=True)
        assert format_merge_output(merge_result) == "Already up to date."

        verify_output = format_verify_output(verify_report, full=True)
        assert "Full verification failed" in verify_output
        assert "Warnings:" in verify_output
        assert "Errors:" in verify_output
