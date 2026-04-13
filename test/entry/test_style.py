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

    def test_public_style_text_returns_plain_text_when_no_style_is_requested(self):
        assert style_text("demo", env={}) == "demo"
        assert style_text(123, env={}) == "123"

    def test_public_echo_helper_emits_color_only_when_allowed(self):
        runner = CliRunner()

        colored = runner.invoke(_style_demo, [], color=True)
        plain = runner.invoke(_style_demo_no_color, [], color=True)

        assert colored.exit_code == 0
        assert "\x1b[" in colored.output

        assert plain.exit_code == 0
        assert "\x1b[" not in plain.output
        assert "styled output" in plain.output

    def test_public_echo_helper_allows_none_messages_without_a_click_context(self, monkeypatch):
        recorded = {}

        def _fake_echo(message=None, file=None, err=False, nl=True, color=None):
            recorded["message"] = message
            recorded["color"] = color
            recorded["err"] = err
            recorded["nl"] = nl

        monkeypatch.setattr(click, "get_current_context", lambda silent=True: None)
        monkeypatch.setattr(click, "echo", _fake_echo)

        echo(None, env={})

        assert recorded == {"message": None, "color": None, "err": False, "nl": True}

    def test_public_echo_helper_uses_click_context_color_when_available(self, monkeypatch):
        recorded = {}

        class _Context(object):
            color = False

        def _fake_echo(message=None, file=None, err=False, nl=True, color=None):
            recorded["message"] = message
            recorded["color"] = color

        monkeypatch.setattr(click, "get_current_context", lambda silent=True: _Context())
        monkeypatch.setattr(click, "echo", _fake_echo)

        echo("styled output", tone="success", env={})

        assert "styled output" in recorded["message"]
        assert recorded["color"] is False

    def test_public_echo_helper_preserves_explicit_color_flags(self, monkeypatch):
        recorded = {}

        def _fake_echo(message=None, file=None, err=False, nl=True, color=None):
            recorded["message"] = message
            recorded["color"] = color

        monkeypatch.setattr(click, "echo", _fake_echo)

        echo("plain", color=False, env={})

        assert recorded == {"message": "plain", "color": False}
