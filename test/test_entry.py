import pytest
from click.testing import CliRunner

from hubvault.entry import hubvaultcli


@pytest.mark.unittest
class TestEntryCli:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ['-v'])

        assert result.exit_code == 0
        assert 'hubvault' in result.output.lower()

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ['-h'])

        assert result.exit_code == 0
        assert 'usage' in result.output.lower()
