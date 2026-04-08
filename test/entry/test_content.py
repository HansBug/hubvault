from pathlib import Path

import pytest
from click.testing import CliRunner

from hubvault import CommitOperationAdd, HubVaultApi
from hubvault.entry.cli import cli


@pytest.mark.unittest
class TestEntryContentCommands:
    def test_ls_tree_download_snapshot_and_verify_commands(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[
                CommitOperationAdd("nested/demo.txt", b"hello"),
                CommitOperationAdd("config.json", b"{}"),
            ],
            commit_message="seed",
        )

        runner = CliRunner()

        tree_result = runner.invoke(cli, ["-C", str(repo_dir), "ls-tree", "main", "-r"])
        download_result = runner.invoke(cli, ["-C", str(repo_dir), "download", "nested/demo.txt"])
        snapshot_result = runner.invoke(cli, ["-C", str(repo_dir), "snapshot"])
        verify_result = runner.invoke(cli, ["-C", str(repo_dir), "verify"])
        full_verify_result = runner.invoke(cli, ["-C", str(repo_dir), "verify", "--full"])

        assert tree_result.exit_code == 0
        assert "100644 blob " in tree_result.output
        assert "\tnested/demo.txt" in tree_result.output

        assert download_result.exit_code == 0
        download_path = Path(download_result.output.strip())
        assert download_path.name == "demo.txt"
        assert download_path.parent.name == "nested"
        assert download_path.read_bytes() == b"hello"

        assert snapshot_result.exit_code == 0
        snapshot_path = Path(snapshot_result.output.strip())
        assert snapshot_path.joinpath("nested", "demo.txt").read_bytes() == b"hello"
        assert snapshot_path.joinpath("config.json").read_bytes() == b"{}"

        assert verify_result.exit_code == 0
        assert "Quick verification OK" in verify_result.output

        assert full_verify_result.exit_code == 0
        assert "Full verification OK" in full_verify_result.output

    def test_verify_command_reports_full_verification_failures(self, tmp_path):
        repo_dir = tmp_path / "repo"
        api = HubVaultApi(repo_dir)
        api.create_repo()
        api.create_commit(
            operations=[CommitOperationAdd("demo.txt", b"hello")],
            commit_message="seed",
        )

        blob_path = next(repo_dir.glob("objects/blobs/sha256/*/*.data"))
        blob_path.write_bytes(b"corrupt")

        runner = CliRunner()
        result = runner.invoke(cli, ["-C", str(repo_dir), "verify", "--full"])

        assert result.exit_code != 0
        assert "Full verification failed" in result.output
        assert "Errors:" in result.output
