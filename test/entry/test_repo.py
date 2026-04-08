from pathlib import Path

import pytest
from click.testing import CliRunner

from hubvault import HubVaultApi
from hubvault.entry.cli import cli


@pytest.mark.unittest
class TestEntryRepoCommands:
    def test_init_commit_and_reset_commands_cover_basic_repo_lifecycle(self, tmp_path):
        repo_dir = tmp_path / "repo"
        source_file = tmp_path / "payload.txt"
        source_file.write_bytes(b"v1")

        runner = CliRunner()

        init_result = runner.invoke(cli, ["init", str(repo_dir)])
        assert init_result.exit_code == 0

        first_commit_result = runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "seed commit",
                "--add",
                "demo.txt={path}".format(path=str(source_file)),
            ],
        )
        assert first_commit_result.exit_code == 0
        assert "[main " in first_commit_result.output

        source_file.write_bytes(b"v2")
        second_commit_result = runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "update commit",
                "--add",
                "demo.txt={path}".format(path=str(source_file)),
            ],
        )
        assert second_commit_result.exit_code == 0

        api = HubVaultApi(repo_dir)
        commits = list(api.list_repo_commits(revision="main"))
        first_commit = commits[-1]

        reset_result = runner.invoke(cli, ["-C", str(repo_dir), "reset", first_commit.commit_id])

        assert reset_result.exit_code == 0
        assert "HEAD is now at" in reset_result.output
        assert api.read_bytes("demo.txt", revision="main") == b"v1"

    def test_merge_command_reports_fast_forward_and_conflict_cases(self, tmp_path):
        runner = CliRunner()

        ff_repo = tmp_path / "fast_forward_repo"
        source_file = tmp_path / "fast_forward.txt"
        source_file.write_bytes(b"base")

        assert runner.invoke(cli, ["init", str(ff_repo)]).exit_code == 0
        assert runner.invoke(
            cli,
            [
                "-C",
                str(ff_repo),
                "commit",
                "-m",
                "seed",
                "--add",
                "demo.txt={path}".format(path=str(source_file)),
            ],
        ).exit_code == 0
        assert runner.invoke(cli, ["-C", str(ff_repo), "branch", "feature"]).exit_code == 0

        feature_file = tmp_path / "feature.txt"
        feature_file.write_bytes(b"feature")
        assert runner.invoke(
            cli,
            [
                "-C",
                str(ff_repo),
                "commit",
                "--revision",
                "feature",
                "-m",
                "feature update",
                "--add",
                "feature.txt={path}".format(path=str(feature_file)),
            ],
        ).exit_code == 0

        merge_result = runner.invoke(cli, ["-C", str(ff_repo), "merge", "feature"])

        assert merge_result.exit_code == 0
        assert "Fast-forward" in merge_result.output
        assert HubVaultApi(ff_repo).read_bytes("feature.txt", revision="main") == b"feature"

        conflict_repo = tmp_path / "conflict_repo"
        shared_file = tmp_path / "shared.txt"
        shared_file.write_bytes(b"base")

        assert runner.invoke(cli, ["init", str(conflict_repo)]).exit_code == 0
        assert runner.invoke(
            cli,
            [
                "-C",
                str(conflict_repo),
                "commit",
                "-m",
                "seed",
                "--add",
                "shared.txt={path}".format(path=str(shared_file)),
            ],
        ).exit_code == 0
        assert runner.invoke(cli, ["-C", str(conflict_repo), "branch", "feature"]).exit_code == 0

        shared_file.write_bytes(b"main change")
        assert runner.invoke(
            cli,
            [
                "-C",
                str(conflict_repo),
                "commit",
                "-m",
                "main change",
                "--add",
                "shared.txt={path}".format(path=str(shared_file)),
            ],
        ).exit_code == 0

        shared_file.write_bytes(b"feature change")
        assert runner.invoke(
            cli,
            [
                "-C",
                str(conflict_repo),
                "commit",
                "--revision",
                "feature",
                "-m",
                "feature change",
                "--add",
                "shared.txt={path}".format(path=str(shared_file)),
            ],
        ).exit_code == 0

        conflict_result = runner.invoke(cli, ["-C", str(conflict_repo), "merge", "feature"])

        assert conflict_result.exit_code != 0
        assert "CONFLICT (modify/modify): shared.txt" in conflict_result.output
        assert HubVaultApi(conflict_repo).read_bytes("shared.txt", revision="main") == b"main change"

    def test_commit_command_supports_copy_delete_and_rejects_invalid_specs(self, tmp_path):
        repo_dir = tmp_path / "repo"
        source_file = tmp_path / "source.txt"
        source_file.write_bytes(b"hello")

        runner = CliRunner()

        assert runner.invoke(cli, ["init", str(repo_dir), "--large-file-threshold", "32"]).exit_code == 0
        assert runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "seed",
                "--add",
                "origin.txt={path}".format(path=str(source_file)),
            ],
        ).exit_code == 0

        copy_result = runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "copy file",
                "--copy",
                "origin.txt=copy.txt",
            ],
        )
        delete_result = runner.invoke(
            cli,
            [
                "-C",
                str(repo_dir),
                "commit",
                "-m",
                "delete file",
                "--delete",
                "copy.txt",
            ],
        )
        no_ops_result = runner.invoke(cli, ["-C", str(repo_dir), "commit", "-m", "no ops"])
        bad_add_result = runner.invoke(
            cli,
            ["-C", str(repo_dir), "commit", "-m", "bad add", "--add", "broken"],
        )
        bad_copy_result = runner.invoke(
            cli,
            ["-C", str(repo_dir), "commit", "-m", "bad copy", "--copy", "origin.txt="],
        )

        assert copy_result.exit_code == 0
        assert delete_result.exit_code == 0
        assert no_ops_result.exit_code != 0
        assert "No operations provided" in no_ops_result.output
        assert bad_add_result.exit_code != 0
        assert "expects <repo_path>=<value>" in bad_add_result.output
        assert bad_copy_result.exit_code != 0
        assert "expects non-empty <repo_path>=<value>" in bad_copy_result.output

        api = HubVaultApi(repo_dir)
        assert api.read_bytes("origin.txt", revision="main") == b"hello"
        assert "copy.txt" not in api.list_repo_files(revision="main")
