"""Each CLI test starts on the 12-hour clock, as a `friday` that hasn't asked the server yet does."""

from collections.abc import Iterator

import pytest

from friday.cli import render


@pytest.fixture(autouse=True)
def twelve_hour_clock() -> Iterator[None]:
    render.use_clock(lambda: "12h")
    yield
    render.use_clock(lambda: "12h")
