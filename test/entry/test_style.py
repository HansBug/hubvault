import click
import pytest
from click.testing import CliRunner

from hubvault.entry.style import colors_enabled, echo, style_text


@click.command()
def _style_demo():
    echo("styled output", tone="success", env={})


@click.command()
def _style_demo_no_color():
    echo("styled output", tone="success", env={"NO_COLOR": "1"})


@pytest.mark.unittest
class TestEntryStyle:
    def test_public_style_helpers_honor_no_color_environment(self):
        assert colors_enabled(env={}) is True
        assert colors_enabled(env={"NO_COLOR": "1"}) is False
        assert colors_enabled(env={"HUBVAULT_NO_COLOR": "1"}) is False
        assert style_text("demo", tone="success", env={"NO_COLOR": "1"}) == "demo"
        assert "\x1b[" in style_text("demo", tone="success", env={})

    def test_public_echo_helper_emits_color_only_when_allowed(self):
        runner = CliRunner()

        colored = runner.invoke(_style_demo, [], color=True)
        plain = runner.invoke(_style_demo_no_color, [], color=True)

        assert colored.exit_code == 0
        assert "\x1b[" in colored.output

        assert plain.exit_code == 0
        assert "\x1b[" not in plain.output
        assert "styled output" in plain.output
