"""Colour suppression must name its own cause.

`skin` and `demo` print nothing when colour is off. The old message said
"no truecolor here" for all three causes, so a user who piped the output into
`head` was told their TERMINAL lacked truecolor — a diagnosis of the wrong
machine, and unactionable. Each cause now names itself.
"""

from __future__ import annotations

import io

import pytest

from cuttlefish_theme import cli


class _Stream(io.StringIO):
    """StringIO with a settable isatty.

    `io.StringIO` defines `isatty` on the type, so `buf.isatty = lambda: True`
    does not take effect. And patching `sys.stdout` from a fixture does not
    survive either: pytest's global capture reassigns it for the call phase.
    Hence the explicit `stream` argument — the same seam an embedding host uses.
    """

    def __init__(self, tty: bool):
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


TTY = _Stream(True)
PIPE = _Stream(False)


def test_no_color_env_is_named_as_the_cause(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli._supports_color(TTY) is False
    reason = cli._no_color_reason(TTY)
    assert reason and "NO_COLOR" in reason


def test_a_pipe_is_named_as_a_pipe_not_as_a_terminal_limitation(monkeypatch):
    """The regression: piping used to blame the terminal's colour depth."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    reason = cli._no_color_reason(PIPE)
    assert reason is not None
    assert "not a terminal" in reason
    assert "truecolor" not in reason.lower()


def test_dumb_term_is_named_as_the_cause(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    reason = cli._no_color_reason(TTY)
    assert reason and "TERM=dumb" in reason


def test_unset_term_says_unset_rather_than_printing_nothing(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    reason = cli._no_color_reason(TTY)
    assert reason and "TERM=(unset)" in reason


def test_a_capable_tty_has_no_reason(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert cli._no_color_reason(TTY) is None
    assert cli._supports_color(TTY) is True


def test_the_default_stream_is_resolved_late_not_at_import(monkeypatch):
    """Binding sys.stdout as a default argument would freeze the wrong stream."""
    import sys
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(sys, "stdout", TTY)
    assert cli._no_color_reason() is None
    monkeypatch.setattr(sys, "stdout", PIPE)
    assert cli._no_color_reason() is not None


@pytest.mark.parametrize("run", ["run_skin", "run_demo"])
def test_suppressed_surfaces_print_the_specific_reason(run, monkeypatch, capsys):
    """Both suppressed surfaces report the cause, and still exit 0.

    Under pytest, captured stdout is genuinely not a tty, so this exercises the
    real default path rather than an injected stream.
    """
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")

    assert getattr(cli, run)() == 0
    out = capsys.readouterr().out
    assert "colour off" in out and "not a terminal" in out
    assert "no truecolor here" not in out
