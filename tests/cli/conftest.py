"""Each CLI test starts on the 12-hour clock, as a `friday` that hasn't asked the server yet does, and prints plain
text whatever the shell running the tests says about color (14 Nov: a full check run in a terminal that sets
FORCE_COLOR read "\\x1b[31mfriday: ..." where the tests expect "friday: ...")."""

from collections.abc import Iterator

import pytest

from friday.cli import render

COLOR_SAYERS = ("FORCE_COLOR", "TTY_COMPATIBLE")


def plain_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """`friday` prints as it would to a pipe: no color, as tests read it."""
    for name in COLOR_SAYERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(render, "out", render.console())
    monkeypatch.setattr(render, "err", render.console(stderr=True))


@pytest.fixture(autouse=True)
def twelve_hour_clock_plain_text(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    plain_output(monkeypatch)
    render.use_clock(lambda: "12h")
    yield
    render.use_clock(lambda: "12h")
