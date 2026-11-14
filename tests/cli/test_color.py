"""Color is for a terminal that wants it (DESIGN §19: warnings and errors), and the tests read plain text whatever the
shell running them says (14 Nov: a full check run where FORCE_COLOR is set failed three CLI tests on "\\x1b[31m")."""

import pytest
import typer
from typer.testing import CliRunner

from friday.cli import render
from tests.cli.conftest import plain_output

app = typer.Typer()


@app.command()
def complain() -> None:
    render.error("boom")
    render.show("triage", {"late": {"essay": 3}, "options": []}, as_json=False)


def ran() -> str:
    return CliRunner().invoke(app, []).output


@pytest.mark.parametrize("asks", [("FORCE_COLOR", "1"), ("TTY_COMPATIBLE", "1")])
def test_a_terminal_asking_for_color_gets_errors_red_and_warnings_yellow(
    monkeypatch: pytest.MonkeyPatch, asks: tuple[str, str]
) -> None:
    monkeypatch.setenv(*asks)
    monkeypatch.setattr(render, "out", render.console())
    monkeypatch.setattr(render, "err", render.console(stderr=True))
    assert "\x1b[31mfriday: boom" in ran() and "\x1b[33m! essay: 3 h late" in ran()


@pytest.mark.parametrize("asks", [("FORCE_COLOR", "1"), ("TTY_COMPATIBLE", "1")])
def test_the_tests_read_plain_text_even_when_the_shell_forces_color(
    monkeypatch: pytest.MonkeyPatch, asks: tuple[str, str]
) -> None:
    # as when the tests' shell sets it before `friday` is imported: its consoles were made colored
    monkeypatch.setenv(*asks)
    monkeypatch.setattr(render, "out", render.console())
    monkeypatch.setattr(render, "err", render.console(stderr=True))
    plain_output(monkeypatch)
    assert ran().splitlines() == ["friday: boom", "! essay: 3 h late"]
